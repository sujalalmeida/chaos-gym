import json
import os
from dataclasses import replace

import pytest

from chaosgym import reporting
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
