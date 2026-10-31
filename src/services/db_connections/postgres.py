"""Origem PostgreSQL (inclui Neon, que é Postgres com SSL obrigatório)."""

from __future__ import annotations

import pandas as pd
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import URL

from src.config.settings import DataSourceConfig, resolve_secret
from src.services.db_connections.base import ColumnInfo, DataSource
from src.services.sql_guard import DEFAULT_LIMIT, enforce_limit

SYSTEM_SCHEMAS = frozenset({"information_schema", "pg_catalog", "pg_toast"})


def build_url(cfg: DataSourceConfig) -> URL:
    return URL.create(
        "postgresql+psycopg",
        username=cfg.username,
        password=resolve_secret(cfg.password),
        host=cfg.host,
        port=cfg.port,
        database=cfg.database,
    )


def build_connect_args(cfg: DataSourceConfig) -> dict[str, object]:
    sslmode = cfg.sslmode or ("require" if cfg.type == "neon" else None)
    args: dict[str, object] = {"connect_timeout": 10}
    if sslmode:
        args["sslmode"] = sslmode
    return args


class PostgresSource(DataSource):
    dialect = "postgres"
    #: Executado no início de cada transação; funciona também atrás de poolers (Neon).
    readonly_statement: str | None = "SET TRANSACTION READ ONLY"

    def __init__(self, cfg: DataSourceConfig, engine: Engine | None = None) -> None:
        self.cfg = cfg
        self.engine = engine or create_engine(
            build_url(cfg), connect_args=build_connect_args(cfg), pool_pre_ping=True
        )

    def _read(self, sql: str) -> pd.DataFrame:
        with self.engine.connect() as conn:
            with conn.begin() as txn:
                if self.readonly_statement:
                    conn.execute(text(self.readonly_statement))
                df = pd.read_sql_query(text(sql), conn)
                txn.rollback()
        return df

    def test_connection(self) -> None:
        self._read("SELECT 1 AS ok")

    def list_schemas(self) -> list[str]:
        names = inspect(self.engine).get_schema_names()
        return [n for n in names if n not in SYSTEM_SCHEMAS and not n.startswith("pg_temp")]

    def list_tables(self, schema: str) -> list[str]:
        insp = inspect(self.engine)
        return sorted(insp.get_table_names(schema=schema) + insp.get_view_names(schema=schema))

    def get_columns(self, table: str, schema: str) -> list[ColumnInfo]:
        cols = inspect(self.engine).get_columns(table, schema=schema)
        return [ColumnInfo(c["name"], str(c["type"]), bool(c.get("nullable", True))) for c in cols]

    def quote_table(self, table: str, schema: str) -> str:
        prep = self.engine.dialect.identifier_preparer
        return f"{prep.quote(schema)}.{prep.quote(table)}"

    def run_query(self, sql: str, limit: int | None = None) -> pd.DataFrame:
        safe_sql = enforce_limit(sql, self.dialect, limit or DEFAULT_LIMIT)
        return self._read(safe_sql)

    def close(self) -> None:
        self.engine.dispose()
