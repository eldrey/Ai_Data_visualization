"""Avaliação da geração de gráficos pela LLM, executada pelo pytest.

Uso:
    uv run pytest --eval dev            # tests/evals/cases_dev.yaml
    uv run pytest --eval test           # tests/evals/cases_test.yaml
    uv run python tests/evals/evaluation_run.py dev|test   # atalho equivalente

Cada caso passa pelo mesmo fluxo da tela "Gerar gráfico": monta o prompt com as tabelas selecionadas,
chama a LLM configurada em config/settings.yaml (chaves via .env), valida o script e executa o SQL
contra os CSVs de tests/evals/data. Regras de correção: tests/evals/README.md.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import sqlglot
import yaml
from sqlglot import exp

ROOT = Path(__file__).resolve().parents[2]
EVALS = Path(__file__).resolve().parent
DATA_DIR = EVALS / "data"

if str(ROOT) not in sys.path:  # execução direta: python tests/evals/evaluation_run.py
    sys.path.insert(0, str(ROOT))

from src.config.settings import DataSourceConfig, load_config  # noqa: E402
from src.services.chart_generator import generate_chart_code  # noqa: E402
from src.services.db_connections.file_source import SCHEMA, FileSource  # noqa: E402
from src.services.script_runner import render_figure  # noqa: E402
from src.services.script_store import parse_script  # noqa: E402

SOURCE_NAME = "eval_cafeterias"
# tipos de gráfico aceitos para cada chart_type esperado
ACCEPTED_KINDS = {
    "bar": {"bar"},
    "line": {"line"},
    "area": {"area"},
    "scatter": {"scatter"},
    "pie": {"pie"},
    "histogram": {"histogram"},
    "heatmap": {"heatmap"},
    "treemap": {"treemap"},
    "table": {"table"},
    "indicator": {"indicator"},
}
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[ T]00:00:00)?$")


# ------------------------------------------------------------------ casos e fixtures
def load_cases(split: str) -> list[dict]:
    with open(EVALS / f"cases_{split}.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["cases"]


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "case" in metafunc.fixturenames:
        split = metafunc.config.getoption("eval") or "dev"
        cases = load_cases(split)
        metafunc.parametrize("case", cases, ids=[f"{c['id']}-{c['category']}" for c in cases])


@pytest.fixture(scope="session")
def source():
    src = FileSource(DataSourceConfig(name=SOURCE_NAME, type="csv", path=str(DATA_DIR)))
    yield src
    src.close()


@pytest.fixture(scope="session")
def llm():
    from dotenv import load_dotenv

    from src.services.llm_connections.factory import create_llm

    load_dotenv(ROOT / ".env")
    try:
        return create_llm(load_config().llm)
    except Exception as exc:  # noqa: BLE001 - sem LLM não há o que avaliar
        pytest.exit(f"LLM não configurada (config/settings.yaml + .env): {exc}", returncode=3)


@pytest.fixture(scope="session")
def snapshot(source) -> dict[str, tuple]:
    return table_fingerprint(source)


def table_fingerprint(source: FileSource) -> dict[str, tuple]:
    out = {}
    for t in source.list_tables(SCHEMA):
        out[t] = source.conn.execute(f'SELECT COUNT(*), SUM(hash(t)) FROM "{t}" t').fetchone()
    return out


# ------------------------------------------------------------------ comparação de resultados
def measure_columns(sql: str, df: pd.DataFrame) -> list[str]:
    """Colunas do SELECT externo com agregação; sem agregação, as colunas numéricas."""
    tree = sqlglot.parse_one(sql, read="duckdb")
    measures = [e.alias_or_name for e in tree.selects if any(isinstance(n, exp.AggFunc) for n in e.walk())]
    if not measures:
        measures = [c for c in df.columns if is_numeric(df[c])]
    return [c for c in measures if c in df.columns]


def is_numeric(s: pd.Series) -> bool:
    if pd.api.types.is_bool_dtype(s):
        return False
    if pd.api.types.is_numeric_dtype(s):
        return True
    vals = s.dropna()
    return len(vals) > 0 and all(isinstance(v, (int, float, np.number)) or type(v).__name__ == "Decimal" for v in vals)


def normalize(s: pd.Series) -> list:
    """Valores comparáveis: números como float; datas como texto, mês como AAAA-MM."""
    if is_numeric(s):
        return [None if pd.isna(v) else float(v) for v in s]
    vals = []
    for v in s:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            vals.append(None)
        elif hasattr(v, "strftime"):
            text = v.strftime("%Y-%m-%d %H:%M:%S")
            vals.append(text[:10] if text.endswith("00:00:00") else text)
        else:
            text = str(v).strip()
            vals.append(text[:10] if _DATE.match(text) else text.lower())
    dates = [v for v in vals if v is not None]
    if dates and all(isinstance(v, str) and _DATE.match(v) and v.endswith("-01") for v in dates):
        vals = [v[:7] if v else v for v in vals]  # 2024-01-01 → 2024-01
    return vals


def as_text(vals: list) -> list:
    return [None if v is None else (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)) for v in vals]


def _key(v):
    return (v is None, "" if v is None else (round(v, 2) if isinstance(v, float) else v))


def match_column(ref: list, gen: list) -> float | str | None:
    """Retorna o fator numérico (1, 100, 0.01), 'text' ou None se as colunas não casam."""
    if len(ref) != len(gen):
        return None
    if all(isinstance(v, float) or v is None for v in ref + gen):
        r = np.array(sorted(ref, key=_key), dtype=float)
        for factor in (1.0, 100.0, 0.01):
            g = np.array(sorted([None if v is None else v / factor for v in gen], key=_key), dtype=float)
            if np.allclose(r, g, rtol=1e-4, atol=0.011, equal_nan=True):
                return factor
        return None
    return "text" if sorted(as_text(ref), key=_key) == sorted(as_text(gen), key=_key) else None


def compare(ref_df: pd.DataFrame, gen_df: pd.DataFrame, ref_sql: str) -> str | None:
    """Compara o resultado gerado com o de referência; retorna o motivo da falha ou None."""
    return compare_frames(ref_df, gen_df, measure_columns(ref_sql, ref_df))


def compare_frames(ref_df: pd.DataFrame, gen_df: pd.DataFrame, measures: list[str]) -> str | None:
    if len(ref_df) != len(gen_df):
        return f"{len(gen_df)} linhas geradas, {len(ref_df)} esperadas"
    ref_cols = {c: normalize(ref_df[c]) for c in ref_df.columns}
    gen_cols = {c: normalize(gen_df[c]) for c in gen_df.columns}
    mapping: dict[str, tuple[str, float | str]] = {}
    for rc in sorted(ref_cols, key=lambda c: c not in measures):  # medidas primeiro
        for gc, gvals in gen_cols.items():
            if gc in {m[0] for m in mapping.values()}:
                continue
            how = match_column(ref_cols[rc], gvals)
            if how is not None:
                mapping[rc] = (gc, how)
                break
    missing = [m for m in measures if m not in mapping]
    if missing:
        return f"valores de {missing} não encontrados no resultado (colunas geradas: {list(gen_df.columns)})"

    def rows(cols: dict, pick) -> list[tuple]:
        return sorted(zip(*[pick(c) for c in mapping]), key=lambda r: tuple(_key(v) for v in r))

    ref_rows = rows(ref_cols, lambda c: ref_cols[c] if mapping[c][1] != "text" else as_text(ref_cols[c]))

    def gen_pick(c):
        gc, how = mapping[c]
        vals = gen_cols[gc]
        if how == "text":
            return as_text(vals)
        return [None if v is None else v / how for v in vals]

    gen_rows = rows(gen_cols, gen_pick)
    for r, g in zip(ref_rows, gen_rows):
        for a, b in zip(r, g):
            if isinstance(a, float) and isinstance(b, float):
                if not np.isclose(a, b, rtol=1e-4, atol=0.011):
                    return f"linhas não conferem: esperado {r}, gerado {g}"
            elif a != b:
                return f"linhas não conferem: esperado {r}, gerado {g}"
    return None


# ------------------------------------------------------------------ pivot (mesmos dados, outro formato)
MAX_PIVOT_VALUES = 12  # só vira coluna uma dimensão com poucos valores distintos


def pivot_variants(ref_df: pd.DataFrame, measures: list[str]) -> list[tuple[str, pd.DataFrame, list[str]]]:
    """Versões da referência com os mesmos dados reorganizados: (descrição, tabela, medidas).

    - formato largo (2+ medidas) -> longo: uma linha por dimensão e medida (unpivot);
    - formato longo -> largo: uma dimensão de poucos valores vira colunas (pivot).
    Variantes ambíguas (chaves duplicadas) são descartadas em vez de agregadas.
    """
    dims = [c for c in ref_df.columns if c not in measures]
    variants = []
    if len(measures) >= 2:
        long_df = ref_df.melt(id_vars=dims, value_vars=measures, var_name="_medida", value_name="_valor")
        variants.append((f"formato longo (unpivot de {', '.join(measures)})", long_df, ["_valor"]))
    for col in dims:
        if not 2 <= ref_df[col].nunique(dropna=False) <= MAX_PIVOT_VALUES:
            continue
        index = [c for c in dims if c != col]
        if ref_df.duplicated(index + [col]).any():
            continue
        base = ref_df if index else ref_df.assign(_linha=0)
        wide = base.pivot(index=index or ["_linha"], columns=col, values=measures)
        wide.columns = [str(v) if len(measures) == 1 else f"{m} {v}" for m, v in wide.columns]
        wide = wide.reset_index().drop(columns=["_linha"], errors="ignore")
        new_measures = [c for c in wide.columns if c not in index]
        variants.append((f"formato largo (pivot de {col})", wide, new_measures))
    return variants


def compare_reshaped(ref_df: pd.DataFrame, gen_df: pd.DataFrame, ref_sql: str) -> str | None:
    """Se a referência reorganizada bater com o resultado, retorna a descrição do formato."""
    for desc, variant, measures in pivot_variants(ref_df, measure_columns(ref_sql, ref_df)):
        if compare_frames(variant, gen_df, measures) is None:
            return desc
    return None


# ------------------------------------------------------------------ tipo de gráfico
def trace_kind(trace) -> str:
    t = trace.type
    if t in ("scatter", "scattergl"):
        if getattr(trace, "stackgroup", None) or getattr(trace, "fill", None) not in (None, "none"):
            return "area"
        # mode combina partes com "+": "markers+text" (pontos com rótulo) é dispersão, não linha.
        # Sem mode, o Plotly desenha linhas.
        parts = set((trace.mode or "lines").split("+"))
        return "line" if "lines" in parts else "scatter"
    return {"histogram2d": "heatmap", "densitymapbox": "heatmap"}.get(t, t)


# ------------------------------------------------------------------ custo
# US$ por milhão de tokens: (entrada, saída, leitura de cache). Escrita em cache = 1,25 x entrada.
# Preços da API da Anthropic (tabela de 2026-11-03); modelos fora da lista mostram só os tokens.
PRICES_PER_MTOK = {
    "claude-fable-5-2": (8.00, 40.00, 0.20),
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-opus-5": (5.00, 25.00, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00, 0.10),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
}


def usage_record(model: str, usage) -> dict:
    record = {
        "model": model,
        "calls": usage.calls,
        "input": usage.input_tokens,
        "output": usage.output_tokens,
        "cache_read": usage.cache_read_tokens,
        "cache_write": usage.cache_write_tokens,
        "cost": None,
    }
    price = PRICES_PER_MTOK.get(model)
    if price:
        inp, out, cache_read = price
        record["cost"] = (usage.input_tokens * inp + usage.output_tokens * out
                          + usage.cache_read_tokens * cache_read + usage.cache_write_tokens * inp * 1.25) / 1e6
    return record


# ------------------------------------------------------------------ teste
def test_case(case: dict, llm, source: FileSource, snapshot, request: pytest.FixtureRequest) -> None:
    before = llm.usage.snapshot()
    try:
        warning = _run_case(case, llm, source, snapshot)
    finally:  # registra o consumo mesmo quando o caso falha; o relatório final soma tudo
        request.node.user_properties.append(("llm_usage", usage_record(llm.cfg.model, llm.usage - before)))
    if warning:  # o conftest mostra o caso como WARNING em vez de PASSED
        request.node.user_properties.append(("eval_warning", warning))


def _run_case(case: dict, llm, source: FileSource, snapshot) -> str | None:
    """Executa o caso; falha com pytest.fail ou retorna o motivo de um warning (None = passou)."""
    tables = [(SCHEMA, t) for t in case["tables"]]
    result = generate_chart_code(llm, source, SOURCE_NAME, tables, case["request"], title=case["id"])

    if case["expected_behavior"] == "reject":
        # Escrita nunca pode chegar à origem: ou a geração é barrada, ou o script aceito é só leitura.
        if result.ok:
            source.run_query(parse_script(case["id"], result.code).sql)
        assert table_fingerprint(source) == snapshot, "os dados da origem foram alterados"
        return None

    if not result.ok:
        pytest.fail("script rejeitado: " + "; ".join(result.errors), pytrace=False)
    sql = parse_script(case["id"], result.code).sql
    try:
        gen_df = source.run_query(sql)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"SQL gerado falhou: {exc}\n{sql}", pytrace=False)
    ref_df = source.run_query(case["reference_sql"])
    warning = None
    problem = compare(ref_df, gen_df, case["reference_sql"])
    if problem:
        reshaped = compare_reshaped(ref_df, gen_df, case["reference_sql"])
        if not reshaped:
            pytest.fail(f"resultado diferente do esperado: {problem}\nSQL gerado:\n{sql}", pytrace=False)
        warning = f"mesmos dados em outro formato: bate com a referência em {reshaped}\nSQL gerado:\n{sql}"

    try:
        fig = render_figure(result.code, gen_df)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"build_chart falhou: {exc}", pytrace=False)
    kinds = {trace_kind(t) for t in fig.data}
    expected = case["chart_type"] if isinstance(case["chart_type"], list) else [case["chart_type"]]
    if not kinds & set().union(*(ACCEPTED_KINDS[t] for t in expected)):
        # o tipo vem do build_chart, então mostra o script inteiro (SQL + build_chart), não só o SQL
        pytest.fail(f"tipo de gráfico {sorted(kinds)}, esperado {' ou '.join(expected)}\n"
                    f"Script gerado:\n{result.code}", pytrace=False)
    return warning


if __name__ == "__main__":
    split = sys.argv[1] if len(sys.argv) > 1 else ""
    if split not in ("dev", "test"):
        sys.exit("uso: python tests/evals/evaluation_run.py dev|test [opções do pytest]")
    sys.exit(pytest.main([str(Path(__file__)), "--eval", split, "--no-cov", "-p", "no:cacheprovider", *sys.argv[2:]],
                         plugins=[]))
