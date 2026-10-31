import pytest

from src.services.script_store import ScriptError, ScriptStore, parse_script, set_metadata, slugify


def test_slugify():
    assert slugify("Vendas por Mês!") == "vendas_por_mes"
    assert slugify("2024 total") == "grafico_2024_total"
    assert slugify("???") == "grafico"


def test_parse_script(valid_script):
    script = parse_script("x", valid_script)
    assert script.title == "Vendas por mês"
    assert script.source == "arquivos"
    assert script.sql.startswith("SELECT")


def test_parse_script_without_literals():
    script = parse_script("x", "SQL = 'a' + 'b'\nMETADATA = None\n")
    assert script.sql == "" and script.metadata == {} and script.title == "x"


def test_parse_script_syntax_error():
    with pytest.raises(ScriptError):
        parse_script("x", "def (")


def test_set_metadata_replaces_existing(valid_script):
    code = set_metadata(valid_script, {"title": "Novo"})
    assert code.count("METADATA =") == 1
    assert parse_script("x", code).title == "Novo"
    assert code.index("METADATA") > code.index("import plotly")


def test_set_metadata_inserts_when_missing():
    code = set_metadata('SQL = "SELECT 1"\n', {"title": "T"})
    assert parse_script("x", code).title == "T"


def test_store_crud(tmp_path, valid_script):
    store = ScriptStore(tmp_path / "scripts")
    saved = store.save("vendas", valid_script)
    assert saved.slug == "vendas" and store.exists("vendas")
    with pytest.raises(ScriptError, match="Já existe"):
        store.save("vendas", valid_script)
    store.save("vendas", valid_script, overwrite=True)
    assert store.load("vendas").code == valid_script
    (tmp_path / "scripts" / "_privado.py").write_text("x = 1")
    (tmp_path / "scripts" / "quebrado.py").write_text("def (")
    assert [s.slug for s in store.list_scripts()] == ["vendas"]
    store.delete("vendas")
    assert not store.exists("vendas")
    with pytest.raises(ScriptError, match="não encontrado"):
        store.load("vendas")


@pytest.mark.parametrize("slug", ["../etc", "a/b", "", "Maiusculo"])
def test_store_rejects_bad_slugs(tmp_path, slug):
    with pytest.raises(ScriptError):
        ScriptStore(tmp_path).load(slug)


def test_store_default_dir(isolated_paths):
    store = ScriptStore()
    assert store.directory == isolated_paths / "scripts"
    assert store.directory.is_dir()
