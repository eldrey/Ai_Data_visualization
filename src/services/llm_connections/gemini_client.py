"""Cliente Google Gemini."""

from __future__ import annotations

from google import genai
from google.genai import types

from src.config.settings import LLMConfig
from src.services.llm_connections.base import LLMClient, LLMError, as_count


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
        meta = getattr(response, "usage_metadata", None)
        cached = as_count(getattr(meta, "cached_content_token_count", 0))
        # prompt_token_count inclui o cache; tokens de raciocínio são cobrados como saída.
        self._record_usage(
            as_count(getattr(meta, "prompt_token_count", 0)) - cached,
            as_count(getattr(meta, "candidates_token_count", 0)) + as_count(getattr(meta, "thoughts_token_count", 0)),
            cached,
        )
        text = response.text
        if not text:
            raise LLMError("Resposta vazia do Gemini.")
        return text
