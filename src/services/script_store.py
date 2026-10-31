"""Persistência dos scripts de gráfico na pasta dashboards_scripts."""

from __future__ import annotations

import ast
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from src.config import settings

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")


class ScriptError(ValueError):
    """Script inexistente, inválido ou com nome não permitido."""


@dataclass
class ChartScript:
    slug: str
    code: str
    metadata: dict = field(default_factory=dict)
    sql: str = ""

    @property
    def title(self) -> str:
        return str(self.metadata.get("title") or self.slug)

    @property
    def source(self) -> str | None:
        return self.metadata.get("source")


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")
    if not slug or slug[0].isdigit():
        slug = f"grafico_{slug}".rstrip("_")
    return slug


def _literal_assignments(code: str) -> dict[str, object]:
    tree = ast.parse(code)
    values: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                try:
                    values[target.id] = ast.literal_eval(node.value)
                except ValueError:
                    continue
    return values


def parse_script(slug: str, code: str) -> ChartScript:
    try:
        values = _literal_assignments(code)
    except SyntaxError as exc:
        raise ScriptError(f"Script '{slug}' com erro de sintaxe: {exc.msg}") from exc
    metadata = values.get("METADATA")
    sql = values.get("SQL")
    return ChartScript(
        slug=slug,
        code=code,
        metadata=metadata if isinstance(metadata, dict) else {},
        sql=sql if isinstance(sql, str) else "",
    )


def set_metadata(code: str, metadata: dict) -> str:
    """Substitui (ou insere) a atribuição METADATA no topo do script."""
    tree = ast.parse(code)
    lines = code.splitlines()
    insert_at = 0
    for node in reversed(tree.body):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "METADATA" for t in node.targets
        ):
            del lines[node.lineno - 1 : node.end_lineno]
    tree = ast.parse("\n".join(lines))
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            insert_at = node.end_lineno
        else:
            break
    lines[insert_at:insert_at] = ["", f"METADATA = {metadata!r}"]
    return "\n".join(lines).strip() + "\n"


class ScriptStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = Path(directory or settings.SCRIPTS_DIR)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, slug: str) -> Path:
        if not _SLUG_RE.match(slug):
            raise ScriptError(f"Nome de script inválido: {slug!r}")
        return self.directory / f"{slug}.py"

    def exists(self, slug: str) -> bool:
        return self._path(slug).exists()

    def save(self, slug: str, code: str, overwrite: bool = False) -> ChartScript:
        path = self._path(slug)
        if path.exists() and not overwrite:
            raise ScriptError(f"Já existe um script chamado '{slug}'.")
        path.write_text(code, encoding="utf-8")
        return parse_script(slug, code)

    def load(self, slug: str) -> ChartScript:
        path = self._path(slug)
        if not path.exists():
            raise ScriptError(f"Script '{slug}' não encontrado.")
        return parse_script(slug, path.read_text(encoding="utf-8"))

    def list_scripts(self) -> list[ChartScript]:
        scripts = []
        for path in sorted(self.directory.glob("*.py")):
            if path.stem.startswith("_") or not _SLUG_RE.match(path.stem):
                continue
            try:
                scripts.append(self.load(path.stem))
            except ScriptError:
                continue
        return scripts

    def delete(self, slug: str) -> None:
        path = self._path(slug)
        if path.exists():
            path.unlink()
