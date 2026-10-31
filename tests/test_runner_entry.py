import json

import pandas as pd

from src.utils import runner_entry


def test_main_success(tmp_path, valid_script):
    script, data, out = tmp_path / "s.py", tmp_path / "d.pkl", tmp_path / "o.json"
    script.write_text(valid_script)
    pd.DataFrame({"mes": [1], "total": [2]}).to_pickle(data)
    assert runner_entry.main(["x", str(script), str(data), str(out)]) == 0
    assert json.loads(out.read_text())["data"]


def test_main_bad_args(capsys):
    assert runner_entry.main(["x"]) == 2
    assert "uso" in capsys.readouterr().err


def test_main_reports_errors(tmp_path, capsys):
    script, data = tmp_path / "s.py", tmp_path / "d.pkl"
    script.write_text("def build_chart(df):\n    raise ValueError('boom')\n")
    pd.DataFrame().to_pickle(data)
    assert runner_entry.main(["x", str(script), str(data), str(tmp_path / "o.json")]) == 1
    assert "ValueError: boom" in capsys.readouterr().err
