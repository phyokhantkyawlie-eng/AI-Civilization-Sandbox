import json
import os
os.environ.setdefault("MPLBACKEND", "Agg")
from civsandbox.config import Settings
from civsandbox.experiments import run_batch
from civsandbox.results import render


def test_real_charts_and_decision_exports(tmp_path):
    folder = tmp_path/"pilot"
    rows = run_batch(Settings(provider="rule-based"), 1, 12, 42, folder)
    charts = render(folder)
    assert len(list(charts.glob("*.png"))) == 6
    assert all(p.stat().st_size > 1000 for p in charts.glob("*.png"))
    decisions = json.loads((charts/"decisions.json").read_text())
    assert decisions and all(d["provider"] == "rule-based" for d in decisions)
    assert len(rows[0]["hunger_series"]) == 12
    assert "directed_trust" not in rows[0]["recent_decisions"][0]["context"]
    assert "directed_trust" in rows[1]["recent_decisions"][0]["context"]


def test_older_results_remain_unavailable_instead_of_invented(tmp_path):
    from civsandbox.experiments import run_batch
    folder = tmp_path/"old"
    run_batch(Settings(), 1, 0, 42, folder)
    data = json.loads((folder/"summary.json").read_text())
    for row in data["trials"]:
        row.pop("hunger_series", None)
        row.pop("recent_decisions", None)
    (folder/"summary.json").write_text(json.dumps(data))
    charts = render(folder)
    assert json.loads((charts/"decisions.json").read_text()) == []
    assert (charts/"hunger_over_time.png").exists()


def test_interrupted_empty_export_is_handled_without_traceback(tmp_path, monkeypatch, capsys):
    from civsandbox.results import main
    (tmp_path/"summary.json").write_text(json.dumps({"trials": []}))
    monkeypatch.setattr("sys.argv", ["results", str(tmp_path)])
    assert main() == 1
    assert "Could not read results" in capsys.readouterr().out
