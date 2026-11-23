from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from src.config import settings
from src.config.settings import DataSourceConfig
from src.services.db_connections.file_source import FileSource

EVALS_DIR = Path(__file__).parent / "evals"


# ---------------------------------------------------------------- avaliação da LLM (tests/evals)
# `pytest --eval dev|test` roda só os casos de avaliação; sem a opção, tests/evals não é coletado.
def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--eval",
        choices=("dev", "test"),
        default=None,
        help="Roda a avaliação da LLM com tests/evals/cases_<split>.yaml em vez dos testes unitários.",
    )
    parser.addoption(
        "--eval-output",
        default=None,
        help="Arquivo JSONL com um registro por caso (padrão: tests/evals/results/<split>_<data-hora>.jsonl).",
    )


RESULTS_PATH = pytest.StashKey[Path]()
RUN_ID = pytest.StashKey[str]()


def _eval_split(config: pytest.Config) -> str | None:
    return config.getoption("eval", default=None)


def pytest_configure(config: pytest.Config) -> None:
    if _eval_split(config):
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        output = config.getoption("eval_output") or EVALS_DIR / "results" / f"{_eval_split(config)}_{run_id}.jsonl"
        config.stash[RUN_ID] = run_id
        config.stash[RESULTS_PATH] = Path(output)
        config.option.verbose = max(config.option.verbose, 1)  # uma linha por caso
        # cobertura (e sua meta de 60%) só faz sentido para os testes unitários
        cov = config.pluginmanager.get_plugin("_cov")
        if cov is not None:
            cov.options.no_cov = True
            controller = getattr(cov, "cov_controller", None)
            if controller is not None and getattr(controller, "cov", None) is not None:
                controller.cov.stop()


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    in_evals = collection_path == EVALS_DIR or EVALS_DIR in collection_path.parents
    if _eval_split(config):
        if in_evals or collection_path in EVALS_DIR.parents:
            return None
        return True  # no modo eval, ignora os testes unitários
    return True if in_evals else None


WARNED = "warned"  # categoria das estatísticas para casos que passaram com warning


def _eval_warning(report) -> str | None:
    return next((value for name, value in getattr(report, "user_properties", []) if name == "eval_warning"), None)


def pytest_report_teststatus(report, config: pytest.Config):
    # Caso que passou só depois de reorganizar a referência (pivot): mostrado como WARNING, não conta como falha.
    if _eval_split(config) and report.when == "call" and report.passed and _eval_warning(report):
        return WARNED, "W", ("WARNING", {"yellow": True})
    return None


def pytest_runtest_logreport(report) -> None:
    """Grava uma linha no JSONL da rodada assim que cada caso termina (uma rodada interrompida não se perde)."""
    config = _current_config
    if config is None or not _eval_split(config):
        return
    setup_error = report.when == "setup" and report.failed
    if report.when != "call" and not setup_error:
        return
    record = next((v for k, v in report.user_properties if k == "eval_record"), None) or {
        "id": report.nodeid.rsplit("[", 1)[-1].split("-", 1)[0].rstrip("]")
    }
    if setup_error:
        status = "error"
    elif report.failed:
        status = "failed"
    else:
        status = "warning" if _eval_warning(report) else "passed"
    line = {
        "run_id": config.stash[RUN_ID],
        "split": _eval_split(config),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "passed": status in ("passed", "warning"),
        **record,
        "message": _eval_warning(report) if status == "warning" else (report.longreprtext or None),
    }
    path = config.stash[RESULTS_PATH]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")


_current_config: pytest.Config | None = None


@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart(session: pytest.Session) -> None:
    global _current_config  # pytest_runtest_logreport não recebe o config
    _current_config = session.config


