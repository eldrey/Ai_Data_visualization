"""Cria a origem de dados adequada para cada configuração."""

from __future__ import annotations

from src.config.settings import DataSourceConfig
from src.services.db_connections.base import DataSource
from src.services.db_connections.file_source import FileSource
from src.services.db_connections.postgres import PostgresSource


def create_source(cfg: DataSourceConfig) -> DataSource:
    if cfg.type in ("postgres", "neon"):
        return PostgresSource(cfg)
    if cfg.type in ("csv", "xlsx"):
        return FileSource(cfg)
    raise ValueError(f"Tipo de origem não suportado: {cfg.type}")
