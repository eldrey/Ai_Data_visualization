"""Painéis (dashboards) nomeados com os gráficos selecionados."""

from datetime import datetime

import streamlit as st

from src.config.settings import DataSourceConfig
from src.services import script_runner
from src.services.script_store import parse_script
from src.utils.ui_state import clear_sources, get_config, get_source, get_store, persist_config

PANEL_KEY = "panel_selector"
SWITCH_KEY = "_switch_to_panel"


@st.cache_data(show_spinner=False)
def render_chart(slug: str, code: str, source_json: str):
    """Executa a query e o build_chart; o resultado fica em cache até o usuário clicar em Atualizar."""
    source = get_source(DataSourceConfig.model_validate_json(source_json))
    fig = script_runner.run_script(parse_script(slug, code), source)
    return fig, datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def switch_panel(name: str) -> None:
    """Agenda a troca de painel; o seletor só pode ser alterado antes de ser renderizado."""
    st.session_state[SWITCH_KEY] = name
    st.rerun()


config = get_config()
store = get_store()
scripts = {s.slug: s for s in store.list_scripts()}

# Painel inicial: troca agendada > ?painel= na URL > seleção atual > primeiro painel.
names = config.panel_names
if SWITCH_KEY in st.session_state:
    st.session_state[PANEL_KEY] = st.session_state.pop(SWITCH_KEY)
elif PANEL_KEY not in st.session_state and st.query_params.get("painel") in names:
    st.session_state[PANEL_KEY] = st.query_params["painel"]
if st.session_state.get(PANEL_KEY) not in names:
    st.session_state[PANEL_KEY] = names[0]

title_col, panel_col, refresh_col = st.columns([3, 2, 1], vertical_alignment="bottom")
title_col.title("📊 Dashboard")
panel_name = panel_col.selectbox("Painel", names, key=PANEL_KEY)
if refresh_col.button("🔄 Atualizar", width="stretch", help="Reexecuta as queries de todos os gráficos"):
    render_chart.clear()
    clear_sources()  # recarrega conexões e arquivos CSV/XLSX alterados no disco
st.query_params["painel"] = panel_name
panel = config.get_panel(panel_name)


def remove_from_panel(slug: str) -> None:
    """Tira o gráfico deste painel, mantendo o script salvo."""
    panel.selected_scripts = [s for s in panel.selected_scripts if s != slug]
    persist_config(config)


def delete_script(slug: str) -> None:
    """Apaga o arquivo do script e o remove de todos os painéis."""
    store.delete(slug)
    config.remove_script_everywhere(slug)
    persist_config(config)


def delete_with_confirmation(slug: str, key: str) -> None:
    with st.popover("🗑️ Excluir", width="stretch"):
        st.warning(f"Excluir definitivamente **{scripts[slug].title}**? O arquivo `{slug}.py` será apagado.")
        others = [p for p in config.panels_with(slug) if p != panel_name]
        if others:
            st.caption("Também será removido dos painéis: " + ", ".join(others))
        if st.button("Confirmar exclusão", type="primary", key=f"confirm_{key}"):
            delete_script(slug)
            st.rerun()


with st.expander("Gerenciar painéis"):
    new_col, rename_col, delete_col = st.columns(3)
    with new_col:
        new_name = st.text_input("Novo painel", placeholder="Ex.: Financeiro")
        if st.button("Criar painel", type="primary"):
            try:
                config.add_panel(new_name)
                persist_config(config)
                switch_panel(new_name.strip())
            except ValueError as exc:
                st.error(str(exc))
    with rename_col:
        renamed = st.text_input("Renomear painel atual", value=panel_name)
        if st.button("Renomear"):
            try:
                config.rename_panel(panel_name, renamed)
                persist_config(config)
                switch_panel(renamed.strip())
            except ValueError as exc:
                st.error(str(exc))
    with delete_col:
        st.write("Excluir painel atual")
        only_one = len(config.panels) == 1
        with st.popover("🗑️ Excluir painel", disabled=only_one, help="É preciso manter pelo menos um painel" if only_one else None):
            st.warning(f"Excluir o painel **{panel_name}**? Os gráficos continuam salvos.")
            if st.button("Confirmar exclusão do painel", type="primary"):
                config.remove_panel(panel_name)
                persist_config(config)
                switch_panel(config.panel_names[0])

if not scripts:
    st.info("Nenhum gráfico salvo ainda. Use a página 'Gerar gráfico'.")
    st.stop()

with st.expander(f"Configurar painel '{panel_name}'"):
    selected = st.multiselect(
        "Gráficos exibidos",
        list(scripts),
        default=[s for s in panel.selected_scripts if s in scripts],
        format_func=lambda slug: scripts[slug].title,
    )
    columns = st.slider("Colunas", 1, 4, panel.columns)
    if st.button("Salvar layout", type="primary"):
        panel.selected_scripts = selected
        panel.columns = columns
        persist_config(config)
        st.rerun()

    orphans = [s for s in scripts if not config.panels_with(s)]
    if orphans:
        st.divider()
        st.caption("Gráficos salvos que não estão em nenhum painel")
        for slug in orphans:
            name_col, delete_col = st.columns([3, 1])
            name_col.write(scripts[slug].title)
            with delete_col:
                delete_with_confirmation(slug, key=f"orphan_{slug}")

active = [scripts[s] for s in panel.selected_scripts if s in scripts]
if not active:
    st.info(f"O painel '{panel_name}' está vazio. Selecione os gráficos em 'Configurar painel'.")
    st.stop()

grid = st.columns(panel.columns)
for index, script in enumerate(active):
    with grid[index % panel.columns]:
        with st.container(border=True):
            source_cfg = config.get_source(script.source or "")
            if source_cfg is None:
                st.warning(f"**{script.title}**: origem '{script.source}' não está configurada.")
            else:
                try:
                    with st.spinner(f"Carregando {script.title}..."):
                        fig, updated_at = render_chart(script.slug, script.code, source_cfg.model_dump_json())
                    st.plotly_chart(fig, width="stretch", key=f"chart_{script.slug}")
                    st.caption(f"Atualizado em {updated_at}")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"**{script.title}**: {exc}")
            code_col, remove_col, delete_col = st.columns(3)
            with code_col.popover("Código", width="stretch"):
                st.code(script.code, language="python")
            if remove_col.button("➖ Remover", key=f"remove_{script.slug}", help="Tira deste painel sem apagar o script"):
                remove_from_panel(script.slug)
                st.rerun()
            with delete_col:
                delete_with_confirmation(script.slug, key=f"card_{script.slug}")
