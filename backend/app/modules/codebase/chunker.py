from dataclasses import dataclass
from typing import List, Optional
from app.modules.codebase.parser import ParsedSymbol


@dataclass
class CodeChunk:
    chunk_index: int
    chunk_type: str  # module_header, class_definition, function_body, struct_definition, block, standalone
    start_line: int
    end_line: int
    scope_path: str
    content: str
    token_count: int
    symbol_name: Optional[str] = None


class CodeChunker:
    TARGET_CHUNK_TOKENS: int = 400
    MAX_CHUNK_TOKENS: int = 600

    @classmethod
    def chunk_file(
        cls,
        file_path: str,
        language: str,
        sanitized_source: str,
        symbols: List[ParsedSymbol],
    ) -> List[CodeChunk]:
        lines = sanitized_source.split("\n")
        total_lines = len(lines)
        if total_lines == 0 or not sanitized_source.strip():
            return []

        # Sort symbols by start_line
        sorted_symbols = sorted(symbols, key=lambda s: (s.start_line, -s.end_line))

        chunks: List[CodeChunk] = []
        chunk_idx = 0
        current_line = 1

        # Collect top-level symbols and track gaps
        while current_line <= total_lines:
            # Find any symbol starting at or after current_line
            matching_sym = None
            for sym in sorted_symbols:
                if sym.start_line >= current_line and sym.symbol_type in ("function", "method", "class", "struct", "interface"):
                    matching_sym = sym
                    break

            if matching_sym and matching_sym.start_line > current_line:
                # There is gap code (imports, globals, comments) before the symbol
                gap_start = current_line
                gap_end = matching_sym.start_line - 1
                gap_lines = lines[gap_start - 1 : gap_end]
                gap_content = "\n".join(gap_lines).strip()
                if gap_content:
                    tokens = max(1, len(gap_content) // 4)
                    chunks.append(
                        CodeChunk(
                            chunk_index=chunk_idx,
                            chunk_type="module_header" if gap_start == 1 else "block",
                            start_line=gap_start,
                            end_line=gap_end,
                            scope_path=file_path,
                            content=gap_content,
                            token_count=tokens,
                        )
                    )
                    chunk_idx += 1
                current_line = matching_sym.start_line

            if matching_sym:
                sym_start = matching_sym.start_line
                sym_end = min(total_lines, matching_sym.end_line)
                sym_lines = lines[sym_start - 1 : sym_end]
                sym_content = "\n".join(sym_lines).strip()
                tokens = max(1, len(sym_content) // 4)

                scope = f"{file_path}::{matching_sym.parent_name + '.' if matching_sym.parent_name else ''}{matching_sym.name}"
                ctype = "class_definition" if matching_sym.symbol_type in ("class", "interface") else "function_body"

                if tokens <= cls.MAX_CHUNK_TOKENS:
                    chunks.append(
                        CodeChunk(
                            chunk_index=chunk_idx,
                            chunk_type=ctype,
                            start_line=sym_start,
                            end_line=sym_end,
                            scope_path=scope,
                            content=sym_content,
                            token_count=tokens,
                            symbol_name=matching_sym.name,
                        )
                    )
                    chunk_idx += 1
                else:
                    # Split oversized function/class into sub-blocks
                    sub_chunks = cls._split_oversized_block(
                        lines, sym_start, sym_end, scope, ctype, matching_sym.name, chunk_idx
                    )
                    chunks.extend(sub_chunks)
                    chunk_idx += len(sub_chunks)

                current_line = sym_end + 1
            else:
                # Remaining trailing lines in file
                trail_lines = lines[current_line - 1 : total_lines]
                trail_content = "\n".join(trail_lines).strip()
                if trail_content:
                    tokens = max(1, len(trail_content) // 4)
                    chunks.append(
                        CodeChunk(
                            chunk_index=chunk_idx,
                            chunk_type="standalone",
                            start_line=current_line,
                            end_line=total_lines,
                            scope_path=file_path,
                            content=trail_content,
                            token_count=tokens,
                        )
                    )
                    chunk_idx += 1
                break

        return chunks

    @classmethod
    def _split_oversized_block(
        cls,
        lines: List[str],
        start_line: int,
        end_line: int,
        scope_path: str,
        chunk_type: str,
        symbol_name: str,
        start_idx: int,
    ) -> List[CodeChunk]:
        result = []
        c_idx = start_idx
        idx = start_line
        lines_per_block = 50

        while idx <= end_line:
            block_end = min(end_line, idx + lines_per_block - 1)
            block_lines = lines[idx - 1 : block_end]
            block_content = f"# Context: {scope_path}\n" + "\n".join(block_lines)
            tokens = max(1, len(block_content) // 4)
            result.append(
                CodeChunk(
                    chunk_index=c_idx,
                    chunk_type=chunk_type,
                    start_line=idx,
                    end_line=block_end,
                    scope_path=scope_path,
                    content=block_content,
                    token_count=tokens,
                    symbol_name=symbol_name,
                )
            )
            c_idx += 1
            idx = block_end + 1

        return result
