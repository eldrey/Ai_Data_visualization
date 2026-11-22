from __future__ import annotations

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


def _eval_split(config: pytest.Config) -> str | None:
    return config.getoption("eval", default=None)


def pytest_configure(config: pytest.Config) -> None:
    if _eval_split(config):
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


def pytest_terminal_summary(terminalreporter, exitstatus: int, config: pytest.Config) -> None:
    split = _eval_split(config)
    if not split:
        return
    stats = terminalreporter.stats
    passed = len([r for r in stats.get("passed", []) if r.when == "call"])
    failed = len({r.nodeid for key in ("failed", "error") for r in stats.get(key, [])})
    total = terminalreporter._numcollected - len(stats.get("deselected", []))  # sem os excluídos por -k
    done = passed + failed
    rate = passed / done * 100 if done else 0.0
    executed = done / total * 100 if total else 0.0
    terminalreporter.write_sep(
        "=",
        f"Avaliação {split}: {total} testes | {passed} passed | {failed} failed | "
        f"{rate:.1f}% de acerto | {executed:.0f}% executado",
        bold=True,
        green=failed == 0 and done > 0,
        red=failed > 0,
    )


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
