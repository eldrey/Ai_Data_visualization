"""Configuração da aplicação persistida em YAML (sem banco local)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

CONFIG_PATH = Path(os.environ.get("APP_CONFIG_PATH", "config/settings.yaml"))
SCRIPTS_DIR = Path(os.environ.get("DASHBOARD_SCRIPTS_DIR", "src/dashboards_scripts"))

_ENV_REF = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")

SourceType = Literal["postgres", "neon", "csv", "xlsx"]
LLMProvider = Literal["anthropic", "openai", "gemini"]

DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-opus-5-5",
    "openai": "gpt-5",
    "gemini": "gemini-2.5-pro",
}


def resolve_secret(value: str | None) -> str | None:
    """Resolve referências `${VAR}` para o valor da variável de ambiente."""
    if not value:
        return value
    match = _ENV_REF.match(value.strip())
    if match:
        return os.environ.get(match.group(1))
    return value


class DataSourceConfig(BaseModel):
    name: str
    type: SourceType
    host: str | None = None
    port: int = 5432
    database: str | None = None
    username: str | None = None
    password: str | None = None
    sslmode: str | None = None
    path: str | None = None

    @property
    def is_file(self) -> bool:
        return self.type in ("csv", "xlsx")


class LLMConfig(BaseModel):
    provider: LLMProvider = "anthropic"
    model: str = DEFAULT_MODELS["anthropic"]
    api_key: str | None = None
    temperature: float = 0.2  # ignorado pelo Claude (não suportado nos modelos atuais)
    max_tokens: int = 16000


DEFAULT_PANEL = "Principal"


class PanelConfig(BaseModel):
    """Um painel (dashboard) nomeado com os gráficos exibidos nele."""

    name: str
    selected_scripts: list[str] = Field(default_factory=list)
    columns: int = 2


class AppConfig(BaseModel):
    data_sources: list[DataSourceConfig] = Field(default_factory=list)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    panels: list[PanelConfig] = Field(default_factory=lambda: [PanelConfig(name=DEFAULT_PANEL)])

    @model_validator(mode="before")
    @classmethod
    def _migrate_single_dashboard(cls, data: object) -> object:
        """Converte o formato antigo (`dashboard:` único) em um painel 'Principal'."""
        if isinstance(data, dict) and "dashboard" in data:
            data = dict(data)
            legacy = data.pop("dashboard") or {}
            data.setdefault("panels", [{"name": DEFAULT_PANEL, **legacy}])
        return data

    @model_validator(mode="after")
    def _ensure_panel(self) -> "AppConfig":
        if not self.panels:
            self.panels = [PanelConfig(name=DEFAULT_PANEL)]
        return self

    def get_source(self, name: str) -> DataSourceConfig | None:
        return next((s for s in self.data_sources if s.name == name), None)

    def upsert_source(self, source: DataSourceConfig) -> None:
        self.data_sources = [s for s in self.data_sources if s.name != source.name]
        self.data_sources.append(source)

    def remove_source(self, name: str) -> None:
        self.data_sources = [s for s in self.data_sources if s.name != name]

    # Painéis ---------------------------------------------------------------

    @property
    def panel_names(self) -> list[str]:
        return [p.name for p in self.panels]

    def get_panel(self, name: str) -> PanelConfig | None:
        return next((p for p in self.panels if p.name == name), None)

    def _validate_panel_name(self, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("Informe um nome para o painel.")
        if self.get_panel(name):
            raise ValueError(f"Já existe um painel chamado '{name}'.")
        return name

    def add_panel(self, name: str) -> PanelConfig:
        panel = PanelConfig(name=self._validate_panel_name(name))
        self.panels.append(panel)
        return panel

    def rename_panel(self, old: str, new: str) -> PanelConfig:
        panel = self.get_panel(old)
        if panel is None:
            raise ValueError(f"Painel '{old}' não encontrado.")
        if new.strip() != old:
            panel.name = self._validate_panel_name(new)
        return panel

    def remove_panel(self, name: str) -> None:
        if len(self.panels) <= 1:
            raise ValueError("É preciso manter pelo menos um painel.")
        self.panels = [p for p in self.panels if p.name != name]

    def panels_with(self, slug: str) -> list[str]:
        return [p.name for p in self.panels if slug in p.selected_scripts]

    def add_script_to_panel(self, slug: str, panel_name: str) -> None:
        panel = self.get_panel(panel_name)
        if panel is None:
            raise ValueError(f"Painel '{panel_name}' não encontrado.")
        if slug not in panel.selected_scripts:
            panel.selected_scripts.append(slug)

    def remove_script_everywhere(self, slug: str) -> None:
        for panel in self.panels:
            panel.selected_scripts = [s for s in panel.selected_scripts if s != slug]


def load_config(path: Path | None = None) -> AppConfig:
    path = path or CONFIG_PATH
    if not path.exists():
        return AppConfig()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(data)


def save_config(config: AppConfig, path: Path | None = None) -> None:
    path = path or CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    data = config.model_dump(mode="json", exclude_none=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
