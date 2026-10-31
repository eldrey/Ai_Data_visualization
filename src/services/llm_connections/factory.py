"""Cria o cliente de LLM conforme o provedor configurado."""

from __future__ import annotations

from src.config.settings import LLMConfig
from src.services.llm_connections.anthropic_client import AnthropicClient
from src.services.llm_connections.base import LLMClient
from src.services.llm_connections.gemini_client import GeminiClient
from src.services.llm_connections.openai_client import OpenAIClient

_PROVIDERS: dict[str, type[LLMClient]] = {
    "anthropic": AnthropicClient,
    "openai": OpenAIClient,
    "gemini": GeminiClient,
}


def create_llm(cfg: LLMConfig) -> LLMClient:
    try:
        return _PROVIDERS[cfg.provider](cfg)
    except KeyError:
        raise ValueError(f"Provedor de LLM não suportado: {cfg.provider}") from None
