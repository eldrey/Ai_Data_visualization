import pytest

from src.config.settings import (
    AppConfig,
    DataSourceConfig,
    LLMConfig,
    load_config,
    resolve_secret,
    save_config,
)


def test_resolve_secret_reads_env(monkeypatch):
    monkeypatch.setenv("MY_KEY", "segredo")
    assert resolve_secret("${MY_KEY}") == "segredo"


def test_resolve_secret_literal_and_empty(monkeypatch):
    monkeypatch.delenv("MISSING_VAR", raising=False)
    assert resolve_secret("literal") == "literal"
    assert resolve_secret(None) is None
    assert resolve_secret("${MISSING_VAR}") is None


def test_load_missing_file_returns_defaults(tmp_path):
    config = load_config(tmp_path / "nao_existe.yaml")
    assert config.data_sources == []
    assert config.llm.provider == "anthropic"
    assert config.llm.model == "claude-opus-5-5"


def test_round_trip(tmp_path):
    path = tmp_path / "cfg" / "settings.yaml"
    config = AppConfig(llm=LLMConfig(provider="openai", model="gpt-x", api_key="${OPENAI_API_KEY}"))
    config.upsert_source(DataSourceConfig(name="pg", type="postgres", host="db", database="app"))
    config.panels[0].selected_scripts = ["a"]
    save_config(config, path)

    loaded = load_config(path)
    assert loaded == config
    assert "${OPENAI_API_KEY}" in path.read_text()


def test_empty_yaml_is_default(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text("")
    assert load_config(path) == AppConfig()


def test_source_management():
    config = AppConfig()
    config.upsert_source(DataSourceConfig(name="a", type="csv", path="x"))
    config.upsert_source(DataSourceConfig(name="a", type="csv", path="y"))
    assert len(config.data_sources) == 1
    assert config.get_source("a").path == "y"
    assert config.get_source("a").is_file
    config.remove_source("a")
    assert config.get_source("a") is None


def test_default_panel():
    assert AppConfig().panel_names == ["Principal"]
    assert AppConfig.model_validate({"panels": []}).panel_names == ["Principal"]


def test_migrates_legacy_dashboard(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text("dashboard:\n  selected_scripts: [a, b]\n  columns: 3\n")
    config = load_config(path)
    assert config.panel_names == ["Principal"]
    assert config.panels[0].selected_scripts == ["a", "b"]
    assert config.panels[0].columns == 3
    save_config(config, path)
    assert "dashboard" not in path.read_text()


def test_panel_management():
    config = AppConfig()
    config.add_panel("  Financeiro ")
    assert config.panel_names == ["Principal", "Financeiro"]
    with pytest.raises(ValueError, match="Já existe"):
        config.add_panel("Financeiro")
    with pytest.raises(ValueError, match="nome"):
        config.add_panel("   ")

    config.rename_panel("Financeiro", "Vendas")
    config.rename_panel("Vendas", "Vendas")  # mesmo nome não é erro
    assert config.get_panel("Vendas") is not None
    with pytest.raises(ValueError, match="não encontrado"):
        config.rename_panel("Inexistente", "X")

    config.add_script_to_panel("graf", "Vendas")
    config.add_script_to_panel("graf", "Vendas")
    config.add_script_to_panel("graf", "Principal")
    assert config.get_panel("Vendas").selected_scripts == ["graf"]
    assert config.panels_with("graf") == ["Principal", "Vendas"]
    with pytest.raises(ValueError):
        config.add_script_to_panel("graf", "Inexistente")

    config.remove_script_everywhere("graf")
    assert config.panels_with("graf") == []

    config.remove_panel("Vendas")
    with pytest.raises(ValueError, match="pelo menos um"):
        config.remove_panel("Principal")
