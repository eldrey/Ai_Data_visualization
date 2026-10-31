"""Explorador de tabelas (estilo DBeaver simplificado, somente leitura)."""

import pandas as pd
import streamlit as st

from src.utils.ui_state import get_config, get_source, source_names

st.title("🗂️ Explorador de dados")

config = get_config()
names = source_names(config)
if not names:
    st.info("Cadastre uma origem de dados primeiro.")
    st.stop()

source_name = st.selectbox("Origem", names)
try:
    source = get_source(config.get_source(source_name))
    schemas = source.list_schemas()
except Exception as exc:  # noqa: BLE001
    st.error(f"Não foi possível conectar: {exc}")
    st.stop()

nav, main = st.columns([1, 3])
with nav:
    schema = st.selectbox("Schema", schemas)
    tables = source.list_tables(schema) if schema else []
    filter_text = st.text_input("Filtrar tabelas")
    visible = [t for t in tables if filter_text.lower() in t.lower()]
    table = st.radio("Tabelas", visible, label_visibility="collapsed") if visible else None
    st.caption(f"{len(tables)} tabela(s)")

with main:
    tab_cols, tab_data, tab_sql = st.tabs(["Colunas", "Dados", "Consulta SQL"])
    if table:
        with tab_cols:
            cols = source.get_columns(table, schema)
            st.dataframe(
                pd.DataFrame([{"coluna": c.name, "tipo": c.type, "nulo": c.nullable} for c in cols]),
                hide_index=True,
                width="stretch",
            )
        with tab_data:
            limit = st.number_input("Linhas", min_value=10, max_value=5000, value=100, step=50)
            try:
                st.dataframe(source.preview(table, schema, limit=int(limit)), width="stretch")
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
    else:
        tab_cols.info("Selecione uma tabela.")
        tab_data.info("Selecione uma tabela.")
    with tab_sql:
        default_sql = f"SELECT * FROM {source.quote_table(table, schema)}" if table else ""
        sql = st.text_area("SQL (somente SELECT)", value=default_sql, height=150)
        if st.button("Executar", type="primary"):
            try:
                result = source.run_query(sql, limit=1000)
                st.caption(f"{len(result)} linha(s)")
                st.dataframe(result, width="stretch")
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
