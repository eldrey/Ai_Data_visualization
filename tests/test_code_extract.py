from src.utils.code_extract import extract_python_code


def test_extracts_python_block():
    text = "Aqui está:\n```python\nx = 1\n```\nFim."
    assert extract_python_code(text) == "x = 1\n"


def test_picks_largest_block():
    text = "```python\na = 1\n```\n```py\nb = 2\nc = 3\n```"
    assert extract_python_code(text) == "b = 2\nc = 3\n"


def test_plain_fence_and_no_fence():
    assert extract_python_code("```\ny = 2\n```") == "y = 2\n"
    assert extract_python_code("  z = 3  ") == "z = 3\n"
    assert extract_python_code("") == "\n"
