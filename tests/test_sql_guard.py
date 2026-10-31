import pytest

from src.services.sql_guard import UnsafeQueryError, enforce_limit, validate_readonly


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM vendas",
        "WITH t AS (SELECT 1 AS x) SELECT x FROM t",
        "SELECT a FROM x UNION SELECT a FROM y",
    ],
)
def test_accepts_selects(sql):
    validate_readonly(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "   ",
        "DROP TABLE vendas",
        "DELETE FROM vendas",
        "UPDATE vendas SET valor = 0",
        "INSERT INTO vendas VALUES (1)",
        "SELECT 1; DELETE FROM vendas",
        "SELECT * INTO copia FROM vendas",
        "CREATE TABLE x AS SELECT 1",
        "TRUNCATE vendas",
        "WITH d AS (DELETE FROM vendas RETURNING *) SELECT * FROM d",
        "SELEC * FRM",
    ],
)
def test_rejects_unsafe(sql):
    with pytest.raises(UnsafeQueryError):
        validate_readonly(sql)


def test_enforce_limit_adds_limit():
    assert enforce_limit("SELECT * FROM t", limit=50).endswith("LIMIT 50")


def test_enforce_limit_keeps_existing_limit():
    assert enforce_limit("SELECT * FROM t LIMIT 5", limit=50).endswith("LIMIT 5")


def test_duckdb_dialect():
    assert "LIMIT" in enforce_limit('SELECT * FROM "main"."t"', dialect="duckdb")
