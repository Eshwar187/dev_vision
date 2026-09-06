from dataclasses import dataclass, field
from typing import List, Optional


class DocumentExtractionError(Exception):
    """Raised when document extraction encounters an unrecoverable structural or encoding error."""
    pass


@dataclass
class ExtractedSection:
    """Represents an extracted unit of text with structural and page provenance."""
    text: str
    page_number: Optional[int] = None
    section_heading: Optional[str] = None


@dataclass
class ExtractionResult:
    """Represents the complete extracted document payload."""
    sections: List[ExtractedSection] = field(default_factory=list)
    unextractable_pages: List[int] = field(default_factory=list)
    total_characters: int = 0
