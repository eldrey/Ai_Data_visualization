"""Ajustes de legibilidade aplicados às figuras antes de exibi-las.

O Streamlit aplica o próprio tema (claro ou escuro) às figuras Plotly. Quando o
script define cores de fundo (ex.: células de go.Table) sem definir a cor da
fonte, o texto herda a cor do tema e pode ficar ilegível, como texto claro sobre
fundo branco. Aqui a fonte recebe uma cor contrastante com o fundo.
"""

from __future__ import annotations

import re

from plotly.graph_objects import Figure

DARK_TEXT = "#111827"
LIGHT_TEXT = "#f9fafb"

_RGB_RE = re.compile(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)")
# Nomes CSS de cores claras mais usados em tabelas; nomes desconhecidos são ignorados.
_LIGHT_NAMES = frozenset(
    {
        "white", "whitesmoke", "snow", "ivory", "ghostwhite", "aliceblue", "azure", "honeydew",
        "mintcream", "lavender", "lavenderblush", "linen", "beige", "oldlace", "floralwhite",
        "seashell", "cornsilk", "lightyellow", "lightcyan", "lightgray", "lightgrey", "gainsboro",
        "lightblue", "lightsteelblue", "paleturquoise", "lemonchiffon", "papayawhip", "mistyrose",
    }
)
_DARK_NAMES = frozenset(
    {"black", "navy", "darkblue", "midnightblue", "darkslategray", "darkslategrey", "dimgray", "dimgrey", "darkgreen", "maroon", "indigo"}
)


def is_light(color: object) -> bool | None:
    """Retorna True/False conforme o brilho da cor, ou None se não for possível determinar."""
    if not isinstance(color, str):
        return None
    value = color.strip().lower()
    if value in _LIGHT_NAMES:
        return True
    if value in _DARK_NAMES:
        return False
    if value.startswith("#") and len(value) in (4, 7):
        digits = value[1:]
        if len(digits) == 3:
            digits = "".join(c * 2 for c in digits)
        try:
            r, g, b = (int(digits[i : i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return None
    elif match := _RGB_RE.match(value):
        r, g, b = (float(x) for x in match.groups())
    else:
        return None
    # Luminância relativa aproximada (ITU-R BT.601).
    return (0.299 * r + 0.587 * g + 0.114 * b) > 150


def _first_color(fill: object) -> object:
    """Cores de preenchimento podem ser escalares, listas ou listas de listas."""
    while isinstance(fill, (list, tuple)):
        if not fill:
            return None
        fill = fill[0]
    return fill


def _fix_section(section) -> None:
    if section is None or section.font.color is not None:
        return
    light = is_light(_first_color(section.fill.color))
    if light is not None:
        section.font.color = DARK_TEXT if light else LIGHT_TEXT


def ensure_readable(fig: Figure) -> Figure:
    for trace in fig.data:
        if trace.type == "table":
            _fix_section(trace.header)
            _fix_section(trace.cells)
    return fig
