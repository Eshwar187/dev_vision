import re
from app.modules.rag.extractors.base import DocumentExtractionError, ExtractedSection, ExtractionResult


class TextExtractor:
    """
    Extracts text from TXT and Markdown files.
    Enforces strict UTF-8 decoding without silent replacement (errors="replace" is prohibited).
    Parses Markdown #, ##, ### headings to maintain section hierarchy.
    """

    @classmethod
    def extract(cls, file_bytes: bytes, is_markdown: bool = False) -> ExtractionResult:
        if not file_bytes:
            raise DocumentExtractionError("Text file payload is empty.")

        try:
            full_text = file_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentExtractionError(
                f"Invalid UTF-8 byte at offset {exc.start}. DevVision requires strict UTF-8 encoded text."
            ) from exc

        if not full_text.strip():
            raise DocumentExtractionError("Text file contains no extractable non-whitespace characters.")

        if not is_markdown:
            return ExtractionResult(
                sections=[
                    ExtractedSection(
                        text=full_text.strip(),
                        page_number=None,
                        section_heading=None,
                    )
                ],
                unextractable_pages=[],
                total_characters=len(full_text.strip()),
            )

        # Markdown heading parsing
        sections = []
        current_heading = None
        current_buffer = []

        heading_pattern = re.compile(r"^(#{1,3})\s+(.+)$")

        for line in full_text.splitlines():
            match = heading_pattern.match(line.strip())
            if match:
                if current_buffer:
                    chunk_text = "\n".join(current_buffer).strip()
                    if chunk_text:
                        sections.append(
                            ExtractedSection(
                                text=chunk_text,
                                page_number=None,
                                section_heading=current_heading,
                            )
                        )
                    current_buffer = []

                current_heading = match.group(2).strip()
                current_buffer.append(line)
            else:
                current_buffer.append(line)

        if current_buffer:
            chunk_text = "\n".join(current_buffer).strip()
            if chunk_text:
                sections.append(
                    ExtractedSection(
                        text=chunk_text,
                        page_number=None,
                        section_heading=current_heading,
                    )
                )

        return ExtractionResult(
            sections=sections,
            unextractable_pages=[],
            total_characters=sum(len(s.text) for s in sections),
        )
