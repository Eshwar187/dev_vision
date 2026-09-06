import io
import docx
from app.modules.rag.extractors.base import DocumentExtractionError, ExtractedSection, ExtractionResult


class DocxExtractor:
    """
    Extracts text from DOCX documents in document XML order using python-docx.
    Traverses doc.element.body children directly without claiming visual layout.
    Preserves heading hierarchies (Heading 1, 2, 3) and converts tables into Markdown tables.
    """

    @classmethod
    def extract(cls, file_bytes: bytes) -> ExtractionResult:
        if not file_bytes:
            raise DocumentExtractionError("DOCX file payload is empty.")

        try:
            doc = docx.Document(io.BytesIO(file_bytes))
        except Exception as exc:
            raise DocumentExtractionError(f"Failed to parse DOCX document: {str(exc)}") from exc

        sections = []
        current_heading = None
        total_chars = 0

        # Traverse body elements in XML structural order
        for child in doc.element.body:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

            if tag == "p":
                # Paragraph element
                p = docx.text.paragraph.Paragraph(child, doc)
                text = p.text.strip()
                if not text:
                    continue

                style_name = p.style.name if p.style else ""
                if style_name.startswith("Heading"):
                    current_heading = text
                    # Include the heading itself as a section
                    sections.append(
                        ExtractedSection(
                            text=text,
                            page_number=None,
                            section_heading=current_heading,
                        )
                    )
                    total_chars += len(text)
                else:
                    # Regular paragraph or list item
                    sections.append(
                        ExtractedSection(
                            text=text,
                            page_number=None,
                            section_heading=current_heading,
                        )
                    )
                    total_chars += len(text)

            elif tag == "tbl":
                # Table element
                tbl = docx.table.Table(child, doc)
                md_table = cls._table_to_markdown(tbl)
                if md_table:
                    sections.append(
                        ExtractedSection(
                            text=md_table,
                            page_number=None,
                            section_heading=current_heading,
                        )
                    )
                    total_chars += len(md_table)

        if not sections:
            raise DocumentExtractionError("No extractable text or tables found in DOCX.")

        return ExtractionResult(
            sections=sections,
            unextractable_pages=[],
            total_characters=total_chars,
        )

    @staticmethod
    def _table_to_markdown(table: docx.table.Table) -> str:
        """Converts a python-docx Table into a deterministic Markdown table string."""
        if not table.rows:
            return ""

        rows_data = []
        for row in table.rows:
            row_cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            rows_data.append(row_cells)

        if not rows_data:
            return ""

        num_cols = max(len(r) for r in rows_data)
        if num_cols == 0:
            return ""

        # Normalize rows to same column count
        for r in rows_data:
            while len(r) < num_cols:
                r.append("")

        lines = []
        # Header row
        header = rows_data[0]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join(["---"] * num_cols) + " |")

        # Data rows
        for row in rows_data[1:]:
            lines.append("| " + " | ".join(row) + " |")

        return "\n".join(lines)
