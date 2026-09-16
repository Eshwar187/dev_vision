import io
import os
import zipfile
from dataclasses import dataclass
from typing import Generator, List, Optional, Set, Tuple

from app.core.exceptions import ValidationException

MAX_UNCOMPRESSED_ARCHIVE_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB
MAX_ARCHIVE_FILE_COUNT = 10_000
MAX_SINGLE_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_COMPRESSION_RATIO = 50.0

IGNORED_DIRECTORIES: Set[str] = {
    ".git",
    ".github",
    ".gitlab",
    ".vscode",
    ".idea",
    "node_modules",
    "vendor",
    "venv",
    ".venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "build",
    "target",
    "bin",
    "obj",
    "coverage",
    ".turbo",
    ".next",
    ".nuxt",
}

IGNORED_EXTENSIONS: Set[str] = {
    # Binaries, compiled, archives
    ".exe", ".dll", ".so", ".dylib", ".bin", ".pyc", ".pyo", ".pyd",
    ".class", ".jar", ".war", ".ear", ".o", ".a", ".lib",
    ".zip", ".tar", ".gz", ".7z", ".rar", ".bz2", ".xz",
    # Media & fonts
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".bmp",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ".ttf", ".woff", ".woff2", ".eot",
    # Database, maps, and logs
    ".sqlite", ".db", ".log", ".map", ".lock",
}

# Explicitly supported source languages
SUPPORTED_EXTENSIONS_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    # Text / configs for auxiliary context
    ".md": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".sql": "sql",
}


@dataclass
class ExtractedSourceFile:
    repo_relative_path: str
    filename: str
    extension: str
    language: str
    byte_size: int
    raw_content: bytes


class SecureArchiveExtractor:
    @staticmethod
    def inspect_and_extract_safe_files(
        archive_bytes: bytes,
    ) -> List[ExtractedSourceFile]:
        if not archive_bytes:
            raise ValidationException("Repository archive is empty.")

        try:
            zf = zipfile.ZipFile(io.BytesIO(archive_bytes))
        except zipfile.BadZipFile:
            raise ValidationException("File is not a valid ZIP archive.")

        infolist = zf.infolist()
        if len(infolist) > MAX_ARCHIVE_FILE_COUNT:
            raise ValidationException(
                f"Archive exceeds maximum file count limit ({MAX_ARCHIVE_FILE_COUNT} files)."
            )

        total_uncompressed_size = 0
        extracted_files: List[ExtractedSourceFile] = []

        for info in infolist:
            # 1. Reject symlinks and special files
            # Check UNIX file attributes for symlinks (0o120000)
            is_symlink = (info.external_attr >> 16) & 0o120000 == 0o120000
            if is_symlink:
                continue

            # Skip directories
            if info.is_dir() or info.filename.endswith("/"):
                continue

            # 2. Decompression Bomb & Path Traversal Checks
            # Normalize path
            norm_path = os.path.normpath(info.filename).replace("\\", "/")
            if norm_path.startswith("/") or norm_path.startswith("../") or "/../" in norm_path:
                raise ValidationException(f"Path traversal detected in archive entry: {info.filename}")

            # Strip leading drive letters or device names on Windows
            if ":" in norm_path:
                raise ValidationException(f"Invalid path with device specifier: {info.filename}")

            # Strip any root directory prefix (e.g. repo-main/src/foo -> src/foo)
            parts = norm_path.split("/")
            if len(parts) > 1 and (parts[0].endswith("-master") or parts[0].endswith("-main") or "-" in parts[0]):
                # Strip leading wrapper folder if present
                clean_path = "/".join(parts[1:])
            else:
                clean_path = norm_path

            clean_parts = clean_path.split("/")
            # Check ignored directories
            if any(part in IGNORED_DIRECTORIES for part in clean_parts):
                continue

            filename = clean_parts[-1]
            ext = os.path.splitext(filename)[1].lower()

            if ext in IGNORED_EXTENSIONS:
                continue

            if ext not in SUPPORTED_EXTENSIONS_MAP:
                continue

            # Compression ratio check
            if info.compress_size > 0:
                ratio = info.file_size / info.compress_size
                if ratio > MAX_COMPRESSION_RATIO:
                    raise ValidationException(
                        f"Decompression bomb detected: file {info.filename} has ratio {ratio:.1f}:1"
                    )

            if info.file_size > MAX_SINGLE_FILE_SIZE_BYTES:
                continue  # Skip single oversized files safely

            total_uncompressed_size += info.file_size
            if total_uncompressed_size > MAX_UNCOMPRESSED_ARCHIVE_SIZE_BYTES:
                raise ValidationException(
                    f"Archive exceeds maximum uncompressed size ({MAX_UNCOMPRESSED_ARCHIVE_SIZE_BYTES // (1024*1024)} MB)."
                )

            # Read and verify content
            try:
                content = zf.read(info)
            except Exception as e:
                raise ValidationException(f"Failed reading archive entry {info.filename}: {str(e)}")

            extracted_files.append(
                ExtractedSourceFile(
                    repo_relative_path=clean_path,
                    filename=filename,
                    extension=ext,
                    language=SUPPORTED_EXTENSIONS_MAP[ext],
                    byte_size=len(content),
                    raw_content=content,
                )
            )

        if not extracted_files:
            raise ValidationException("Archive contains no supported source files to index.")

        return extracted_files
