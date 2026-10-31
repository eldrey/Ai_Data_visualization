import pandas as pd
import pytest

from src.services.script_runner import _sandbox_env, render_figure, run_code, run_script
from src.services.script_store import ScriptError, parse_script

DF = pd.DataFrame({"mes": [1, 2], "total": [10, 20]})


def test_render_figure(valid_script):
    fig = render_figure(valid_script, DF)
    assert fig.layout.title.text == "Vendas"


def test_render_rejects_invalid_code(valid_script):
    with pytest.raises(ScriptError, match="inválido"):
        render_figure(valid_script + "\nimport os\n", DF)


def test_render_reports_runtime_error(valid_script):
    code = valid_script.replace('x="mes"', 'x="coluna_inexistente"')
    with pytest.raises(ScriptError, match="Erro ao executar"):
        render_figure(code, DF)


def test_render_requires_figure():
    code = 'METADATA = {}\nSQL = "SELECT 1"\ndef build_chart(df):\n    return 1\n'
    with pytest.raises(ScriptError, match="Plotly"):
        render_figure(code, DF)


def test_render_timeout():
    code = 'METADATA = {}\nSQL = "SELECT 1"\ndef build_chart(df):\n    while True:\n        pass\n'
    with pytest.raises(ScriptError, match="Tempo limite"):
        render_figure(code, DF, timeout=2)


def test_sandbox_env_does_not_leak_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "nao-deve-vazar")
    env = _sandbox_env(str(tmp_path))
    assert "ANTHROPIC_API_KEY" not in env
    assert env["HOME"] == str(tmp_path)


def test_run_script_with_file_source(file_source, valid_script):
    fig = run_script(parse_script("vendas", valid_script), file_source)
    assert fig.data[0].type == "bar"
    assert fig.layout.title.text == "Vendas"


def test_run_code_preview(file_source, valid_script):
    assert run_code(valid_script, file_source).data


def test_run_script_requires_sql(file_source):
    with pytest.raises(ScriptError, match="não define SQL"):
        run_script(parse_script("x", "METADATA = {}\n"), file_source)
