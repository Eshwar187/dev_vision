from dataclasses import dataclass
from typing import List, Optional, Tuple
import tree_sitter
import tree_sitter_python
import tree_sitter_javascript
import tree_sitter_typescript
import tree_sitter_go
import tree_sitter_rust
import tree_sitter_java


@dataclass
class ParsedSymbol:
    name: str
    symbol_type: str  # module, class, method, function, interface, struct, variable, type_alias
    parent_name: Optional[str]
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int
    signature: Optional[str]
    docstring: Optional[str]


@dataclass
class ParsedImport:
    module_name: str
    symbol_name: Optional[str]
    line_number: int


class CodeParser:
    _languages = {}

    @classmethod
    def get_language(cls, language: str) -> Optional[tree_sitter.Language]:
        if language in cls._languages:
            return cls._languages[language]

        try:
            if language == "python":
                lang = tree_sitter.Language(tree_sitter_python.language())
            elif language == "javascript":
                lang = tree_sitter.Language(tree_sitter_javascript.language())
            elif language == "typescript":
                lang = tree_sitter.Language(tree_sitter_typescript.language_typescript())
            elif language == "go":
                lang = tree_sitter.Language(tree_sitter_go.language())
            elif language == "rust":
                lang = tree_sitter.Language(tree_sitter_rust.language())
            elif language == "java":
                lang = tree_sitter.Language(tree_sitter_java.language())
            else:
                return None
            cls._languages[language] = lang
            return lang
        except Exception:
            return None

    @classmethod
    def parse_source(
        cls, language: str, source_text: str
    ) -> Tuple[List[ParsedSymbol], List[ParsedImport]]:
        lang = cls.get_language(language)
        if not lang:
            return [], []

        parser = tree_sitter.Parser()
        parser.language = lang
        source_bytes = source_text.encode("utf-8")
        tree = parser.parse(source_bytes)

        symbols: List[ParsedSymbol] = []
        imports: List[ParsedImport] = []

        cls._traverse_node(tree.root_node, language, source_bytes, None, symbols, imports)
        return symbols, imports

    @classmethod
    def _get_node_text(cls, node: tree_sitter.Node, source_bytes: bytes) -> str:
        return source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

    @classmethod
    def _traverse_node(
        cls,
        node: tree_sitter.Node,
        language: str,
        source_bytes: bytes,
        current_parent: Optional[str],
        symbols: List[ParsedSymbol],
        imports: List[ParsedImport],
    ):
        ntype = node.type

        # ----------------- PYTHON -----------------
        if language == "python":
            if ntype in ("function_definition", "async_function_definition"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = cls._get_node_text(name_node, source_bytes)
                    sym_type = "method" if current_parent else "function"
                    symbols.append(
                        ParsedSymbol(
                            name=name,
                            symbol_type=sym_type,
                            parent_name=current_parent,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            signature=f"def {name}(...)",
                            docstring=None,
                        )
                    )
            elif ntype == "class_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = cls._get_node_text(name_node, source_bytes)
                    symbols.append(
                        ParsedSymbol(
                            name=name,
                            symbol_type="class",
                            parent_name=current_parent,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            signature=f"class {name}",
                            docstring=None,
                        )
                    )
                    # Recurse inside class with parent set
                    for child in node.children:
                        cls._traverse_node(child, language, source_bytes, name, symbols, imports)
                    return
            elif ntype in ("import_statement", "import_from_statement"):
                text = cls._get_node_text(node, source_bytes).strip()
                imports.append(
                    ParsedImport(
                        module_name=text,
                        symbol_name=None,
                        line_number=node.start_point[0] + 1,
                    )
                )

        # ------------- TYPESCRIPT / JAVASCRIPT -------------
        elif language in ("javascript", "typescript"):
            if ntype in ("function_declaration", "method_definition", "arrow_function"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = cls._get_node_text(name_node, source_bytes)
                    sym_type = "method" if current_parent else "function"
                    symbols.append(
                        ParsedSymbol(
                            name=name,
                            symbol_type=sym_type,
                            parent_name=current_parent,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            signature=f"{name}()",
                            docstring=None,
                        )
                    )
            elif ntype in ("class_declaration", "interface_declaration", "type_alias_declaration"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = cls._get_node_text(name_node, source_bytes)
                    st = "interface" if "interface" in ntype else ("type_alias" if "type" in ntype else "class")
                    symbols.append(
                        ParsedSymbol(
                            name=name,
                            symbol_type=st,
                            parent_name=current_parent,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            signature=f"{st} {name}",
                            docstring=None,
                        )
                    )
                    for child in node.children:
                        cls._traverse_node(child, language, source_bytes, name, symbols, imports)
                    return
            elif ntype in ("import_statement", "import_declaration"):
                text = cls._get_node_text(node, source_bytes).strip()
                imports.append(
                    ParsedImport(
                        module_name=text,
                        symbol_name=None,
                        line_number=node.start_point[0] + 1,
                    )
                )

        # ----------------- GO -----------------
        elif language == "go":
            if ntype in ("function_declaration", "method_declaration"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = cls._get_node_text(name_node, source_bytes)
                    symbols.append(
                        ParsedSymbol(
                            name=name,
                            symbol_type="function" if ntype == "function_declaration" else "method",
                            parent_name=current_parent,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            signature=f"func {name}",
                            docstring=None,
                        )
                    )
            elif ntype == "type_spec":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = cls._get_node_text(name_node, source_bytes)
                    symbols.append(
                        ParsedSymbol(
                            name=name,
                            symbol_type="struct",
                            parent_name=current_parent,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            signature=f"type {name}",
                            docstring=None,
                        )
                    )
            elif ntype == "import_declaration":
                text = cls._get_node_text(node, source_bytes).strip()
                imports.append(
                    ParsedImport(
                        module_name=text,
                        symbol_name=None,
                        line_number=node.start_point[0] + 1,
                    )
                )

        # ----------------- RUST -----------------
        elif language == "rust":
            if ntype == "function_item":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = cls._get_node_text(name_node, source_bytes)
                    symbols.append(
                        ParsedSymbol(
                            name=name,
                            symbol_type="method" if current_parent else "function",
                            parent_name=current_parent,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            signature=f"fn {name}",
                            docstring=None,
                        )
                    )
            elif ntype in ("struct_item", "enum_item", "trait_item", "impl_item"):
                name_node = node.child_by_field_name("name")
                name = cls._get_node_text(name_node, source_bytes) if name_node else "impl"
                st = "struct" if "struct" in ntype else ("trait" if "trait" in ntype else "class")
                symbols.append(
                    ParsedSymbol(
                        name=name,
                        symbol_type=st,
                        parent_name=current_parent,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        start_byte=node.start_byte,
                        end_byte=node.end_byte,
                        signature=f"{ntype} {name}",
                        docstring=None,
                    )
                )
                for child in node.children:
                    cls._traverse_node(child, language, source_bytes, name, symbols, imports)
                return
            elif ntype == "use_declaration":
                text = cls._get_node_text(node, source_bytes).strip()
                imports.append(
                    ParsedImport(
                        module_name=text,
                        symbol_name=None,
                        line_number=node.start_point[0] + 1,
                    )
                )

        # ----------------- JAVA -----------------
        elif language == "java":
            if ntype in ("method_declaration", "constructor_declaration"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = cls._get_node_text(name_node, source_bytes)
                    symbols.append(
                        ParsedSymbol(
                            name=name,
                            symbol_type="method",
                            parent_name=current_parent,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            signature=f"{name}()",
                            docstring=None,
                        )
                    )
            elif ntype in ("class_declaration", "interface_declaration", "enum_declaration"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = cls._get_node_text(name_node, source_bytes)
                    st = "interface" if "interface" in ntype else "class"
                    symbols.append(
                        ParsedSymbol(
                            name=name,
                            symbol_type=st,
                            parent_name=current_parent,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            signature=f"{st} {name}",
                            docstring=None,
                        )
                    )
                    for child in node.children:
                        cls._traverse_node(child, language, source_bytes, name, symbols, imports)
                    return
            elif ntype == "import_declaration":
                text = cls._get_node_text(node, source_bytes).strip()
                imports.append(
                    ParsedImport(
                        module_name=text,
                        symbol_name=None,
                        line_number=node.start_point[0] + 1,
                    )
                )

        # Default: Traverse children
        for child in node.children:
            cls._traverse_node(child, language, source_bytes, current_parent, symbols, imports)
