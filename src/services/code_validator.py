"""Validação estática (AST) dos scripts de gráfico gerados pela LLM."""

from __future__ import annotations

import ast

ALLOWED_IMPORTS = frozenset(
    {"pandas", "numpy", "plotly", "math", "datetime", "statistics", "__future__"}
)
FORBIDDEN_NAMES = frozenset(
    {
        "exec",
        "eval",
        "compile",
        "open",
        "__import__",
        "globals",
        "locals",
        "vars",
        "getattr",
        "setattr",
        "delattr",
        "input",
        "breakpoint",
        "memoryview",
    }
)
REQUIRED_ASSIGNMENTS = ("METADATA", "SQL")
ENTRYPOINT = "build_chart"


def _check_imports(node: ast.AST, errors: list[str]) -> None:
    if isinstance(node, ast.Import):
        modules = [alias.name for alias in node.names]
    elif isinstance(node, ast.ImportFrom):
        if node.level:
            errors.append(f"Linha {node.lineno}: imports relativos não são permitidos.")
            return
        modules = [node.module or ""]
    else:
        return
    for module in modules:
        if module.split(".")[0] not in ALLOWED_IMPORTS:
            errors.append(f"Linha {node.lineno}: import não permitido '{module}'.")


def validate_script(code: str) -> list[str]:
    """Retorna a lista de erros encontrados; lista vazia significa script válido."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"Erro de sintaxe na linha {exc.lineno}: {exc.msg}"]

    errors: list[str] = []
    for node in ast.walk(tree):
        _check_imports(node, errors)
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            errors.append(f"Linha {node.lineno}: uso de '{node.id}' não é permitido.")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            errors.append(f"Linha {node.lineno}: acesso a atributo '{node.attr}' não é permitido.")
        elif isinstance(node, ast.Name) and node.id.startswith("__") and node.id != "__name__":
            errors.append(f"Linha {node.lineno}: uso de '{node.id}' não é permitido.")
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            errors.append(f"Linha {node.lineno}: 'global'/'nonlocal' não são permitidos.")

    top_level = {
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    for name in REQUIRED_ASSIGNMENTS:
        if name not in top_level:
            errors.append(f"O script deve definir '{name}' no nível superior.")

    functions = {
        node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    func = functions.get(ENTRYPOINT)
    if func is None:
        errors.append(f"O script deve definir a função '{ENTRYPOINT}(df)'.")
    elif len(func.args.args) != 1:
        errors.append(f"'{ENTRYPOINT}' deve receber exatamente um argumento (df).")
    return errors
