from src.services.chart_generator import (
    build_system_prompt,
    build_user_prompt,
    check_code,
    generate_chart_code,
)
from src.services.script_store import parse_script

GOOD = '''```python
import pandas as pd
import plotly.express as px

SQL = "SELECT mes, SUM(valor) AS total FROM vendas GROUP BY mes"

def build_chart(df):
    return px.bar(df, x="mes", y="total")
```'''

BAD_SQL = GOOD.replace("SELECT mes, SUM(valor) AS total FROM vendas GROUP BY mes", "DELETE FROM vendas")


def test_system_prompt_mentions_dialect_and_imports():
    prompt = build_system_prompt("duckdb")
    assert "duckdb" in prompt and "plotly" in prompt and "__future__" not in prompt


def test_user_prompt_includes_schema_and_sample(file_source):
    prompt = build_user_prompt(file_source, [("main", "vendas")], "  vendas por mês ")
    assert '"main"."vendas"' in prompt
    assert "mes: BIGINT" in prompt
    assert "mes,valor" in prompt
    assert prompt.endswith("vendas por mês")


def test_user_prompt_survives_sample_failure(file_source, mocker):
    mocker.patch.object(file_source, "preview", side_effect=RuntimeError("falhou"))
    assert "amostra indisponível" in build_user_prompt(file_source, [("main", "vendas")], "x")


def test_generate_happy_path(file_source, fake_llm_factory):
    llm = fake_llm_factory(GOOD)
    result = generate_chart_code(llm, file_source, "arquivos", [("main", "vendas")], "vendas", "Vendas")
    assert result.ok and result.attempts == 1
    script = parse_script("x", result.code)
    assert script.metadata["source"] == "arquivos"
    assert script.metadata["title"] == "Vendas"
    assert script.metadata["prompt"] == "vendas"


def test_generate_retries_with_errors(file_source, fake_llm_factory):
    llm = fake_llm_factory(BAD_SQL, GOOD)
    result = generate_chart_code(llm, file_source, "arquivos", [("main", "vendas")], "vendas", "V")
    assert result.ok and result.attempts == 2
    assert "rejeitada" in llm.calls[1][1]


def test_generate_gives_up(file_source, fake_llm_factory):
    llm = fake_llm_factory("não sei", "def (")
    result = generate_chart_code(llm, file_source, "arquivos", [("main", "vendas")], "vendas", "V")
    assert not result.ok and result.attempts == 2


def test_check_code_reports_sql_errors(valid_script):
    assert check_code(valid_script, "duckdb") == []
    bad = valid_script.replace("SELECT mes, SUM(valor) AS total FROM vendas GROUP BY mes ORDER BY mes", "DROP TABLE vendas")
    assert check_code(bad, "duckdb")[0].startswith("SQL:")


def test_system_prompt_mentions_theme_contrast():
    prompt = build_system_prompt("postgres")
    assert "tema claro ou escuro" in prompt
    assert "cor da fonte" in prompt
