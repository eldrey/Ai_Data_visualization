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


def test_anthropic_records_usage(mocker):
    sdk = mocker.MagicMock()
    usage = SimpleNamespace(input_tokens=100, output_tokens=40, cache_read_input_tokens=7,
                            cache_creation_input_tokens=None)
    sdk.beta.messages.create.return_value = SimpleNamespace(stop_reason="end_turn", content=[text_block("ok")],
                                                            usage=usage)
    client = AnthropicClient(LLMConfig(api_key="k"), client=sdk)
    client.generate("s", "u")
    client.generate("s", "u")
    u = client.usage
    assert (u.calls, u.input_tokens, u.output_tokens, u.cache_read_tokens, u.cache_write_tokens) == (2, 200, 80, 14, 0)


def test_anthropic_records_usage_on_refusal(mocker):
    sdk = mocker.MagicMock()
    sdk.beta.messages.create.return_value = SimpleNamespace(
        stop_reason="refusal", content=[], usage=SimpleNamespace(input_tokens=50, output_tokens=3)
    )
    client = AnthropicClient(LLMConfig(api_key="k"), client=sdk)
    with pytest.raises(LLMError):
        client.generate("s", "u")
    assert (client.usage.input_tokens, client.usage.output_tokens) == (50, 3)


def test_usage_without_sdk_counts(mocker):
    sdk = mocker.MagicMock()
    sdk.messages.create.return_value = SimpleNamespace(stop_reason="end_turn", content=[text_block("x")])
    client = AnthropicClient(LLMConfig(api_key="k", model="claude-haiku-5-5"), client=sdk)
    before = client.usage.snapshot()
    client.generate("s", "u")
    diff = client.usage - before
    assert (diff.calls, diff.input_tokens, diff.output_tokens) == (1, 0, 0)


def test_openai_records_usage(mocker):
    sdk = mocker.MagicMock()
    usage = SimpleNamespace(input_tokens=120, output_tokens=30, input_tokens_details=SimpleNamespace(cached_tokens=20))
    sdk.responses.create.return_value = SimpleNamespace(output_text="r", usage=usage)
    client = OpenAIClient(LLMConfig(provider="openai", api_key="k"), client=sdk)
    client.generate("s", "u")
    assert (client.usage.input_tokens, client.usage.output_tokens, client.usage.cache_read_tokens) == (100, 30, 20)


def test_gemini_records_usage(mocker):
    sdk = mocker.MagicMock()
    meta = SimpleNamespace(prompt_token_count=90, candidates_token_count=25, thoughts_token_count=15,
                           cached_content_token_count=10)
    sdk.models.generate_content.return_value = SimpleNamespace(text="oi", usage_metadata=meta)
    client = GeminiClient(LLMConfig(provider="gemini", api_key="k"), client=sdk)
    client.generate("s", "u")
    assert (client.usage.input_tokens, client.usage.output_tokens, client.usage.cache_read_tokens) == (80, 40, 10)


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
