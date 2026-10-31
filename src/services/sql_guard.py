"""Garante que apenas consultas de leitura cheguem às origens de dados."""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

DEFAULT_LIMIT = 10_000

_FORBIDDEN = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Command,
    exp.Into,
)


class UnsafeQueryError(ValueError):
    """Consulta rejeitada por não ser somente leitura."""


def validate_readonly(sql: str, dialect: str = "postgres") -> exp.Expression:
    """Valida que `sql` é um único SELECT (ou WITH ... SELECT) e retorna a árvore."""
    if not sql or not sql.strip():
        raise UnsafeQueryError("Consulta vazia.")
    try:
        statements = [s for s in sqlglot.parse(sql, read=dialect) if s is not None]
    except ParseError as exc:
        raise UnsafeQueryError(f"SQL inválido: {exc}") from exc
    if len(statements) != 1:
        raise UnsafeQueryError("Apenas uma instrução por consulta é permitida.")
    tree = statements[0]
    if not isinstance(tree, exp.Query):
        raise UnsafeQueryError("Apenas consultas SELECT são permitidas.")
    for node in tree.walk():
        if isinstance(node, _FORBIDDEN):
            raise UnsafeQueryError(f"Operação não permitida: {node.key.upper()}.")
    return tree


def enforce_limit(sql: str, dialect: str = "postgres", limit: int = DEFAULT_LIMIT) -> str:
    """Valida a consulta e aplica um LIMIT caso ela não possua um."""
    tree = validate_readonly(sql, dialect)
    if tree.args.get("limit") is None:
        tree = tree.limit(limit)
    return tree.sql(dialect=dialect)
