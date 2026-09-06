from dataclasses import dataclass
from typing import List, Optional
import re
from transformers import AutoTokenizer

from app.modules.rag.extractors.base import ExtractedSection


@dataclass
class ChunkPayload:
    chunk_index: int
    page_number: Optional[int]
    section_heading: Optional[str]
    token_count: int
    text_content: str

    @property
    def content(self) -> str:
        return self.text_content



class RecursiveStructuralChunker:
    """
    Deterministic structural chunker using authoritative HuggingFace AutoTokenizer
    (BAAI/bge-small-en-v1.5, WordPiece).
    
    Target: 500 tokens
    Overlap: 50 tokens
    
    Splitting hierarchy:
    1. Paragraph boundaries (\n\n)
    2. Single newlines (\n)
    3. Sentence boundaries (. , ? , ! )
    4. Whitespace ( )
    """

    def __init__(
        self,
        tokenizer_name: str = "BAAI/bge-small-en-v1.5",
        target_tokens: int = 500,
        overlap_tokens: int = 50,
    ):
        self.tokenizer_name = tokenizer_name
        self.target_tokens = target_tokens
        self.overlap_tokens = overlap_tokens
        self._tokenizer = AutoTokenizer.from_pretrained(tokenizer_name)

    def count_tokens(self, text: str) -> int:
        return len(self._tokenizer.encode(text, add_special_tokens=False))

    def chunk_document(
        self,
        sections: List[ExtractedSection],
        target_tokens: Optional[int] = None,
        overlap_tokens: Optional[int] = None,
    ) -> List[ChunkPayload]:
        """Convenience alias for chunking a list of sections."""
        if target_tokens is not None:
            self.target_tokens = target_tokens
        if overlap_tokens is not None:
            self.overlap_tokens = overlap_tokens
        return self.chunk_sections(sections)

    def chunk_sections(self, sections: List[ExtractedSection]) -> List[ChunkPayload]:
        """
        Chunks extracted sections preserving page numbers and heading provenance.
        Deterministic chunk indexing 0..N.
        """
        all_chunks: List[ChunkPayload] = []
        chunk_index = 0

        for section in sections:
            section_chunks = self._chunk_single_section(
                text=section.text,
                page_number=section.page_number,
                section_heading=section.section_heading,
                start_index=chunk_index,
            )
            all_chunks.extend(section_chunks)
            chunk_index += len(section_chunks)

        return all_chunks

    def _chunk_single_section(
        self,
        text: str,
        page_number: Optional[int],
        section_heading: Optional[str],
        start_index: int,
    ) -> List[ChunkPayload]:
        clean_text = text.strip()
        if not clean_text:
            return []

        tokens = self._tokenizer.encode(clean_text, add_special_tokens=False)
        total_tokens = len(tokens)

        # If fits in a single chunk
        if total_tokens <= self.target_tokens:
            return [
                ChunkPayload(
                    chunk_index=start_index,
                    page_number=page_number,
                    section_heading=section_heading,
                    token_count=total_tokens,
                    text_content=clean_text,
                )
            ]

        # Recursive splitting into units
        units = self._split_text_recursively(clean_text)
        
        chunks: List[ChunkPayload] = []
        current_units: List[str] = []
        current_token_count = 0
        current_chunk_idx = start_index

        for unit in units:
            unit_tokens = self.count_tokens(unit)
            if not unit.strip():
                continue

            if current_token_count + unit_tokens > self.target_tokens and current_units:
                # Emit current chunk
                chunk_text = " ".join(current_units).strip()
                chunks.append(
                    ChunkPayload(
                        chunk_index=current_chunk_idx,
                        page_number=page_number,
                        section_heading=section_heading,
                        token_count=self.count_tokens(chunk_text),
                        text_content=chunk_text,
                    )
                )
                current_chunk_idx += 1

                # Calculate overlap: backtrack units from the end until ~overlap_tokens reached
                overlap_units = []
                overlap_count = 0
                for u in reversed(current_units):
                    u_tok = self.count_tokens(u)
                    if overlap_count + u_tok <= self.overlap_tokens or not overlap_units:
                        overlap_units.insert(0, u)
                        overlap_count += u_tok
                    else:
                        break

                current_units = list(overlap_units)
                current_token_count = overlap_count

            current_units.append(unit)
            current_token_count += unit_tokens

        if current_units:
            chunk_text = " ".join(current_units).strip()
            if chunk_text:
                chunks.append(
                    ChunkPayload(
                        chunk_index=current_chunk_idx,
                        page_number=page_number,
                        section_heading=section_heading,
                        token_count=self.count_tokens(chunk_text),
                        text_content=chunk_text,
                    )
                )

        return chunks

    def _split_text_recursively(self, text: str) -> List[str]:
        """Splits text along paragraph, newline, sentence, and word boundaries."""
        # Split paragraphs
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        result = []

        for p in paragraphs:
            p_tokens = self.count_tokens(p)
            if p_tokens <= self.target_tokens:
                result.append(p)
            else:
                # Split by single newline
                lines = [line.strip() for line in p.split("\n") if line.strip()]
                for line in lines:
                    line_tokens = self.count_tokens(line)
                    if line_tokens <= self.target_tokens:
                        result.append(line)
                    else:
                        # Split by sentences
                        sentences = re.split(r"(?<=[.?!])\s+", line)
                        for s in sentences:
                            s = s.strip()
                            if not s:
                                continue
                            s_tokens = self.count_tokens(s)
                            if s_tokens <= self.target_tokens:
                                result.append(s)
                            else:
                                # Split by words
                                words = s.split()
                                current_word_chunk = []
                                for w in words:
                                    current_word_chunk.append(w)
                                    if self.count_tokens(" ".join(current_word_chunk)) >= 400:
                                        result.append(" ".join(current_word_chunk))
                                        current_word_chunk = []
                                if current_word_chunk:
                                    result.append(" ".join(current_word_chunk))

        return result
