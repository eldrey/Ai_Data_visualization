"""Extrai blocos de código da resposta de uma LLM."""

from __future__ import annotations

import re

_FENCE = re.compile(r"```(?:python|py)?[ \t]*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_python_code(text: str) -> str:
    """Retorna o maior bloco ```python``` da resposta ou o texto inteiro se não houver bloco."""
    blocks = _FENCE.findall(text or "")
    if blocks:
        return max(blocks, key=len).strip() + "\n"
    return (text or "").strip() + "\n"
