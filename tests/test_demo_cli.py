import json

from roboway.demo_cli import Demo, render, run_no_ui


def test_render_shows_grid_jobs_and_metrics_without_color():
    demo = Demo("narrow_passage")
    state = demo.last_state
    text = render(state, [], color=False, terminal_width=120)
    assert "#" in text
    assert "P1" in text
    assert "D1" in text
    assert "Tick 0" in text
    assert "Completed: 0/3" in text
    assert "JOBS" in text


def test_scripted_no_ui_run_prints_events_metrics_and_summary(capsys):
    demo = Demo("narrow_passage", scripted=True)
    run_no_ui(demo)
    output = capsys.readouterr().out
    assert "DEADLOCK_DETECTED" in output
    assert "DEADLOCK_RESOLVED" in output
    assert "RUN SUMMARY" in output
    assert "Jobs delivered: 3/3" in output
    assert "delivered_by R1" in output
    assert "Invariant violations: 0" in output
    assert "Deadlocks resolved: 1" in output


def test_export_writes_complete_event_log(tmp_path, monkeypatch):
    demo = Demo("narrow_passage")
    demo.step()
    monkeypatch.chdir(tmp_path)
    demo.export_events()
    written = json.loads((tmp_path / "demo_events.json").read_text(encoding="utf-8"))
    assert written == demo.simulation.events_since(0)
