import signal
from pathlib import Path

import pytest

from chaosgym.core.supervisor import run_scenario
from chaosgym.scenarios import Limits
from tests.test_runner import scenario


def test_supervised_run_preserves_evidence_and_returns_a_successful_result():
    run = run_scenario(scenario(), module_root=Path.cwd())
    assert run.status == "passed"
    assert run.fault.activation_count == 1
    assert run.effects[-1].kind == "cleanup"


@pytest.mark.skipif(not hasattr(signal, "setitimer"), reason="POSIX deadline interrupt")
def test_deadline_interrupts_a_hung_application_and_runs_fixture_cleanup():
    spec = scenario(entrypoint="hang")
    spec = spec.model_copy(update={"limits": Limits(timeout_seconds=0.1)})
    run = run_scenario(spec)
    assert run.status == "failed"
    assert run.limit_violation == "timeout_seconds"
    assert run.effects[-1].kind == "cleanup"


def test_abrupt_worker_exit_is_an_infrastructure_error_without_invented_evidence():
    run = run_scenario(scenario(entrypoint="exit_worker"))
    assert run.status == "test_error"
    assert run.test_error == "supervision: WorkerFailure"
    assert run.effects == ()
    assert not run.fault.triggered


def test_application_output_does_not_leak_into_the_parent_stream(capfd):
    run = run_scenario(scenario(entrypoint="noisy"))
    captured = capfd.readouterr()
    assert run.status == "passed"
    assert "private application output" not in captured.out + captured.err


def test_uncooperative_worker_is_terminated_and_missing_evidence_is_explicit():
    spec = scenario(entrypoint="ignore_cancellation")
    spec = spec.model_copy(update={"limits": Limits(timeout_seconds=0.1)})
    run = run_scenario(spec)
    assert run.status == "test_error"
    assert run.test_error == "supervision: WorkerTimeout"
    assert run.limit_violation == "worker_timeout"
    assert run.effects == run.events == ()
