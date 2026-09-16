import io
import zipfile
import pytest
from app.core.exceptions import ValidationException
from app.modules.codebase.extractor import SecureArchiveExtractor


def create_zip_with_files(files_dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, data in files_dict.items():
            zf.writestr(path, data)
    return buf.getvalue()


def test_safe_archive_extraction():
    files = {
        "src/main.py": "def main(): pass",
        "src/utils.ts": "export const x = 1;",
        "README.md": "# Project Title",
    }
    archive_bytes = create_zip_with_files(files)
    extracted = SecureArchiveExtractor.inspect_and_extract_safe_files(archive_bytes)
    assert len(extracted) == 3
    paths = {f.repo_relative_path for f in extracted}
    assert "src/main.py" in paths
    assert "src/utils.ts" in paths
    assert "README.md" in paths


def test_reject_zip_slip_traversal():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        # Malicious traversal path
        zf.writestr("../../etc/passwd", "root:x:0:0:")
    
    with pytest.raises(ValidationException, match="Path traversal detected"):
        SecureArchiveExtractor.inspect_and_extract_safe_files(buf.getvalue())


def test_reject_windows_device_path():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("C:/Windows/System32/evil.py", "print('bad')")
    
    with pytest.raises(ValidationException, match="Invalid path with device specifier"):
        SecureArchiveExtractor.inspect_and_extract_safe_files(buf.getvalue())


def test_ignore_forbidden_directories():
    files = {
        ".git/config": "[core] bare = false",
        "node_modules/lodash/index.js": "module.exports = {};",
        "__pycache__/bad.pyc": "binary",
        "dist/bundle.js": "var x = 1;",
        "src/app.py": "def app(): return True",
    }
    archive_bytes = create_zip_with_files(files)
    extracted = SecureArchiveExtractor.inspect_and_extract_safe_files(archive_bytes)
    assert len(extracted) == 1
    assert extracted[0].repo_relative_path == "src/app.py"


def test_ignore_binary_and_compiled_extensions():
    files = {
        "bin/runner.exe": b"\x4d\x5a\x90\x00",
        "lib/libfoo.so": b"\x7f\x45\x4c\x46",
        "src/code.py": "print('hello')",
    }
    archive_bytes = create_zip_with_files(files)
    extracted = SecureArchiveExtractor.inspect_and_extract_safe_files(archive_bytes)
    assert len(extracted) == 1
    assert extracted[0].repo_relative_path == "src/code.py"


def test_reject_decompression_bomb_ratio():
    buf = io.BytesIO()
    # 1MB of null bytes compresses down to ~1KB (>50:1 ratio)
    compressed_stream = io.BytesIO()
    with zipfile.ZipFile(compressed_stream, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("big_zeros.py", b"\x00" * (1024 * 1024))
    
    with pytest.raises(ValidationException, match="Decompression bomb detected"):
        SecureArchiveExtractor.inspect_and_extract_safe_files(compressed_stream.getvalue())