"""Interface comum para origens de dados somente leitura."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd

PREVIEW_ROWS = 100


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    type: str
    nullable: bool = True


class DataSource(ABC):
    """Origem de dados que expõe schemas, tabelas e consultas SELECT."""

    #: Dialeto sqlglot usado para validar as consultas desta origem.
    dialect: str = "postgres"

    @abstractmethod
    def test_connection(self) -> None:
        """Lança exceção se a origem não estiver acessível."""

    @abstractmethod
    def list_schemas(self) -> list[str]: ...

    @abstractmethod
    def list_tables(self, schema: str) -> list[str]: ...

    @abstractmethod
    def get_columns(self, table: str, schema: str) -> list[ColumnInfo]: ...

    @abstractmethod
    def quote_table(self, table: str, schema: str) -> str:
        """Retorna o nome qualificado e escapado da tabela."""

    @abstractmethod
    def run_query(self, sql: str, limit: int | None = None) -> pd.DataFrame:
        """Executa uma consulta validada como somente leitura."""

    def preview(self, table: str, schema: str, limit: int = PREVIEW_ROWS) -> pd.DataFrame:
        return self.run_query(f"SELECT * FROM {self.quote_table(table, schema)}", limit=limit)

    def close(self) -> None:  # pragma: no cover - implementação opcional
        """Libera recursos da conexão."""
