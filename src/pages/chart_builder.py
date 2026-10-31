"""Geração de gráficos a partir de linguagem natural."""

import streamlit as st

from src.services.chart_generator import check_code, generate_chart_code
from src.services.script_runner import run_code
from src.services.script_store import ScriptError, slugify
from src.utils.ui_state import get_config, get_source, get_store, persist_config, source_names

NO_PANEL = "(não adicionar a um painel)"

st.title("✨ Gerar gráfico")

config = get_config()
names = source_names(config)
if not names:
    st.info("Cadastre uma origem de dados primeiro.")
    st.stop()

source_name = st.selectbox("Origem", names)
try:
    source = get_source(config.get_source(source_name))
    options = [(s, t) for s in source.list_schemas() for t in source.list_tables(s)]
except Exception as exc:  # noqa: BLE001
    st.error(f"Não foi possível conectar: {exc}")
    st.stop()

tables = st.multiselect("Tabelas usadas no gráfico", options, format_func=lambda o: f"{o[0]}.{o[1]}")
title = st.text_input("Título do gráfico")
request = st.text_area(
    "Descreva o gráfico", placeholder="Ex.: total de vendas por mês em 2024, em barras, separado por região"
)

if st.button("Gerar com a LLM", type="primary", disabled=not (tables and title and request)):
    from src.services.llm_connections.factory import create_llm

    try:
        with st.spinner("Gerando código..."):
            result = generate_chart_code(create_llm(config.llm), source, source_name, tables, request, title)
        st.session_state["generated_code"] = result.code
        st.session_state["generated_title"] = title
        # Widgets com key ignoram `value=` após o primeiro render: atualiza o estado diretamente.
        st.session_state["code_editor"] = result.code
        st.session_state.pop("preview", None)
        if result.errors:
            st.warning("O código gerado ainda tem problemas:\n- " + "\n- ".join(result.errors))
    except Exception as exc:  # noqa: BLE001
        st.error(f"Falha ao gerar: {exc}")

code = st.session_state.get("generated_code")
if code:
    st.subheader("Código gerado")
    st.session_state.setdefault("code_editor", code)
    edited = st.text_area("Revise/edite antes de salvar", height=380, key="code_editor")
    errors = check_code(edited, source.dialect)
    if errors:
        st.error("Validação:\n- " + "\n- ".join(errors))
    c1, c2 = st.columns(2)
    if c1.button("Pré-visualizar", disabled=bool(errors)):
        try:
            with st.spinner("Executando..."):
                st.session_state["preview"] = (edited, run_code(edited, source))
        except Exception as exc:  # noqa: BLE001
            st.session_state.pop("preview", None)
            st.error(str(exc))
    preview = st.session_state.get("preview")
    # Só exibe a pré-visualização se ela corresponde ao código atual do editor.
    if preview and preview[0] == edited:
        st.plotly_chart(preview[1], width="stretch")
    slug = slugify(st.session_state.get("generated_title", "grafico"))
    panel_options = [*config.panel_names, NO_PANEL]
    last_panel = st.session_state.get("panel_selector")
    target_panel = st.selectbox(
        "Adicionar ao painel",
        panel_options,
        index=panel_options.index(last_panel) if last_panel in panel_options else 0,
    )
    overwrite = st.checkbox(f"Sobrescrever se '{slug}' já existir")
    if c2.button("Salvar", disabled=bool(errors)):
        try:
            get_store().save(slug, edited, overwrite=overwrite)
            message = f"Salvo em dashboards_scripts/{slug}.py"
            if target_panel != NO_PANEL:
                config.add_script_to_panel(slug, target_panel)
                persist_config(config)
                message += f" e adicionado ao painel '{target_panel}'"
            st.success(message + ".")
        except ScriptError as exc:
            st.error(str(exc))
