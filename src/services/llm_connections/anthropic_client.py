"""Cliente Claude (Anthropic)."""

from __future__ import annotations

import anthropic

from src.config.settings import LLMConfig
from src.services.llm_connections.base import LLMClient, LLMError

# Modelos que aceitam o fallback automático do servidor em caso de recusa.
FALLBACK_MODELS = frozenset({"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"})
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicClient(LLMClient):
    def __init__(self, cfg: LLMConfig, client: anthropic.Anthropic | None = None) -> None:
        super().__init__(cfg)
        self.client = client or anthropic.Anthropic(api_key=self.api_key)

    def generate(self, system: str, user: str) -> str:
        # Modelos Claude atuais não aceitam temperature; a profundidade é controlada por effort.
        params = dict(
            model=self.cfg.model,
            max_tokens=self.cfg.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if self.cfg.model in FALLBACK_MODELS:
            response = self.client.beta.messages.create(
                **params, betas=[FALLBACK_BETA], fallbacks="default"
            )
        else:
            response = self.client.messages.create(**params)
        if response.stop_reason == "refusal":
            raise LLMError("O modelo recusou a solicitação.")
        text = "".join(block.text for block in response.content if block.type == "text")
        if not text:
            raise LLMError("Resposta vazia do Claude.")
        return text
