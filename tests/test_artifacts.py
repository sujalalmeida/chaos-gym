import json

import pytest

from chaosgym.artifacts import ArtifactError, read_report, report_path
from chaosgym.refund.experiment import run_refund_experiment
from chaosgym.reporting import write_report


def test_saved_evidence_round_trips_without_running_the_application(tmp_path):
    run = run_refund_experiment("protected")
    path = write_report(run, tmp_path)
    assert read_report(path, expected_run_id=run.run_id) == run


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 2),
        ("created_at", "2026-10-24T10:00:00"),
        ("duration_ms", -1),
        ("status", "unknown"),
        ("run_id", "../escape"),
    ],
)
def test_invalid_saved_metadata_is_rejected(tmp_path, field, value):
    path = write_report(run_refund_experiment("unsafe"), tmp_path)
    data = json.loads(path.read_text())
    data[field] = value
    path.write_text(json.dumps(data))
    with pytest.raises(ArtifactError):
        read_report(path)


def test_report_cannot_impersonate_another_run_directory(tmp_path):
    path = write_report(run_refund_experiment("protected"), tmp_path)
    with pytest.raises(ArtifactError, match="does not match"):
        read_report(path, expected_run_id="run-" + "0" * 32)


def test_broken_evidence_links_are_rejected(tmp_path):
    path = write_report(run_refund_experiment("protected"), tmp_path)
    data = json.loads(path.read_text())
    data["effects"] = []
    path.write_text(json.dumps(data))
    with pytest.raises(ArtifactError, match="missing committed effect"):
        read_report(path)


def test_corrupt_reports_do_not_echo_raw_payloads_in_errors(tmp_path):
    path = tmp_path / "report.json"
    path.write_text('{"private-token":')
    with pytest.raises(ArtifactError) as error:
        read_report(path)
    assert "private-token" not in str(error.value)


def test_paths_cannot_escape_the_run_root_or_follow_artifact_symlinks(tmp_path):
    with pytest.raises(ArtifactError):
        report_path(tmp_path, "../escape")
    run = run_refund_experiment("protected")
    path = write_report(run, tmp_path / "original")
    other = tmp_path / "other"
    other.mkdir()
    (other / run.run_id).symlink_to(path.parent, target_is_directory=True)
    with pytest.raises(ArtifactError, match="symbolic"):
        report_path(other, run.run_id)
