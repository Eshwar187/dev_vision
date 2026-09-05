import io
import re
import unicodedata
import zipfile
from typing import Tuple
from app.core.exceptions import (
    FileTooLargeException,
    UnsupportedMediaTypeException,
    ValidationException,
)

# Supported extensions and canonical MIME types
SUPPORTED_EXTENSIONS = {
    "pdf": "application/pdf",
    "txt": "text/plain",
    "md": "text/markdown",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

MAX_FILE_SIZE_DEFAULT = 20 * 1024 * 1024  # 20 MB ceiling
MAX_TEXT_FILE_SIZE = 10 * 1024 * 1024     # 10 MB ceiling for txt/md


def sanitize_filename(raw_name: str) -> Tuple[str, str]:
    """
    Sanitizes and normalizes an uploaded filename.
    Returns (safe_display_name, final_extension_without_dot).

    Rules:
    - Normalizes both '/' and '\\' path separators
    - Applies Unicode normalization Form KC (NFKC)
    - Removes ASCII control characters, NUL bytes, CR/LF
    - Removes bidirectional control characters and zero-width markers
    - Preserves legitimate multi-dot filenames (e.g. 'report.v2.pdf')
    - Extracts and validates the final extension
    - Truncates display filename to max 200 chars while preserving extension
    - Provides safe fallback name if result is empty
    """
    if not raw_name:
        raise ValidationException("Filename must not be empty.")

    # 1. Handle both Unix and Windows path separators
    cleaned = raw_name.replace("\\", "/").split("/")[-1].strip()

    # 2. Unicode normalization (NFKC)
    cleaned = unicodedata.normalize("NFKC", cleaned)

    # 3. Strip control characters, NUL, CR, LF, and bidi override characters
    # Bidi characters: \u202a-\u202e, \u2066-\u2069, zero-width: \u200b-\u200d, \ufeff
    bad_chars = re.compile(r"[\x00-\x1f\x7f\r\n\u202a-\u202e\u2066-\u2069\u200b-\u200d\ufeff]")
    cleaned = bad_chars.sub("", cleaned)

    # 4. Extract final extension after the last dot
    if "." not in cleaned:
        raise UnsupportedMediaTypeException(
            "File lacks an extension. Supported extensions: .pdf, .txt, .md, .docx"
        )

    parts = cleaned.rsplit(".", 1)
    base_stem = parts[0].strip()
    ext = parts[1].lower().strip()

    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedMediaTypeException(
            f"Extension '.{ext}' is not supported. Supported extensions: .pdf, .txt, .md, .docx"
        )

    # 5. Sanitize stem and enforce fallback
    # Remove any remaining dangerous characters from stem
    safe_stem = re.sub(r'[<>:"/\\|?*]', "_", base_stem).strip()
    if not safe_stem:
        safe_stem = "unnamed_document"

    # 6. Enforce max display length (200 chars max, keeping stem truncated)
    max_stem_len = 200 - len(ext) - 1
    if len(safe_stem) > max_stem_len:
        safe_stem = safe_stem[:max_stem_len].rstrip("._- ")

    safe_filename = f"{safe_stem}.{ext}"
    return safe_filename, ext


def validate_file_content(file_bytes: bytes, extension: str) -> str:
    """
    Validates file payload content based on the final extension.
    Enforces size limits, magic bytes, and structural zip constraints for DOCX.
    Returns the canonical MIME type string.
    """
    size = len(file_bytes)
    if size == 0:
        raise ValidationException("File payload is empty (0 bytes).")

    # Size check based on extension
    if extension in ("txt", "md"):
        if size > MAX_TEXT_FILE_SIZE:
            raise FileTooLargeException(
                f"Text/Markdown files must not exceed {MAX_TEXT_FILE_SIZE // (1024 * 1024)} MB."
            )
    else:
        if size > MAX_FILE_SIZE_DEFAULT:
            raise FileTooLargeException(
                f"Files must not exceed {MAX_FILE_SIZE_DEFAULT // (1024 * 1024)} MB."
            )

    # Content signature validation
    if extension == "pdf":
        # Lightweight signature validation: Must start with %PDF-
        if not file_bytes.startswith(b"%PDF-"):
            raise ValidationException(
                "Invalid PDF file. Header signature '%PDF-' not found."
            )
        return SUPPORTED_EXTENSIONS["pdf"]

    elif extension in ("txt", "md"):
        # Must be valid UTF-8 and have no NUL bytes
        if b"\x00" in file_bytes:
            raise ValidationException("Text file contains prohibited NUL bytes.")
        try:
            file_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationException("Text file contains invalid UTF-8 encoding.") from exc
        return SUPPORTED_EXTENSIONS[extension]

    elif extension == "docx":
        # Must pass standard-library zipfile OOXML validation
        validate_docx_zip(file_bytes)
        return SUPPORTED_EXTENSIONS["docx"]

    raise UnsupportedMediaTypeException(f"Unsupported extension '.{extension}'.")


def validate_docx_zip(file_bytes: bytes) -> None:
    """
    Inspects in-memory DOCX package using standard library zipfile.
    Enforces OOXML entry existence, compression ratio limits, entry counts,
    and prohibits encrypted entries, archive traversal, or embedded executables.
    """
    # 1. Header signature check (PK\x03\x04)
    if not file_bytes.startswith(b"PK\x03\x04"):
        raise ValidationException("Invalid DOCX file. ZIP header signature not found.")

    bio = io.BytesIO(file_bytes)
    if not zipfile.is_zipfile(bio):
        raise ValidationException("Invalid DOCX file. File is not a valid ZIP archive.")

    try:
        with zipfile.ZipFile(bio, "r") as zf:
            infolist = zf.infolist()

            # 2. Maximum entry count
            if len(infolist) > 500:
                raise ValidationException(
                    "DOCX package rejected. Archive contains more than 500 entries."
                )

            # 3. Check for required OOXML components
            names = set(zf.namelist())
            if "[Content_Types].xml" not in names:
                raise ValidationException(
                    "Invalid DOCX structure. Missing '[Content_Types].xml'."
                )
            if not any(
                n.startswith("word/") or n == "_rels/.rels" for n in names
            ):
                raise ValidationException(
                    "Invalid DOCX structure. Missing document structure components."
                )

            # 4. Check entries for zip bombs, encryption, traversal, and executables
            total_uncompressed = 0
            executable_extensions = {
                ".exe", ".dll", ".bat", ".cmd", ".sh", ".ps1", ".vbs", ".js",
                ".scr", ".bin", ".com", ".pif", ".msi", ".jar", ".app"
            }

            for info in infolist:
                # Reject encrypted zip entries
                if info.flag_bits & 0x1:
                    raise ValidationException(
                        "Encrypted or password-protected DOCX files are not permitted."
                    )

                # Reject path traversal or null bytes in entry names
                name = info.filename
                if "\x00" in name or ".." in name or name.startswith("/") or "\\" in name:
                    raise ValidationException(
                        "DOCX archive contains unsafe entry paths (path traversal)."
                    )

                # Reject embedded executables
                lower_name = name.lower()
                if any(lower_name.endswith(ext) for ext in executable_extensions):
                    raise ValidationException(
                        f"DOCX archive contains prohibited executable entry: {name}"
                    )

                total_uncompressed += info.file_size

            # Cumulative uncompressed size ceiling (100 MB max)
            if total_uncompressed > 100 * 1024 * 1024:
                raise ValidationException(
                    "DOCX uncompressed size exceeds maximum permitted threshold (100 MB)."
                )

            # Compression ratio check (Zip bomb defense, max 10:1 ratio)
            compressed_size = len(file_bytes)
            if compressed_size > 0:
                ratio = total_uncompressed / compressed_size
                if ratio > 10.0:
                    raise ValidationException(
                        f"DOCX compression ratio ({ratio:.1f}:1) exceeds safe limit (10:1)."
                    )

    except zipfile.BadZipFile as exc:
        raise ValidationException("Corrupted DOCX archive.") from exc
