"""Origem baseada em arquivos CSV/XLSX, consultada via DuckDB em memória."""

from __future__ import annotations

import re
from pathlib import Path

import duckdb
import pandas as pd

from src.config.settings import DataSourceConfig
from src.services.db_connections.base import ColumnInfo, DataSource
from src.services.sql_guard import DEFAULT_LIMIT, enforce_limit

SCHEMA = "main"
_EXTENSIONS = {"csv": (".csv",), "xlsx": (".xlsx", ".xlsm")}


def table_name(*parts: str) -> str:
    """Normaliza nomes de arquivo/aba para identificadores SQL simples."""
    name = "_".join(parts).lower()
    name = re.sub(r"[^a-z0-9_]+", "_", name).strip("_")
    if not name or name[0].isdigit():
        name = f"t_{name}"
    return name


def load_frames(cfg: DataSourceConfig) -> dict[str, pd.DataFrame]:
    if not cfg.path:
        raise ValueError("Informe o caminho do arquivo ou diretório.")
    base = Path(cfg.path)
    if not base.exists():
        raise FileNotFoundError(f"Caminho não encontrado: {base}")
    exts = _EXTENSIONS[cfg.type]
    files = sorted(p for p in base.iterdir() if p.suffix.lower() in exts) if base.is_dir() else [base]
    frames: dict[str, pd.DataFrame] = {}
    for file in files:
        if cfg.type == "csv":
            frames[table_name(file.stem)] = pd.read_csv(file, sep=None, engine="python")
        else:
            sheets = pd.read_excel(file, sheet_name=None)
            for sheet, df in sheets.items():
                key = table_name(sheet) if len(files) == 1 else table_name(file.stem, sheet)
                frames[key] = df
    if not frames:
        raise ValueError(f"Nenhum arquivo {'/'.join(exts)} encontrado em {base}.")
    return frames


class FileSource(DataSource):
    dialect = "duckdb"

    def __init__(self, cfg: DataSourceConfig) -> None:
        self.cfg = cfg
        self.conn = duckdb.connect(":memory:")
        for name, df in load_frames(cfg).items():
            self.conn.register("_incoming", df)
            self.conn.execute(f'CREATE TABLE "{name}" AS SELECT * FROM _incoming')
            self.conn.unregister("_incoming")
        # Impede que consultas leiam arquivos/URLs arbitrários (ex.: read_csv('/etc/passwd')).
        self.conn.execute("SET enable_external_access = false")
        self.conn.execute("SET lock_configuration = true")

    def test_connection(self) -> None:
        self.conn.execute("SELECT 1").fetchall()

    def list_schemas(self) -> list[str]:
        return [SCHEMA]

    def list_tables(self, schema: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ? ORDER BY 1",
            [schema],
        ).fetchall()
        return [r[0] for r in rows]

    def get_columns(self, table: str, schema: str) -> list[ColumnInfo]:
        rows = self.conn.execute(
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = ? AND table_name = ? ORDER BY ordinal_position",
            [schema, table],
        ).fetchall()
        return [ColumnInfo(name, dtype, nullable == "YES") for name, dtype, nullable in rows]

    def quote_table(self, table: str, schema: str) -> str:
        return '"{}"."{}"'.format(schema.replace('"', '""'), table.replace('"', '""'))

    def run_query(self, sql: str, limit: int | None = None) -> pd.DataFrame:
        safe_sql = enforce_limit(sql, self.dialect, limit or DEFAULT_LIMIT)
        return self.conn.execute(safe_sql).fetchdf()

    def close(self) -> None:
        self.conn.close()
