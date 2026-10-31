from types import SimpleNamespace

import pytest

from src.config.settings import LLMConfig
from src.services.llm_connections.anthropic_client import FALLBACK_BETA, AnthropicClient
from src.services.llm_connections.base import LLMError
from src.services.llm_connections.factory import create_llm
from src.services.llm_connections.gemini_client import GeminiClient
from src.services.llm_connections.openai_client import OpenAIClient


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("NOPE", raising=False)
    with pytest.raises(LLMError, match="Chave"):
        AnthropicClient(LLMConfig(api_key="${NOPE}"), client=object())


def test_anthropic_uses_fallback_for_supported_models(mocker):
    sdk = mocker.MagicMock()
    sdk.beta.messages.create.return_value = SimpleNamespace(
        stop_reason="end_turn", content=[SimpleNamespace(type="thinking"), text_block("ok")]
    )
    client = AnthropicClient(LLMConfig(api_key="k", model="claude-opus-5-5"), client=sdk)
    assert client.generate("sys", "user") == "ok"
    kwargs = sdk.beta.messages.create.call_args.kwargs
    assert kwargs["system"] == "sys"
    assert kwargs["betas"] == [FALLBACK_BETA]
    assert kwargs["fallbacks"] == "default"
    assert "temperature" not in kwargs


def test_anthropic_plain_call_for_other_models(mocker):
    sdk = mocker.MagicMock()
    sdk.messages.create.return_value = SimpleNamespace(stop_reason="end_turn", content=[text_block("x")])
    client = AnthropicClient(LLMConfig(api_key="k", model="claude-haiku-5-5"), client=sdk)
    assert client.generate("s", "u") == "x"
    sdk.beta.messages.create.assert_not_called()


@pytest.mark.parametrize(
    "response, message",
    [
        (SimpleNamespace(stop_reason="refusal", content=[]), "recusou"),
        (SimpleNamespace(stop_reason="end_turn", content=[]), "vazia"),
    ],
)
def test_anthropic_errors(mocker, response, message):
    sdk = mocker.MagicMock()
    sdk.beta.messages.create.return_value = response
    with pytest.raises(LLMError, match=message):
        AnthropicClient(LLMConfig(api_key="k"), client=sdk).generate("s", "u")


def test_openai(mocker):
    sdk = mocker.MagicMock()
    sdk.responses.create.return_value = SimpleNamespace(output_text="resposta")
    client = OpenAIClient(LLMConfig(provider="openai", model="gpt-x", api_key="k"), client=sdk)
    assert client.generate("sys", "user") == "resposta"
    kwargs = sdk.responses.create.call_args.kwargs
    assert kwargs["instructions"] == "sys" and kwargs["input"] == "user"


def test_openai_empty(mocker):
    sdk = mocker.MagicMock()
    sdk.responses.create.return_value = SimpleNamespace(output_text="")
    with pytest.raises(LLMError):
        OpenAIClient(LLMConfig(provider="openai", api_key="k"), client=sdk).generate("s", "u")


def test_gemini(mocker):
    sdk = mocker.MagicMock()
    sdk.models.generate_content.return_value = SimpleNamespace(text="oi")
    client = GeminiClient(LLMConfig(provider="gemini", model="g", api_key="k", temperature=0.5), client=sdk)
    assert client.generate("sys", "user") == "oi"
    kwargs = sdk.models.generate_content.call_args.kwargs
    assert kwargs["config"].system_instruction == "sys"
    assert kwargs["config"].temperature == 0.5


def test_gemini_empty(mocker):
    sdk = mocker.MagicMock()
    sdk.models.generate_content.return_value = SimpleNamespace(text=None)
    with pytest.raises(LLMError):
        GeminiClient(LLMConfig(provider="gemini", api_key="k"), client=sdk).generate("s", "u")


@pytest.mark.parametrize(
    "provider, cls",
    [("anthropic", AnthropicClient), ("openai", OpenAIClient), ("gemini", GeminiClient)],
)
def test_factory(provider, cls):
    assert isinstance(create_llm(LLMConfig(provider=provider, api_key="k")), cls)


def test_factory_unknown():
    cfg = LLMConfig(api_key="k").model_copy(update={"provider": "outro"})
    with pytest.raises(ValueError):
        create_llm(cfg)
