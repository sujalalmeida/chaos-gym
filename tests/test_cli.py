import json

import pytest
from typer.testing import CliRunner

from chaosgym.cli import app

runner = CliRunner()


def test_default_demo_proves_the_expected_failure_and_recovery(tmp_path):
    result = runner.invoke(app, ["demo", "refund", "--json", "--output", str(tmp_path)])
    assert result.exit_code == 0, result.output
    unsafe, protected = json.loads(result.output)
    assert (unsafe["status"], protected["status"]) == ("failed", "passed")
    assert (unsafe["assertions"][0]["actual"], protected["assertions"][0]["actual"]) == (2, 1)
    assert len(list(tmp_path.glob("run-*/report.json"))) == 2


@pytest.mark.parametrize("variant,exit_code", [("unsafe", 1), ("protected", 0)])
def test_single_variant_exit_codes_reflect_assertions(tmp_path, variant, exit_code):
    result = runner.invoke(
        app, ["demo", "refund", "--variant", variant, "--output", str(tmp_path), "--trace"]
    )
    assert result.exit_code == exit_code
    assert "fault_injected" in result.output
    assert "effect_count" in result.output


def test_untriggered_fault_is_nonzero_even_when_the_workflow_succeeds(tmp_path):
    result = runner.invoke(
        app, ["demo", "refund", "--on-call", "2", "--json", "--output", str(tmp_path)]
    )
    assert result.exit_code == 3
    assert all(run["status"] == "not_triggered" for run in json.loads(result.output))


def test_incomplete_before_after_proof_is_not_a_success(tmp_path):
    result = runner.invoke(
        app, ["demo", "refund", "--max-attempts", "1", "--output", str(tmp_path)]
    )
    assert result.exit_code == 1


@pytest.mark.parametrize("arguments", [["--on-call", "0"], ["--variant", "unknown"]])
def test_invalid_arguments_do_not_create_artifacts(tmp_path, arguments):
    result = runner.invoke(app, ["demo", "refund", "--output", str(tmp_path), *arguments])
    assert result.exit_code == 2
    assert list(tmp_path.iterdir()) == []


def test_artifact_storage_errors_exit_as_test_errors(tmp_path):
    output = tmp_path / "file"
    output.write_text("not a directory")
    result = runner.invoke(app, ["demo", "refund", "--output", str(output)])
    assert result.exit_code == 2
    assert "Test error:" in result.output
