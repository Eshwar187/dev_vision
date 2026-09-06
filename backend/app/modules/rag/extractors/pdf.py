import io
import pymupdf
from app.modules.rag.extractors.base import DocumentExtractionError, ExtractedSection, ExtractionResult


class PdfExtractor:
    """
    Extracts text from PDF documents page-by-page using PyMuPDF.
    Preserves 1-indexed page numbers.
    Tracks unextractable (e.g. scanned or empty) pages.
    Raises DocumentExtractionError if the entire PDF contains zero extractable text.
    """

    @classmethod
    def extract(cls, file_bytes: bytes) -> ExtractionResult:
        if not file_bytes:
            raise DocumentExtractionError("PDF file payload is empty.")

        try:
            doc = pymupdf.open(stream=file_bytes, filetype="pdf")
        except Exception as exc:
            raise DocumentExtractionError(f"Failed to parse PDF document: {str(exc)}") from exc

        sections = []
        unextractable_pages = []
        total_chars = 0

        try:
            for page_index in range(len(doc)):
                page_num = page_index + 1  # 1-indexed page number
                page = doc[page_index]
                page_text = page.get_text("text").strip()

                if not page_text:
                    unextractable_pages.append(page_num)
                else:
                    sections.append(
                        ExtractedSection(
                            text=page_text,
                            page_number=page_num,
                            section_heading=None,
                        )
                    )
                    total_chars += len(page_text)
        finally:
            doc.close()

        if not sections:
            raise DocumentExtractionError(
                "No extractable text found in PDF. Scanned documents require OCR, which is scheduled for Phase 9."
            )

        return ExtractionResult(
            sections=sections,
            unextractable_pages=unextractable_pages,
            total_characters=total_chars,
        )
