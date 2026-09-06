from app.modules.rag.extractors.base import DocumentExtractionError, ExtractedSection, ExtractionResult
from app.modules.rag.extractors.pdf import PdfExtractor
from app.modules.rag.extractors.docx import DocxExtractor
from app.modules.rag.extractors.text import TextExtractor

def extract_document(data: bytes, filename: str) -> ExtractionResult:
    """Convenience dispatcher to extract document text based on file extension."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return PdfExtractor().extract(data, filename)
    elif lower.endswith(".docx"):
        return DocxExtractor().extract(data, filename)
    elif lower.endswith(".txt") or lower.endswith(".md"):
        return TextExtractor().extract(data, filename)
    else:
        raise DocumentExtractionError(f"Unsupported file format for extraction: {filename}")

__all__ = [
    "DocumentExtractionError",
    "ExtractedSection",
    "ExtractionResult",
    "PdfExtractor",
    "DocxExtractor",
    "TextExtractor",
    "extract_document",
]

