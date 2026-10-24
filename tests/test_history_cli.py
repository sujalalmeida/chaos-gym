import json

from typer.testing import CliRunner

from chaosgym.cli import app
from chaosgym.history import HistoryStore
from chaosgym.refund.experiment import run_refund_experiment
from chaosgym.reporting import write_report

runner = CliRunner()


def demo(root):
    result = runner.invoke(app, ["demo", "refund", "--output", str(root), "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def test_history_lists_real_runs_with_filters_and_pagination(tmp_path):
    unsafe, protected = demo(tmp_path)
    result = runner.invoke(
        app, ["history", "--root", str(tmp_path), "--status", "failed", "--json"]
    )
    assert result.exit_code == 0, result.output
    assert [row["run_id"] for row in json.loads(result.stdout)["runs"]] == [unsafe["run_id"]]
    result = runner.invoke(app, ["history", "--root", str(tmp_path), "--limit", "1", "--json"])
    assert json.loads(result.stdout)["runs"][0]["run_id"] == protected["run_id"]


def test_show_preserves_failed_outcome_without_rerunning_the_application(tmp_path):
    unsafe, _ = demo(tmp_path)
    original_paths = set(tmp_path.glob("run-*"))
    result = runner.invoke(app, ["show", unsafe["run_id"], "--root", str(tmp_path), "--json"])
    assert result.exit_code == 0, result.output
    run = json.loads(result.stdout)
    assert run["status"] == "failed"
    assert run["assertions"][0]["actual"] == 2
    assert set(tmp_path.glob("run-*")) == original_paths
    result = runner.invoke(app, ["show", "latest", "--root", str(tmp_path), "--trace"])
    assert result.exit_code == 0
    assert "fault_injected" in result.stdout


def test_existing_reports_are_discovered_when_the_index_is_missing(tmp_path):
    demo(tmp_path)
    HistoryStore(tmp_path).database.unlink()
    result = runner.invoke(app, ["history", "--root", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["rebuild"]["indexed"] == 2
    assert len(data["runs"]) == 2


def test_rebuild_reports_corrupt_artifacts_without_polluting_json_stdout(tmp_path):
    run = run_refund_experiment("protected")
    path = write_report(run, tmp_path)
    path.write_text('{"private-token":')
    result = runner.invoke(app, ["history", "--root", str(tmp_path), "--rebuild", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["runs"] == []
    assert data["rebuild"]["skipped"][0]["run_id"] == run.run_id
    assert "Skipped 1" in result.stderr
    assert "private-token" not in result.output


def test_invalid_or_missing_identifiers_fail_without_reading_arbitrary_files(tmp_path):
    for run_id in ("../escape", "run-" + "0" * 32, "latest"):
        result = runner.invoke(app, ["show", run_id, "--root", str(tmp_path)])
        assert result.exit_code == 2
    assert list(tmp_path.iterdir()) == []


def test_history_without_artifacts_is_read_only_and_configuration_errors_are_clear(tmp_path):
    root = tmp_path / "missing"
    result = runner.invoke(app, ["history", "--root", str(root), "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["runs"] == []
    assert not root.exists()
    result = runner.invoke(app, ["history", "--limit", "0"])
    assert result.exit_code == 2