def pytest_terminal_summary(terminalreporter, exitstatus: int, config: pytest.Config) -> None:
    split = _eval_split(config)
    if not split:
        return
    stats = terminalreporter.stats
    warned_reports = stats.get(WARNED, [])
    if warned_reports:
        terminalreporter.write_sep("=", "WARNINGS DA AVALIAÇÃO", yellow=True)
        for report in warned_reports:
            terminalreporter.write_sep("_", report.head_line or report.nodeid, yellow=True)
            terminalreporter.write_line(_eval_warning(report))
    passed = len([r for r in stats.get("passed", []) if r.when == "call"])
    warned = len(warned_reports)
    failed = len({r.nodeid for key in ("failed", "error") for r in stats.get(key, [])})
    total = terminalreporter._numcollected - len(stats.get("deselected", []))  # sem os excluídos por -k
    done = passed + warned + failed
    rate = passed / done * 100 if done else 0.0
    rate_warn = (passed + warned) / done * 100 if done else 0.0
    executed = done / total * 100 if total else 0.0
    terminalreporter.write_sep(
        "=",
        f"Avaliação {split}: {total} testes | {passed} passed | {warned} warning | {failed} failed | "
        f"{rate:.1f}% de acerto ({rate_warn:.1f}% com warnings) | {executed:.0f}% executado",
        bold=True,
        green=failed == 0 and warned == 0 and done > 0,
        yellow=failed == 0 and warned > 0,
        red=failed > 0,
    )
    _write_usage_summary(terminalreporter)
    results = config.stash.get(RESULTS_PATH, None)
    if results is not None and results.exists():
        terminalreporter.write_line(f"Resultados por caso: {results}")


def _fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _write_usage_summary(terminalreporter) -> None:
    """Soma os tokens que cada caso registrou em user_properties e estima o custo da rodada."""
    records = [
        value
        for key in ("passed", WARNED, "failed")
        for report in terminalreporter.stats.get(key, [])
        if report.when == "call"
        for name, value in report.user_properties
        if name == "llm_usage"
    ]
    if not records:
        return
    total = {k: sum(r[k] for r in records) for k in ("calls", "input", "output", "cache_read", "cache_write")}
    models = sorted({r["model"] for r in records})
    line = (
        f"Tokens: {_fmt_int(total['input'])} entrada | {_fmt_int(total['output'])} saída"
        + (f" | {_fmt_int(total['cache_read'] + total['cache_write'])} cache" if total["cache_read"] + total["cache_write"] else "")
        + f" | {total['calls']} chamadas em {len(records)} casos"
    )
    if all(r["cost"] is not None for r in records):
        cost = sum(r["cost"] for r in records)
        line += f" | custo estimado US$ {cost:.2f} (US$ {cost / len(records):.3f}/caso, {', '.join(models)})"
    else:
        line += f" | custo não estimado: sem preço para {', '.join(models)}"
    terminalreporter.write_sep("-", line)


VALID_SCRIPT = '''import pandas as pd
import plotly.express as px

METADATA = {"title": "Vendas por mês", "source": "arquivos"}

SQL = "SELECT mes, SUM(valor) AS total FROM vendas GROUP BY mes ORDER BY mes"

def build_chart(df):
    return px.bar(df, x="mes", y="total", title="Vendas")
'''


@pytest.fixture
def valid_script() -> str:
    return VALID_SCRIPT


@pytest.fixture
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redireciona config e scripts para um diretório temporário."""
    monkeypatch.setattr(settings, "CONFIG_PATH", tmp_path / "config" / "settings.yaml")
    monkeypatch.setattr(settings, "SCRIPTS_DIR", tmp_path / "scripts")
    return tmp_path


@pytest.fixture
def csv_dir(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    pd.DataFrame({"mes": [1, 1, 2, 3], "valor": [10, 5, 20, 30]}).to_csv(data / "vendas.csv", index=False)
    pd.DataFrame({"id": [1, 2], "nome": ["Ana", "Bia"]}).to_csv(data / "Clientes 2024.csv", index=False)
    return data


@pytest.fixture
def csv_config(csv_dir: Path) -> DataSourceConfig:
    return DataSourceConfig(name="arquivos", type="csv", path=str(csv_dir))


@pytest.fixture
def file_source(csv_config: DataSourceConfig):
    source = FileSource(csv_config)
    yield source
    source.close()


class FakeLLM:
    """LLM falsa que devolve respostas pré-definidas em sequência."""

    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.responses.pop(0)


@pytest.fixture
def fake_llm_factory():
    return FakeLLM
