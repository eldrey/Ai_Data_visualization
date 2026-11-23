"""Cliente OpenAI (Responses API)."""

from __future__ import annotations

import openai

from src.config.settings import LLMConfig
from src.services.llm_connections.base import LLMClient, LLMError, as_count


class OpenAIClient(LLMClient):
    def __init__(self, cfg: LLMConfig, client: openai.OpenAI | None = None) -> None:
        super().__init__(cfg)
        self.client = client or openai.OpenAI(api_key=self.api_key)

    def generate(self, system: str, user: str) -> str:
        response = self.client.responses.create(
            model=self.cfg.model,
            instructions=system,
            input=user,
            max_output_tokens=self.cfg.max_tokens,
        )
        usage = getattr(response, "usage", None)
        cached = as_count(getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0))
        # Na OpenAI, input_tokens já inclui os tokens lidos do cache.
        self._record_usage(as_count(getattr(usage, "input_tokens", 0)) - cached,
                           getattr(usage, "output_tokens", 0), cached)
        text = response.output_text
        if not text:
            raise LLMError("Resposta vazia da OpenAI.")
        return text
