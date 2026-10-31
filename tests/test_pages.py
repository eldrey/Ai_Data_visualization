"""Smoke tests das páginas Streamlit com AppTest."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.config.settings import AppConfig, LLMConfig, save_config
from src.services.script_store import ScriptStore

PAGES = Path(__file__).resolve().parent.parent / "src" / "pages"


@pytest.fixture
def configured(isolated_paths, csv_config, valid_script):
    config = AppConfig(data_sources=[csv_config], llm=LLMConfig(api_key="k"))
    config.panels[0].selected_scripts = ["vendas"]
    save_config(config)
    ScriptStore().save("vendas", valid_script)
    return config


def run_page(name: str) -> AppTest:
    at = AppTest.from_file(str(PAGES / name), default_timeout=30)
    return at.run()


@pytest.mark.parametrize(
    "page", ["data_sources.py", "explorer.py", "llm_settings.py", "chart_builder.py", "dashboard.py"]
)
def test_pages_render_empty(isolated_paths, page):
    at = run_page(page)
    assert not at.exception


@pytest.mark.parametrize(
    "page", ["data_sources.py", "explorer.py", "llm_settings.py", "chart_builder.py", "dashboard.py"]
)
def test_pages_render_configured(configured, page):
    at = run_page(page)
    assert not at.exception
    assert not at.error


def test_dashboard_renders_chart(configured):
    at = run_page("dashboard.py")
    assert len(at.get("plotly_chart")) == 1


def test_explorer_runs_query(configured):
    at = run_page("explorer.py")
    at.text_area[0].set_value("SELECT * FROM vendas").run()
    at.button[0].click().run()
    assert not at.error
    assert len(at.dataframe) >= 1


def test_explorer_blocks_write(configured):
    at = run_page("explorer.py")
    at.text_area[0].set_value("DELETE FROM vendas").run()
    at.button[0].click().run()
    assert at.error


def test_data_sources_save(isolated_paths, csv_dir):
    at = run_page("data_sources.py")
    at.selectbox[0].set_value("csv").run()
    at.text_input[0].set_value("novos")
    at.text_input[1].set_value(str(csv_dir))
    at.button[0].click().run()
    assert at.success
    from src.config.settings import load_config

    assert load_config().get_source("novos") is not None


def test_llm_settings_save(isolated_paths):
    at = run_page("llm_settings.py")
    at.selectbox[0].set_value("openai").run()
    at.text_input[0].set_value("gpt-x")
    at.button[0].click().run()
    from src.config.settings import load_config

    assert load_config().llm.provider == "openai"


def test_app_entrypoint(isolated_paths):
    at = AppTest.from_file(str(PAGES.parent / "app.py"), default_timeout=30).run()
    assert not at.exception


def _llm_reply(title: str) -> str:
    return (
        "```python\nimport plotly.express as px\n"
        'SQL = "SELECT mes, valor FROM vendas"\n'
        f"def build_chart(df):\n    return px.bar(df, x=\"mes\", y=\"valor\", title=\"{title}\")\n```"
    )


def test_chart_builder_updates_code_and_preview_on_regenerate(configured, mocker, fake_llm_factory):
    llm = fake_llm_factory(_llm_reply("Primeiro"), _llm_reply("Segundo"))
    mocker.patch("src.services.llm_connections.factory.create_llm", return_value=llm)
    at = run_page("chart_builder.py")
    at.multiselect[0].set_value([("main", "vendas")])
    at.text_input[0].set_value("Grafico")
    at.text_area[0].set_value("vendas por mes").run()

    at.button[0].click().run()  # gerar
    assert "Primeiro" in at.text_area[1].value
    at.button[1].click().run()  # pré-visualizar
    assert len(at.get("plotly_chart")) == 1

    at.button[0].click().run()  # gerar novamente
    assert "Segundo" in at.text_area[1].value
    assert len(at.get("plotly_chart")) == 0  # preview antigo não pode continuar na tela
    at.button[1].click().run()
    assert len(at.get("plotly_chart")) == 1


def _button(at: AppTest, key: str):
    return next(b for b in at.button if b.key == key)


def test_dashboard_remove_keeps_script(configured):
    at = run_page("dashboard.py")
    _button(at, "remove_vendas").click().run()
    from src.config.settings import load_config

    assert load_config().panels[0].selected_scripts == []
    assert ScriptStore().exists("vendas")
    assert len(at.get("plotly_chart")) == 0
    # O script continua disponível para exclusão na lista de gráficos sem painel.
    assert any(b.key == "confirm_orphan_vendas" for b in at.button)


def test_dashboard_delete_removes_file(configured):
    at = run_page("dashboard.py")
    _button(at, "confirm_card_vendas").click().run()
    from src.config.settings import load_config

    assert not ScriptStore().exists("vendas")
    assert load_config().panels[0].selected_scripts == []
    assert at.info  # "Nenhum gráfico salvo ainda"


def test_dashboard_delete_hidden_script(configured):
    at = run_page("dashboard.py")
    _button(at, "remove_vendas").click().run()
    _button(at, "confirm_orphan_vendas").click().run()
    assert not ScriptStore().exists("vendas")


def test_dashboard_caches_until_refresh(configured, mocker):
    import streamlit as st

    from src.services import script_runner

    st.cache_data.clear()
    spy = mocker.spy(script_runner, "run_script")
    at = run_page("dashboard.py")
    assert spy.call_count == 1
    assert any("Atualizado em" in c.value for c in at.caption)

    at.run()
    assert spy.call_count == 1  # rerun sem clicar em Atualizar usa o cache

    next(b for b in at.button if "Atualizar" in b.label).click().run()
    assert spy.call_count == 2


def _text_input(at: AppTest, label: str):
    return next(t for t in at.text_input if t.label == label)


def test_create_rename_and_delete_panel(configured):
    from src.config.settings import load_config

    at = run_page("dashboard.py")
    _text_input(at, "Novo painel").set_value("Financeiro")
    next(b for b in at.button if b.label == "Criar painel").click().run()
    assert load_config().panel_names == ["Principal", "Financeiro"]
    assert at.selectbox[0].value == "Financeiro"  # troca para o painel criado
    assert at.info  # painel novo começa vazio

    _text_input(at, "Renomear painel atual").set_value("Custos")
    next(b for b in at.button if b.label == "Renomear").click().run()
    assert load_config().panel_names == ["Principal", "Custos"]
    assert at.selectbox[0].value == "Custos"

    next(b for b in at.button if b.label == "Confirmar exclusão do painel").click().run()
    assert load_config().panel_names == ["Principal"]
    assert at.selectbox[0].value == "Principal"
    assert len(at.get("plotly_chart")) == 1


def test_duplicate_panel_name_shows_error(configured):
    at = run_page("dashboard.py")
    _text_input(at, "Novo painel").set_value("Principal")
    next(b for b in at.button if b.label == "Criar painel").click().run()
    assert any("Já existe" in e.value for e in at.error)


def test_switch_panels_shows_each_panel_charts(configured):
    from src.config.settings import load_config, save_config

    config = load_config()
    config.add_panel("Vazio")
    save_config(config)
    at = run_page("dashboard.py")
    assert len(at.get("plotly_chart")) == 1
    at.selectbox[0].set_value("Vazio").run()
    assert len(at.get("plotly_chart")) == 0


def test_delete_script_removes_from_all_panels(configured):
    from src.config.settings import load_config, save_config

    config = load_config()
    config.add_panel("Outro")
    config.add_script_to_panel("vendas", "Outro")
    save_config(config)
    at = run_page("dashboard.py")
    _button(at, "confirm_card_vendas").click().run()
    assert load_config().panels_with("vendas") == []


def test_chart_builder_saves_to_selected_panel(configured, mocker, fake_llm_factory):
    from src.config.settings import load_config, save_config

    config = load_config()
    config.add_panel("Financeiro")
    save_config(config)
    mocker.patch(
        "src.services.llm_connections.factory.create_llm",
        return_value=fake_llm_factory(_llm_reply("Novo")),
    )
    at = run_page("chart_builder.py")
    at.multiselect[0].set_value([("main", "vendas")])
    at.text_input[0].set_value("Grafico novo")
    at.text_area[0].set_value("vendas").run()
    at.button[0].click().run()
    next(s for s in at.selectbox if s.label == "Adicionar ao painel").set_value("Financeiro")
    next(b for b in at.button if b.label == "Salvar").click().run()
    assert at.success
    assert load_config().panels_with("grafico_novo") == ["Financeiro"]
