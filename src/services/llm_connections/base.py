"""Interface comum para provedores de LLM."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.config.settings import LLMConfig, resolve_secret


class LLMError(RuntimeError):
    """Falha ao obter uma resposta utilizável da LLM."""


class LLMClient(ABC):
    def __init__(self, cfg: LLMConfig) -> None:
        self.cfg = cfg
        self.api_key = resolve_secret(cfg.api_key)
        if not self.api_key:
            raise LLMError(f"Chave de API não configurada para '{cfg.provider}'.")

    @abstractmethod
    def generate(self, system: str, user: str) -> str:
        """Retorna o texto gerado pelo modelo."""
