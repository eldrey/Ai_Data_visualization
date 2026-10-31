"""Cadastro das origens de dados."""

import streamlit as st

from src.config.settings import DataSourceConfig
from src.utils.ui_state import clear_sources, get_config, persist_config

TYPE_LABELS = {"postgres": "PostgreSQL", "neon": "Neon (Postgres serverless)", "csv": "Arquivos CSV", "xlsx": "Arquivos Excel (xlsx)"}

st.title("🔌 Origens de dados")
st.caption("Conexões somente leitura. Senhas podem ser informadas como ${NOME_DA_VARIAVEL} para ler do .env.")

config = get_config()


def test_source(cfg: DataSourceConfig) -> None:
    from src.services.db_connections.factory import create_source

    try:
        source = create_source(cfg)
        source.test_connection()
        source.close()
        st.success(f"Conexão com '{cfg.name}' OK.")
    except Exception as exc:  # noqa: BLE001
        st.error(f"Falha na conexão: {exc}")


if config.data_sources:
    for src in config.data_sources:
        with st.expander(f"{src.name} — {TYPE_LABELS[src.type]}"):
            if src.is_file:
                st.write(f"Caminho: `{src.path}`")
            else:
                st.write(f"`{src.username}@{src.host}:{src.port}/{src.database}`")
            col1, col2 = st.columns(2)
            if col1.button("Testar conexão", key=f"test_{src.name}"):
                test_source(src)
            if col2.button("Remover", key=f"del_{src.name}", type="secondary"):
                config.remove_source(src.name)
                persist_config(config)
                clear_sources()
                st.rerun()
else:
    st.info("Nenhuma origem cadastrada ainda.")

st.subheader("Adicionar / atualizar origem")
source_type = st.selectbox("Tipo", list(TYPE_LABELS), format_func=TYPE_LABELS.get)
with st.form("source_form"):
    name = st.text_input("Nome (identificador único)")
    values: dict = {"type": source_type}
    if source_type in ("csv", "xlsx"):
        values["path"] = st.text_input("Caminho do arquivo ou diretório", value="data/")
    else:
        c1, c2 = st.columns([3, 1])
        values["host"] = c1.text_input("Host", value="localhost" if source_type == "postgres" else "")
        values["port"] = c2.number_input("Porta", value=5432, min_value=1, max_value=65535)
        values["database"] = st.text_input("Banco de dados")
        values["username"] = st.text_input("Usuário")
        values["password"] = st.text_input("Senha", type="password")
        default_ssl = "require" if source_type == "neon" else ""
        values["sslmode"] = st.text_input("sslmode (opcional)", value=default_ssl) or None
    c1, c2 = st.columns(2)
    save = c1.form_submit_button("Salvar", type="primary")
    test = c2.form_submit_button("Testar sem salvar")

if save or test:
    if not name.strip():
        st.error("Informe um nome para a origem.")
    else:
        cfg = DataSourceConfig(name=name.strip(), **values)
        if test:
            test_source(cfg)
        else:
            config.upsert_source(cfg)
            persist_config(config)
            clear_sources()
            st.success(f"Origem '{cfg.name}' salva.")
