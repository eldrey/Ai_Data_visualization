from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.config import settings
from src.config.settings import DataSourceConfig
from src.services.db_connections.file_source import FileSource

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
