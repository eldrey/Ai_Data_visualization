import pandas as pd
import pytest

from src.config.settings import DataSourceConfig
from src.services.db_connections.file_source import FileSource, load_frames, table_name
from src.services.sql_guard import UnsafeQueryError


def test_table_name_normalization():
    assert table_name("Vendas 2024") == "vendas_2024"
    assert table_name("2024") == "t_2024"
    assert table_name("Plan", "Aba 1") == "plan_aba_1"


def test_lists_tables_and_columns(file_source):
    file_source.test_connection()
    assert file_source.list_schemas() == ["main"]
    assert file_source.list_tables("main") == ["clientes_2024", "vendas"]
    cols = file_source.get_columns("vendas", "main")
    assert [c.name for c in cols] == ["mes", "valor"]


def test_preview_and_query(file_source):
    assert len(file_source.preview("vendas", "main", limit=2)) == 2
    df = file_source.run_query("SELECT mes, SUM(valor) AS total FROM vendas GROUP BY mes ORDER BY mes")
    assert df["total"].tolist() == [15, 20, 30]


def test_rejects_writes(file_source):
    with pytest.raises(UnsafeQueryError):
        file_source.run_query("DROP TABLE vendas")


def test_blocks_external_file_access(file_source, tmp_path):
    secret = tmp_path / "secret.csv"
    secret.write_text("a\n1\n")
    with pytest.raises(Exception, match="(?i)permission|disabled"):
        file_source.run_query(f"SELECT * FROM read_csv('{secret}')")


def test_quote_table(file_source):
    assert file_source.quote_table('x"y', "main") == '"main"."x""y"'


def test_single_xlsx_file_uses_sheet_names(tmp_path):
    path = tmp_path / "planilha.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"a": [1]}).to_excel(writer, sheet_name="Resumo", index=False)
        pd.DataFrame({"b": [2]}).to_excel(writer, sheet_name="Detalhe", index=False)
    source = FileSource(DataSourceConfig(name="x", type="xlsx", path=str(path)))
    assert source.list_tables("main") == ["detalhe", "resumo"]


def test_xlsx_directory_prefixes_file_name(tmp_path):
    for name in ("a", "b"):
        pd.DataFrame({"v": [1]}).to_excel(tmp_path / f"{name}.xlsx", sheet_name="S", index=False)
    frames = load_frames(DataSourceConfig(name="x", type="xlsx", path=str(tmp_path)))
    assert set(frames) == {"a_s", "b_s"}


@pytest.mark.parametrize(
    "path, error",
    [(None, ValueError), ("/caminho/que/nao/existe", FileNotFoundError)],
)
def test_invalid_paths(path, error):
    with pytest.raises(error):
        load_frames(DataSourceConfig(name="x", type="csv", path=path))


def test_empty_directory(tmp_path):
    with pytest.raises(ValueError, match="Nenhum arquivo"):
        load_frames(DataSourceConfig(name="x", type="csv", path=str(tmp_path)))
