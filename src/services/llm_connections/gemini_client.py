"""Cliente Google Gemini."""

from __future__ import annotations

from google import genai
from google.genai import types

from src.config.settings import LLMConfig
from src.services.llm_connections.base import LLMClient, LLMError


class GeminiClient(LLMClient):
    def __init__(self, cfg: LLMConfig, client: genai.Client | None = None) -> None:
        super().__init__(cfg)
        self.client = client or genai.Client(api_key=self.api_key)

    def generate(self, system: str, user: str) -> str:
        response = self.client.models.generate_content(
            model=self.cfg.model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=self.cfg.temperature,
                max_output_tokens=self.cfg.max_tokens,
            ),
        )
        text = response.text
        if not text:
            raise LLMError("Resposta vazia do Gemini.")
        return text
