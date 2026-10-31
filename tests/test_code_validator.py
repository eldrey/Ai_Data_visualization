import pytest

from src.services.code_validator import validate_script


def test_valid_script(valid_script):
    assert validate_script(valid_script) == []


def test_syntax_error():
    errors = validate_script("def x(:")
    assert errors and "sintaxe" in errors[0]


@pytest.mark.parametrize(
    "snippet, expected",
    [
        ("import os", "import não permitido"),
        ("from subprocess import run", "import não permitido"),
        ("import socket", "import não permitido"),
        ("from . import x", "relativos"),
        ("x = open('/etc/passwd')", "open"),
        ("x = eval('1')", "eval"),
        ("x = __import__('os')", "__import__"),
        ("x = ().__class__", "__class__"),
        ("x = getattr(1, 'real')", "getattr"),
        ("def f():\n    global y", "global"),
        ("x = __builtins__", "__builtins__"),
    ],
)
def test_rejects_dangerous_code(valid_script, snippet, expected):
    errors = validate_script(valid_script + "\n" + snippet + "\n")
    assert any(expected in e for e in errors), errors


def test_requires_contract():
    errors = validate_script("import pandas as pd\n")
    assert any("METADATA" in e for e in errors)
    assert any("SQL" in e for e in errors)
    assert any("build_chart" in e for e in errors)


def test_build_chart_signature():
    code = 'METADATA = {}\nSQL = "SELECT 1"\ndef build_chart(df, extra):\n    return df\n'
    assert any("exatamente um argumento" in e for e in validate_script(code))


def test_allows_submodules():
    code = (
        "import plotly.graph_objects as go\nfrom plotly.subplots import make_subplots\n"
        'METADATA = {}\nSQL = "SELECT 1"\ndef build_chart(df):\n    return go.Figure()\n'
    )
    assert validate_script(code) == []
