"""Ponto de entrada Streamlit."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")  # no Docker as variáveis já chegam via env_file

PAGES = Path(__file__).resolve().parent / "pages"

st.set_page_config(page_title="AI Data Visualization", page_icon="📊", layout="wide")

navigation = st.navigation(
    {
        "Visualização": [
            st.Page(PAGES / "dashboard.py", title="Dashboard", icon="📊", default=True),
            st.Page(PAGES / "chart_builder.py", title="Gerar gráfico", icon="✨"),
        ],
        "Dados": [
            st.Page(PAGES / "explorer.py", title="Explorador", icon="🗂️"),
            st.Page(PAGES / "data_sources.py", title="Origens de dados", icon="🔌"),
        ],
        "Configuração": [
            st.Page(PAGES / "llm_settings.py", title="LLM", icon="🤖"),
        ],
    }
)
navigation.run()
