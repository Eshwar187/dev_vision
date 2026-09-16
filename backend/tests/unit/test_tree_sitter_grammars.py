import pytest
import tree_sitter
import tree_sitter_python
import tree_sitter_javascript
import tree_sitter_typescript
import tree_sitter_go
import tree_sitter_rust
import tree_sitter_java

from app.modules.codebase.parser import CodeParser

@pytest.mark.parametrize(
    "language, source_code, expected_symbol_name, expected_symbol_type",
    [
        ("python", "def calculate_sum(a: int, b: int) -> int:\n    return a + b\n", "calculate_sum", "function"),
        ("javascript", "function authenticateUser(token) { return true; }\n", "authenticateUser", "function"),
        ("typescript", "interface UserProfile { id: string; name: string; }\n", "UserProfile", "interface"),
        ("go", "package main\nfunc ExecuteTask() error { return nil }\n", "ExecuteTask", "function"),
        ("rust", "pub fn process_event() -> bool { true }\n", "process_event", "function"),
        ("java", "public class AuthService { public void login() {} }\n", "AuthService", "class"),
    ],
)
def test_grammar_parsing_smoke(language, source_code, expected_symbol_name, expected_symbol_type):
    symbols, imports = CodeParser.parse_source(language, source_code)
    assert len(symbols) >= 1
    found = any(s.name == expected_symbol_name and s.symbol_type == expected_symbol_type for s in symbols)
    assert found, f"Expected {expected_symbol_type} {expected_symbol_name} in {symbols}"