import io
import zipfile
import pytest
from app.core.exceptions import (
    FileTooLargeException,
    UnsupportedMediaTypeException,
    ValidationException,
)
from app.modules.documents.validator import (
    MAX_FILE_SIZE_DEFAULT,
    MAX_TEXT_FILE_SIZE,
    sanitize_filename,
    validate_docx_zip,
    validate_file_content,
)


def create_mock_docx(
    include_content_types: bool = True,
    include_word_doc: bool = True,
    corrupt_zip: bool = False,
    extra_entries: dict = None,
) -> bytes:
    """Creates an in-memory valid or corrupted DOCX zip archive."""
    bio = io.BytesIO()
    if corrupt_zip:
        return b"PK\x03\x04corrupted_payload"

    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        if include_content_types:
            zf.writestr("[Content_Types].xml", "<Types></Types>")
        if include_word_doc:
            zf.writestr("word/document.xml", "<w:document></w:document>")
        if extra_entries:
            for name, content in extra_entries.items():
                zf.writestr(name, content)
    return bio.getvalue()


class TestFilenameSanitization:
    def test_basic_valid_filename(self):
        name, ext = sanitize_filename("architecture.pdf")
        assert name == "architecture.pdf"
        assert ext == "pdf"

    def test_multi_dot_filename_allowed(self):
        name, ext = sanitize_filename("report.v2.final.pdf")
        assert name == "report.v2.final.pdf"
        assert ext == "pdf"

        name2, ext2 = sanitize_filename("script.py.txt")
        assert name2 == "script.py.txt"
        assert ext2 == "txt"

    def test_double_extension_executable_rejected(self):
        with pytest.raises(UnsupportedMediaTypeException):
            sanitize_filename("exploit.pdf.exe")

    def test_path_traversal_stripping(self):
        # Unix traversal
        name1, ext1 = sanitize_filename("../../etc/passwd.pdf")
        assert name1 == "passwd.pdf"
        assert ext1 == "pdf"

        # Windows traversal
        name2, ext2 = sanitize_filename(r"..\..\Windows\System32\cmd.txt")
        assert name2 == "cmd.txt"
        assert ext2 == "txt"

    def test_control_and_bidi_characters_removed(self):
        # Filename with Right-to-Left Override (\u202e) and null bytes
        malicious = "legit\u202efdp.exe\x00.pdf"
        name, ext = sanitize_filename(malicious)
        assert "\u202e" not in name
        assert "\x00" not in name
        assert ext == "pdf"

    def test_empty_or_no_extension(self):
        with pytest.raises(ValidationException):
            sanitize_filename("")

        with pytest.raises(UnsupportedMediaTypeException):
            sanitize_filename("no_extension_file")

    def test_length_truncation_preserves_extension(self):
        long_name = "a" * 250 + ".pdf"
        name, ext = sanitize_filename(long_name)
        assert len(name) <= 200
        assert name.endswith(".pdf")
        assert ext == "pdf"


class TestContentValidation:
    def test_valid_pdf_signature(self):
        pdf_bytes = b"%PDF-1.7\nSample content"
        mime = validate_file_content(pdf_bytes, "pdf")
        assert mime == "application/pdf"

    def test_invalid_pdf_signature_rejected(self):
        fake_pdf = b"NOT_A_PDF_HEADER"
        with pytest.raises(ValidationException, match="Header signature"):
            validate_file_content(fake_pdf, "pdf")

    def test_valid_txt_and_md(self):
        txt_bytes = "Hello, world! Unicode: 🚀".encode("utf-8")
        assert validate_file_content(txt_bytes, "txt") == "text/plain"

        md_bytes = "# Title\n\n**Bold markdown text**".encode("utf-8")
        assert validate_file_content(md_bytes, "md") == "text/markdown"

    def test_txt_with_null_byte_rejected(self):
        poisoned = b"Hello\x00World"
        with pytest.raises(ValidationException, match="prohibited NUL bytes"):
            validate_file_content(poisoned, "txt")

    def test_txt_invalid_utf8_rejected(self):
        invalid_utf8 = b"\xff\xfe\x00\x00"
        with pytest.raises(ValidationException):
            validate_file_content(invalid_utf8, "txt")

    def test_empty_file_rejected(self):
        with pytest.raises(ValidationException, match="0 bytes"):
            validate_file_content(b"", "pdf")

    def test_oversized_file_rejected(self):
        large_bytes = b"a" * (MAX_FILE_SIZE_DEFAULT + 10)
        with pytest.raises(FileTooLargeException):
            validate_file_content(large_bytes, "pdf")


class TestDocxZipValidation:
    def test_valid_docx(self):
        docx_bytes = create_mock_docx()
        mime = validate_file_content(docx_bytes, "docx")
        assert mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    def test_docx_corrupt_zip_rejected(self):
        corrupt = b"PK\x03\x04invalid_garbage"
        with pytest.raises(ValidationException):
            validate_docx_zip(corrupt)

    def test_docx_missing_content_types_rejected(self):
        bad_docx = create_mock_docx(include_content_types=False)
        with pytest.raises(ValidationException, match="Missing '\\[Content_Types\\].xml'"):
            validate_docx_zip(bad_docx)

    def test_docx_with_embedded_executable_rejected(self):
        bad_docx = create_mock_docx(extra_entries={"word/media/malicious.exe": b"MZ\x90\x00"})
        with pytest.raises(ValidationException, match="prohibited executable entry"):
            validate_docx_zip(bad_docx)

    def test_docx_path_traversal_entry_rejected(self):
        bad_docx = create_mock_docx(extra_entries={"../../outside.xml": b"<xml/>"})
        with pytest.raises(ValidationException, match="path traversal"):
            validate_docx_zip(bad_docx)
