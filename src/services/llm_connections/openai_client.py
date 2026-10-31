"""Cliente OpenAI (Responses API)."""

from __future__ import annotations

import openai

from src.config.settings import LLMConfig
from src.services.llm_connections.base import LLMClient, LLMError


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
        text = response.output_text
        if not text:
            raise LLMError("Resposta vazia da OpenAI.")
        return text
