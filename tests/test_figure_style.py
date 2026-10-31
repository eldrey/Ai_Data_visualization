import plotly.graph_objects as go
import pytest

from src.services.figure_style import DARK_TEXT, LIGHT_TEXT, ensure_readable, is_light


@pytest.mark.parametrize(
    "color, expected",
    [
        ("white", True),
        ("#FFF", True),
        ("#f5f7fa", True),
        ("rgb(240, 240, 240)", True),
        ("rgba(255,255,255,0.5)", True),
        ("#2f4050", False),
        ("navy", False),
        ("rgb(20, 20, 20)", False),
        ("cornflowerblue", None),
        ("#zzzzzz", None),
        ("#12345", None),
        (None, None),
        (3, None),
    ],
)
def test_is_light(color, expected):
    assert is_light(color) is expected


def make_table(header_fill=None, cells_fill=None, cells_font=None):
    return go.Figure(
        go.Table(
            header=dict(values=["a"], fill_color=header_fill),
            cells=dict(values=[[1, 2]], fill_color=cells_fill, font=dict(color=cells_font)),
        )
    )


def test_light_cells_get_dark_text():
    # Linhas alternadas: lista de listas, como no caso real reportado.
    fig = ensure_readable(make_table(header_fill="#2f4050", cells_fill=[["#f5f7fa", "white"]]))
    assert fig.data[0].cells.font.color == DARK_TEXT
    assert fig.data[0].header.font.color == LIGHT_TEXT


def test_explicit_font_is_kept():
    fig = ensure_readable(make_table(cells_fill="white", cells_font="red"))
    assert fig.data[0].cells.font.color == "red"


def test_without_fill_uses_theme():
    fig = ensure_readable(make_table())
    assert fig.data[0].cells.font.color is None
    assert fig.data[0].header.font.color is None


def test_empty_fill_list_and_non_table_traces():
    fig = make_table(cells_fill=[[]])
    fig.add_trace(go.Bar(x=[1], y=[2]))
    ensure_readable(fig)
    assert fig.data[0].cells.font.color is None


def test_runner_applies_fix():
    from src.services.script_runner import render_figure
    import pandas as pd

    code = (
        "import plotly.graph_objects as go\n"
        'METADATA = {}\nSQL = "SELECT 1"\n'
        "def build_chart(df):\n"
        "    return go.Figure(go.Table(header=dict(values=['a']), cells=dict(values=[[1]], fill_color='white')))\n"
    )
    fig = render_figure(code, pd.DataFrame({"a": [1]}))
    assert fig.data[0].cells.font.color == DARK_TEXT
