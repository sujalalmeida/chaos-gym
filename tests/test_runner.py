import pytest

from chaosgym.core.runner import execute_scenario
from chaosgym.scenarios import (
    AssertionSpec,
    ExperimentSpec,
    FaultSpec,
    Limits,
    ScenarioSpec,
    TargetSpec,
)


def scenario(entrypoint="recover", fixture="fixture", *, fault="timeout", calls=15, on_call=1):
    return ScenarioSpec(
        project="custom-app",
        target=TargetSpec(
            entrypoint=f"tests.runner_fixtures:{entrypoint}",
            fixture=f"tests.runner_fixtures:{fixture}",
        ),
        scenario=ExperimentSpec(
            name="custom-test",
            fault=FaultSpec(
                target="tool:operation",
                type=fault,
                on_call=on_call,
            ),
        ),
        assertions=(AssertionSpec(type="completed"),),
        limits=Limits(max_tool_calls=calls),
    )


def test_custom_application_uses_python_assertions_and_always_closes_fixture():
    run = execute_scenario(scenario())
    assert run.status == "passed"
    assert run.tool_calls == 2
    assert len(run.assertions) == 2
    assert run.effects[-1].kind == "cleanup"
    assert run.events[-1].event_type == "fixture_closed"
    assert run.variant is None


@pytest.mark.parametrize(
    "fixture,stage", [("broken_setup", "setup"), ("broken_teardown", "teardown")]
)
def test_infrastructure_errors_are_distinct_from_application_failures(fixture, stage):
    run = execute_scenario(scenario(fixture=fixture))
    assert run.status == "test_error"
    assert run.test_error == f"{stage}: RuntimeError"
    assert "private" not in run.test_error


def test_application_crash_retains_commit_evidence_and_closes_fixture():
    run = execute_scenario(scenario(entrypoint="crash", fault="response_lost_after_commit"))
    assert run.status == "failed"
    assert run.application_error == "AcknowledgmentLost"
    assert run.test_error is None
    assert [effect.kind for effect in run.effects] == ["work", "cleanup"]


def test_unreached_target_is_not_a_passing_test():
    run = execute_scenario(scenario(entrypoint="skip"))
    assert run.status == "not_triggered"
    assert not run.fault.target_reached


def test_retry_storm_stops_at_the_shared_call_budget_and_closes_fixture():
    run = execute_scenario(scenario(entrypoint="loop", calls=3))
    assert run.status == "failed"
    assert run.limit_violation == "max_tool_calls"
    assert run.tool_calls == 3
    assert not run.completed
    assert run.effects[-1].kind == "cleanup"


def test_missing_target_is_a_helpful_setup_error_and_fixture_still_closes():
    spec = scenario()
    spec = spec.model_copy(
        update={
            "scenario": ExperimentSpec(
                name="invalid-target", fault=FaultSpec(target="tool:missing", type="timeout")
            )
        }
    )
    run = execute_scenario(spec)
    assert run.status == "test_error"
    assert "not registered: missing" in run.test_error
    assert run.effects[-1].kind == "cleanup"


def test_invalid_entrypoint_input_is_a_setup_error():
    spec = scenario()
    spec = spec.model_copy(
        update={"target": spec.target.model_copy(update={"input": {"unknown": 1}})}
    )
    run = execute_scenario(spec)
    assert run.status == "test_error"
    assert "target.input" in run.test_error
