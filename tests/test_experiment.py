import pytest

from chaosgym.assertions import AssertionResult, AssertionStatus
from chaosgym.refund.experiment import run_refund_experiment
from chaosgym.results import RunStatus, classify_run


@pytest.mark.parametrize(
    "variant,status,refunds", [("unsafe", "failed", 2), ("protected", "passed", 1)]
)
def test_experiment_derives_outcome_and_links_fault_to_committed_evidence(variant, status, refunds):
    run = run_refund_experiment(variant)
    assert run.status == status
    assert run.completed
    assert run.fault.triggered
    assert run.fault.attempts == 2
    assert run.assertions[0].actual == refunds
    fault = next(event for event in run.events if event.event_id == run.fault.event_id)
    assert fault.effect_id in {effect.effect_id for effect in run.effects}


def test_unreached_trigger_does_not_pass_even_when_all_assertions_pass():
    run = run_refund_experiment("protected", on_call=2)
    assert run.fault.target_reached
    assert not run.fault.triggered
    assert all(result.status == "passed" for result in run.assertions)
    assert run.status == RunStatus.NOT_TRIGGERED


def test_application_that_never_reaches_target_is_not_a_resilience_pass():
    run = run_refund_experiment("protected", order_id="missing")
    assert run.status == RunStatus.NOT_TRIGGERED
    assert not run.fault.target_reached
    assert not run.completed
    assert run.application_error == "KeyError"
    assert run.effects == ()


def test_no_retry_after_lost_ack_still_fails_completion_and_confirmation_assertions():
    run = run_refund_experiment("protected", max_attempts=1)
    assert run.status == RunStatus.FAILED
    assert run.assertions[0].status == "passed"
    assert not run.completed
    assert run.application_error == "AcknowledgmentLost"
    assert run.assertions[1].actual == 0


def test_repeated_experiments_have_fresh_state_and_stable_semantic_evidence():
    first = run_refund_experiment("unsafe")
    second = run_refund_experiment("unsafe")
    assert first.run_id != second.run_id
    assert first.effects == second.effects
    assert first.assertions == second.assertions
    assert first.fault == second.fault
    assert [(e.event_type, e.effect_id) for e in first.events] == [
        (e.event_type, e.effect_id) for e in second.events
    ]


def test_refund_demo_counts_each_registered_tool_call_once():
    run = run_refund_experiment("protected")
    started = [event for event in run.events if event.event_type == "tool_started"]
    assert run.tool_calls == len(started) == 4
    assert [event.operation for event in started] == [
        "get_order",
        "refund_payment",
        "refund_payment",
        "send_email",
    ]
    assert run.fault.activation_count == 1


@pytest.mark.parametrize(
    "triggered,assertions,test_error,status",
    [
        (True, [], False, "inconclusive"),
        (False, [], False, "not_triggered"),
        (False, [], True, "test_error"),
        (True, [AssertionStatus.PASSED], False, "passed"),
        (True, [AssertionStatus.INCONCLUSIVE], False, "inconclusive"),
        (True, [AssertionStatus.INCONCLUSIVE, AssertionStatus.FAILED], False, "failed"),
        (True, [AssertionStatus.FAILED], True, "test_error"),
    ],
)
def test_run_classification(triggered, assertions, test_error, status):
    evidence = [AssertionResult("check", state, 1, None, ()) for state in assertions]
    assert classify_run(triggered=triggered, assertions=evidence, test_error=test_error) == status
