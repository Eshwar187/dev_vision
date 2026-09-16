from app.modules.codebase.chunker import CodeChunker
from app.modules.codebase.parser import CodeParser


def test_python_structural_chunking():
    code = (
        "import os\n"
        "import sys\n\n"
        "class WorkerPool:\n"
        "    def __init__(self, size: int):\n"
        "        self.size = size\n\n"
        "    def start(self):\n"
        "        print('started')\n\n"
        "def standalone_func():\n"
        "    return 42\n"
    )
    symbols, imports = CodeParser.parse_source("python", code)
    chunks = CodeChunker.chunk_file("worker.py", "python", code, symbols)

    assert len(chunks) >= 2
    types = [c.chunk_type for c in chunks]
    assert "module_header" in types or "class_definition" in types
    assert all(c.token_count > 0 for c in chunks)
    assert all(c.start_line <= c.end_line for c in chunks)