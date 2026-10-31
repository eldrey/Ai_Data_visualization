"""Configuração do provedor de LLM."""

import streamlit as st

from src.config.settings import DEFAULT_MODELS, LLMConfig
from src.utils.ui_state import get_config, persist_config

PROVIDERS = {"anthropic": "Claude (Anthropic)", "openai": "OpenAI", "gemini": "Google Gemini"}

st.title("🤖 Configuração da LLM")
st.caption("A chave pode ser informada como ${ANTHROPIC_API_KEY}, ${OPENAI_API_KEY} ou ${GEMINI_API_KEY} para ler do .env.")

config = get_config()
current = config.llm

provider = st.selectbox(
    "Provedor", list(PROVIDERS), index=list(PROVIDERS).index(current.provider), format_func=PROVIDERS.get
)
with st.form("llm_form"):
    default_model = current.model if provider == current.provider else DEFAULT_MODELS[provider]
    model = st.text_input("Modelo", value=default_model)
    api_key = st.text_input(
        "Chave de API",
        value=(current.api_key or "") if provider == current.provider else "",
        type="password",
    )
    temperature = st.slider(
        "Temperatura", 0.0, 1.0, current.temperature, 0.05,
        help="Usada pelo Gemini. Claude e modelos de raciocínio da OpenAI ignoram este parâmetro.",
    )
    max_tokens = st.number_input("Máx. tokens de saída", 1024, 64000, current.max_tokens, 1024)
    c1, c2 = st.columns(2)
    save = c1.form_submit_button("Salvar", type="primary")
    test = c2.form_submit_button("Testar")

if save or test:
    llm_cfg = LLMConfig(
        provider=provider, model=model.strip(), api_key=api_key or None,
        temperature=temperature, max_tokens=int(max_tokens),
    )
    if save:
        config.llm = llm_cfg
        persist_config(config)
        st.success("Configuração salva.")
    if test:
        from src.services.llm_connections.factory import create_llm

        try:
            with st.spinner("Consultando modelo..."):
                reply = create_llm(llm_cfg).generate("Responda apenas com a palavra OK.", "ping")
            st.success(f"Resposta: {reply.strip()[:200]}")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Falha: {exc}")
