import json
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from chaosgym.cli import app

runner = CliRunner()


def initialized(tmp_path):
    path = tmp_path / "chaosgym.yaml"
    result = runner.invoke(app, ["init", "--path", str(path)])
    assert result.exit_code == 0, result.output
    return path


def test_initialize_writes_a_runnable_scenario_and_refuses_to_overwrite_it(tmp_path):
    path = initialized(tmp_path)
    original = path.read_bytes()
    assert runner.invoke(app, ["init", "--path", str(path)]).exit_code == 2
    assert path.read_bytes() == original
    result = runner.invoke(app, ["test", str(path), "--json", "--output", str(tmp_path / "runs")])
    assert result.exit_code == 0, result.output
    run = json.loads(result.output)
    assert run["status"] == "passed"
    assert run["tool_calls"] == 4
    assert Path(run["report_path"]).exists()


def test_yaml_can_select_the_unsafe_application_and_fail_the_same_assertion(tmp_path):
    path = initialized(tmp_path)
    path.write_text(path.read_text().replace("variant: protected", "variant: unsafe"))
    result = runner.invoke(app, ["test", str(path), "--json", "--output", str(tmp_path / "runs")])
    assert result.exit_code == 1
    assert json.loads(result.output)["assertions"][0]["actual"] == 2


def test_configuration_errors_never_start_a_worker_or_write_run_artifacts(tmp_path):
    path = initialized(tmp_path)
    path.write_text(path.read_text().replace("on_call: 1", "on_call: 0"))
    output = tmp_path / "runs"
    result = runner.invoke(app, ["test", str(path), "--output", str(output)])
    assert result.exit_code == 2
    assert "on_call" in result.output
    assert not output.exists()


def test_missing_registered_target_is_saved_as_a_test_error(tmp_path):
    path = initialized(tmp_path)
    path.write_text(path.read_text().replace("tool:refund_payment", "tool:missing"))
    result = runner.invoke(app, ["test", str(path), "--json", "--output", str(tmp_path / "runs")])
    assert result.exit_code == 2
    run = json.loads(result.output)
    assert run["status"] == "test_error"
    assert "not registered: missing" in run["test_error"]


def test_python_module_entrypoint_does_not_reenter_cli_when_spawning_worker(tmp_path):
    path = initialized(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "chaosgym", "test", str(path), "--json"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "passed"
