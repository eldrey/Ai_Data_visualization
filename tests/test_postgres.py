import pytest
from sqlalchemy import create_engine, text

from src.config.settings import DataSourceConfig
from src.services.db_connections.factory import create_source
from src.services.db_connections.file_source import FileSource
from src.services.db_connections.postgres import PostgresSource, build_connect_args, build_url
from src.services.sql_guard import UnsafeQueryError


def pg_config(**overrides):
    data = dict(name="pg", type="postgres", host="db", port=5432, database="app", username="u", password="p")
    data.update(overrides)
    return DataSourceConfig(**data)


def test_build_url_resolves_password(monkeypatch):
    monkeypatch.setenv("PG_PASS", "s3cr3t")
    url = build_url(pg_config(password="${PG_PASS}"))
    assert url.drivername == "postgresql+psycopg"
    assert url.password == "s3cr3t"
    assert url.host == "db" and url.database == "app"


def test_connect_args_neon_requires_ssl():
    assert build_connect_args(pg_config(type="neon"))["sslmode"] == "require"
    assert "sslmode" not in build_connect_args(pg_config())
    assert build_connect_args(pg_config(sslmode="verify-full"))["sslmode"] == "verify-full"


class SqliteSource(PostgresSource):
    """Usa SQLite para exercitar o caminho SQLAlchemy sem um Postgres real."""

    readonly_statement = None


@pytest.fixture
def sqlite_source():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE vendas (mes INTEGER NOT NULL, valor REAL)"))
        conn.execute(text("INSERT INTO vendas VALUES (1, 10), (2, 20), (3, 30)"))
        conn.execute(text("CREATE VIEW v_vendas AS SELECT * FROM vendas"))
    source = SqliteSource(pg_config(), engine=engine)
    yield source
    source.close()


def test_introspection(sqlite_source):
    sqlite_source.test_connection()
    assert sqlite_source.list_schemas() == ["main"]
    assert sqlite_source.list_tables("main") == ["v_vendas", "vendas"]
    cols = sqlite_source.get_columns("vendas", "main")
    assert cols[0].name == "mes" and cols[0].nullable is False


def test_preview_and_query(sqlite_source):
    assert len(sqlite_source.preview("vendas", "main", limit=2)) == 2
    df = sqlite_source.run_query("SELECT SUM(valor) AS total FROM vendas")
    assert df["total"].iloc[0] == 60


def test_query_rejects_writes(sqlite_source):
    with pytest.raises(UnsafeQueryError):
        sqlite_source.run_query("DELETE FROM vendas")


def test_readonly_statement_runs_in_transaction(mocker):
    engine = mocker.MagicMock()
    conn = engine.connect.return_value.__enter__.return_value
    mocker.patch("src.services.db_connections.postgres.pd.read_sql_query", return_value="df")
    source = PostgresSource(pg_config(), engine=engine)
    assert source._read("SELECT 1") == "df"
    first_stmt = conn.execute.call_args_list[0].args[0]
    assert str(first_stmt) == "SET TRANSACTION READ ONLY"
    conn.begin.return_value.__enter__.return_value.rollback.assert_called_once()


def test_factory(csv_config):
    assert isinstance(create_source(pg_config(type="neon")), PostgresSource)
    assert isinstance(create_source(csv_config), FileSource)
    bogus = pg_config().model_copy(update={"type": "oracle"})
    with pytest.raises(ValueError):
        create_source(bogus)
