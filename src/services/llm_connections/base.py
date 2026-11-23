"""Interface comum para provedores de LLM."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, replace

from src.config.settings import LLMConfig, resolve_secret


class LLMError(RuntimeError):
    """Falha ao obter uma resposta utilizável da LLM."""


def as_count(value: object) -> int:
    """Contagem de tokens informada pelo SDK; ausente ou inválida vira 0."""
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


@dataclass
class TokenUsage:
    """Tokens acumulados pelo cliente desde a criação (todas as chamadas)."""

    calls: int = 0
    input_tokens: int = 0  # entrada sem cache
    output_tokens: int = 0  # inclui tokens de raciocínio, cobrados como saída
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def snapshot(self) -> "TokenUsage":
        return replace(self)

    def __sub__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            self.calls - other.calls,
            self.input_tokens - other.input_tokens,
            self.output_tokens - other.output_tokens,
            self.cache_read_tokens - other.cache_read_tokens,
            self.cache_write_tokens - other.cache_write_tokens,
        )


class LLMClient(ABC):
    def __init__(self, cfg: LLMConfig) -> None:
        self.cfg = cfg
        self.api_key = resolve_secret(cfg.api_key)
        if not self.api_key:
            raise LLMError(f"Chave de API não configurada para '{cfg.provider}'.")
        self.usage = TokenUsage()

    def _record_usage(self, input_tokens: object = 0, output_tokens: object = 0,
                      cache_read: object = 0, cache_write: object = 0) -> None:
        self.usage.calls += 1
        self.usage.input_tokens += as_count(input_tokens)
        self.usage.output_tokens += as_count(output_tokens)
        self.usage.cache_read_tokens += as_count(cache_read)
        self.usage.cache_write_tokens += as_count(cache_write)

    @abstractmethod
    def generate(self, system: str, user: str) -> str:
        """Retorna o texto gerado pelo modelo."""
