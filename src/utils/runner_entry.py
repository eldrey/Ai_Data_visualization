"""Processo isolado que executa um script de gráfico.

Uso: python -I runner_entry.py <script.py> <dados.pkl> <saida.json>
Não depende do pacote `src` para poder rodar com `python -I`.
"""

from __future__ import annotations

import sys

MEMORY_LIMIT_BYTES = 2 * 1024**3


def _limit_resources(cpu_seconds: int) -> None:
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    except (ImportError, ValueError, OSError):  # pragma: no cover - depende da plataforma
        pass


def run(script_path: str, data_path: str, output_path: str) -> None:
    import pandas as pd

    with open(script_path, encoding="utf-8") as fh:
        code = fh.read()
    namespace: dict = {"__name__": "chart_script"}
    exec(compile(code, script_path, "exec"), namespace)  # noqa: S102 - código validado via AST
    df = pd.read_pickle(data_path)
    fig = namespace["build_chart"](df)
    if not hasattr(fig, "to_json"):
        raise TypeError("build_chart deve retornar uma figura Plotly.")
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(fig.to_json())


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print("uso: runner_entry.py <script> <dados> <saida>", file=sys.stderr)
        return 2
    try:
        run(argv[1], argv[2], argv[3])
    except Exception as exc:  # noqa: BLE001 - erro reportado ao processo pai
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    # Limites aplicados apenas no subprocesso, nunca no processo que importa o módulo.
    _limit_resources(cpu_seconds=60)
    sys.exit(main(sys.argv))
