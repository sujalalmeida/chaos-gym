import json
import os
from dataclasses import replace

import pytest

from chaosgym import reporting
from chaosgym.history import HistoryError, HistoryStore
from chaosgym.refund.experiment import run_refund_experiment


def test_saved_report_and_event_stream_preserve_execution_evidence(tmp_path):
    run = run_refund_experiment("unsafe")
    path = reporting.write_report(run, tmp_path)
    data = json.loads(path.read_text())
    events = [json.loads(line) for line in path.with_name("events.jsonl").read_text().splitlines()]

    assert data["schema_version"] == 1
    assert data["run_id"] == run.run_id
    assert data["status"] == "failed"
    assert data["assertions"][0]["actual"] == 2
    assert events == data["events"]
    fault = next(event for event in events if event["event_id"] == data["fault"]["event_id"])
    assert fault["effect_id"] in {effect["effect_id"] for effect in data["effects"]}
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700


def test_report_does_not_overwrite_an_existing_run(tmp_path):
    run = run_refund_experiment("protected")
    path = reporting.write_report(run, tmp_path)
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        reporting.write_report(run, tmp_path)
    assert path.read_bytes() == original


def test_failed_write_does_not_publish_partial_artifacts(tmp_path, monkeypatch):
    run = run_refund_experiment("protected")

    def disk_full(*args):
        raise OSError("Disk full")

    monkeypatch.setattr(reporting, "_write_private", disk_full)
    with pytest.raises(OSError):
        reporting.write_report(run, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_run_identifier_cannot_escape_the_artifact_directory(tmp_path):
    run = replace(run_refund_experiment("protected"), run_id="../escape")
    with pytest.raises(ValueError, match="identifier"):
        reporting.write_report(run, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_successfully_published_reports_are_available_in_history(tmp_path):
    run = run_refund_experiment("protected")
    path = reporting.write_report(run, tmp_path)
    (summary,) = HistoryStore(tmp_path).list_runs()
    assert summary.run_id == run.run_id
    assert summary.status == run.status
    assert path.exists()


def test_index_failure_does_not_discard_evidence_or_change_the_run_outcome(tmp_path, monkeypatch):
    run = run_refund_experiment("protected")

    def unavailable(*args):
        raise HistoryError("Database unavailable")

    monkeypatch.setattr(HistoryStore, "index", unavailable)
    with pytest.warns(reporting.HistoryIndexWarning, match="Report saved"):
        path = reporting.write_report(run, tmp_path)
    assert json.loads(path.read_text())["status"] == "passed"
    assert path.with_name("events.jsonl").exists()


def test_history_can_be_recovered_entirely_from_saved_reports(tmp_path):
    runs = [run_refund_experiment(variant) for variant in ("unsafe", "protected")]
    for run in runs:
        reporting.write_report(run, tmp_path)
    store = HistoryStore(tmp_path)
    store.database.unlink()
    assert store.rebuild().indexed == 2
    assert {row.run_id for row in store.list_runs()} == {run.run_id for run in runs}
