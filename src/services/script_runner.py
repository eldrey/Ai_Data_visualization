"""Executa scripts de gráfico: consulta somente leitura + build_chart em subprocesso."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import plotly.io as pio
from plotly.graph_objects import Figure

from src.services.code_validator import validate_script
from src.services.figure_style import ensure_readable
from src.services.db_connections.base import DataSource
from src.services.script_store import ChartScript, ScriptError, parse_script

RUNNER = Path(__file__).resolve().parent.parent / "utils" / "runner_entry.py"
DEFAULT_TIMEOUT = 30


def _sandbox_env(workdir: str) -> dict[str, str]:
    # Sem herdar o ambiente: o script não deve enxergar chaves de API ou senhas.
    return {"PATH": os.environ.get("PATH", ""), "HOME": workdir, "MPLCONFIGDIR": workdir}


def render_figure(code: str, df, timeout: int = DEFAULT_TIMEOUT) -> Figure:
    """Valida o código e executa `build_chart(df)` num subprocesso isolado."""
    errors = validate_script(code)
    if errors:
        raise ScriptError("Script inválido:\n- " + "\n- ".join(errors))
    with tempfile.TemporaryDirectory(prefix="chart_") as tmp:
        script_path = Path(tmp, "script.py")
        data_path = Path(tmp, "data.pkl")
        output_path = Path(tmp, "figure.json")
        script_path.write_text(code, encoding="utf-8")
        df.to_pickle(data_path)
        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(RUNNER), str(script_path), str(data_path), str(output_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmp,
                env=_sandbox_env(tmp),
            )
        except subprocess.TimeoutExpired as exc:
            raise ScriptError(f"Tempo limite de {timeout}s excedido ao gerar o gráfico.") from exc
        if proc.returncode != 0:
            raise ScriptError(f"Erro ao executar o script: {proc.stderr.strip()[-2000:]}")
        return ensure_readable(pio.from_json(output_path.read_text(encoding="utf-8")))


def run_script(script: ChartScript, source: DataSource, timeout: int = DEFAULT_TIMEOUT) -> Figure:
    if not script.sql:
        raise ScriptError(f"O script '{script.slug}' não define SQL.")
    df = source.run_query(script.sql)
    return render_figure(script.code, df, timeout=timeout)


def run_code(code: str, source: DataSource, timeout: int = DEFAULT_TIMEOUT) -> Figure:
    """Atalho para pré-visualizar um código ainda não salvo."""
    return run_script(parse_script("preview", code), source, timeout=timeout)
