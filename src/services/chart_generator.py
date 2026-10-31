"""Gera scripts de gráfico a partir de linguagem natural usando a LLM configurada."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.services.code_validator import ALLOWED_IMPORTS, validate_script
from src.services.db_connections.base import DataSource
from src.services.llm_connections.base import LLMClient
from src.services.script_store import parse_script, set_metadata
from src.services.sql_guard import UnsafeQueryError, validate_readonly
from src.utils.code_extract import extract_python_code

SAMPLE_ROWS = 5

SYSTEM_PROMPT = """Você é um especialista em análise de dados e visualização com Plotly.
Gere UM script Python que siga exatamente este contrato:

```python
import pandas as pd
import plotly.express as px

SQL = \"\"\"<uma única consulta SELECT no dialeto {dialect}>\"\"\"

def build_chart(df: pd.DataFrame):
    # df contém o resultado de SQL
    fig = px.bar(df, x="...", y="...")
    return fig
```

Regras:
- `SQL` deve ser uma única consulta SELECT (ou WITH ... SELECT), somente leitura, no dialeto {dialect}.
  Faça agregações no SQL sempre que possível e use os nomes de tabela exatamente como fornecidos.
- `build_chart(df)` recebe o DataFrame resultante e retorna uma figura Plotly (plotly.graph_objects.Figure).
- Imports permitidos apenas: {allowed}.
- Proibido: acesso a arquivos, rede, os/sys/subprocess, exec/eval/open, atributos dunder.
- Não defina METADATA; ele é adicionado pela aplicação.
- Inclua título e rótulos de eixos legíveis em português.
- O gráfico é exibido num app que pode estar em tema claro ou escuro: não defina paper_bgcolor/plot_bgcolor nem template.
- Se definir qualquer cor de preenchimento (ex.: header/cells de go.Table), defina também a cor da fonte com alto contraste
  (fundo claro → fonte escura como "#111827"; fundo escuro → fonte clara como "#f9fafb").
- Responda apenas com o bloco de código ```python```.
"""


@dataclass
class GenerationResult:
    code: str
    errors: list[str] = field(default_factory=list)
    attempts: int = 1

    @property
    def ok(self) -> bool:
        return not self.errors


def build_system_prompt(dialect: str) -> str:
    allowed = ", ".join(sorted(ALLOWED_IMPORTS - {"__future__"}))
    return SYSTEM_PROMPT.format(dialect=dialect, allowed=allowed)


def describe_tables(source: DataSource, tables: list[tuple[str, str]]) -> str:
    parts = []
    for schema, table in tables:
        qualified = source.quote_table(table, schema)
        columns = source.get_columns(table, schema)
        cols = "\n".join(f"  - {c.name}: {c.type}" for c in columns)
        try:
            sample = source.preview(table, schema, limit=SAMPLE_ROWS).to_csv(index=False)
        except Exception as exc:  # noqa: BLE001 - amostra é opcional
            sample = f"(amostra indisponível: {exc})"
        parts.append(f"Tabela {qualified}\nColunas:\n{cols}\nAmostra (CSV):\n{sample}")
    return "\n\n".join(parts)


def build_user_prompt(source: DataSource, tables: list[tuple[str, str]], request: str) -> str:
    return f"{describe_tables(source, tables)}\n\nPedido do usuário:\n{request.strip()}"


def check_code(code: str, dialect: str) -> list[str]:
    errors = validate_script(code)
    if errors:
        return errors
    script = parse_script("generated", code)
    try:
        validate_readonly(script.sql, dialect)
    except UnsafeQueryError as exc:
        return [f"SQL: {exc}"]
    return []


def generate_chart_code(
    llm: LLMClient,
    source: DataSource,
    source_name: str,
    tables: list[tuple[str, str]],
    request: str,
    title: str,
    max_retries: int = 1,
) -> GenerationResult:
    system = build_system_prompt(source.dialect)
    user = build_user_prompt(source, tables, request)
    metadata = {
        "title": title,
        "source": source_name,
        "prompt": request.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    prompt = user
    code, errors = "", []
    for attempt in range(1, max_retries + 2):
        raw = llm.generate(system, prompt)
        code = extract_python_code(raw)
        try:
            code = set_metadata(code, metadata)
        except SyntaxError:
            pass
        errors = check_code(code, source.dialect)
        if not errors:
            return GenerationResult(code=code, attempts=attempt)
        prompt = (
            f"{user}\n\nSua resposta anterior foi rejeitada pelos seguintes motivos:\n- "
            + "\n- ".join(errors)
            + f"\n\nCódigo anterior:\n```python\n{code}```\nCorrija e responda novamente."
        )
    return GenerationResult(code=code, errors=errors, attempts=max_retries + 1)
