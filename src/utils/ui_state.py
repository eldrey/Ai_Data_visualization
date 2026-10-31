"""Helpers de estado compartilhados pelas páginas Streamlit."""

from __future__ import annotations

import streamlit as st

from src.config.settings import AppConfig, DataSourceConfig, load_config, save_config
from src.services.db_connections.base import DataSource
from src.services.db_connections.factory import create_source
from src.services.script_store import ScriptStore

_CONFIG_KEY = "app_config"


def get_config() -> AppConfig:
    if _CONFIG_KEY not in st.session_state:
        st.session_state[_CONFIG_KEY] = load_config()
    return st.session_state[_CONFIG_KEY]


def persist_config(config: AppConfig) -> None:
    save_config(config)
    st.session_state[_CONFIG_KEY] = config


@st.cache_resource(show_spinner=False)
def _cached_source(cfg_json: str) -> DataSource:
    return create_source(DataSourceConfig.model_validate_json(cfg_json))


def get_source(cfg: DataSourceConfig) -> DataSource:
    """Reaproveita conexões entre reruns; muda automaticamente se a configuração mudar."""
    return _cached_source(cfg.model_dump_json())


def clear_sources() -> None:
    _cached_source.clear()


def get_store() -> ScriptStore:
    return ScriptStore()


def source_names(config: AppConfig) -> list[str]:
    return [s.name for s in config.data_sources]
