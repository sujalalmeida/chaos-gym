import pytest

from chaosgym.core.context import RunContext, RunLimitExceeded
from chaosgym.injectors.configured import FaultInjector, ProviderUnavailable, RateLimitError
from chaosgym.injectors.lost_ack import AcknowledgmentLost
from chaosgym.scenarios import FaultSpec, Limits


def configured(kind, *, times=1, tracked=False, sleeper=lambda seconds: None, delay=None):
    context = RunContext(Limits())
    calls = []

    def operation():
        calls.append(1)
        return context.ledger.commit("refund", "order", f"attempt-{len(calls)}")

    wrapped = context.register_tool("payment", operation, tracks_commits=tracked)
    spec = FaultSpec(target="tool:payment", type=kind, times=times, delay_seconds=delay)
    injector = FaultInjector(spec, context, sleeper=sleeper)
    context.interceptor = injector
    return context, wrapped, injector, calls


@pytest.mark.parametrize(
    "kind,error",
    [
        ("timeout", TimeoutError),
        ("rate_limit", RateLimitError),
        ("provider_outage", ProviderUnavailable),
    ],
)
def test_pre_execution_fault_does_not_commit_and_retry_can_recover(kind, error):
    context, wrapped, fault, calls = configured(kind)
    with pytest.raises(error):
        wrapped()
    assert fault.triggered
    assert calls == []
    assert context.ledger.effects == ()
    effect = wrapped()
    assert context.ledger.effects == (effect,)
    assert fault.attempts == 2
    assert len(fault.events) == 1


def test_lost_ack_is_linked_to_the_commit_before_the_caller_times_out():
    context, wrapped, fault, calls = configured("response_lost_after_commit", tracked=True)
    with pytest.raises(AcknowledgmentLost):
        wrapped()
    assert calls == [1]
    assert fault.events[0].effect_id == context.ledger.effects[0].effect_id
    wrapped()
    assert len(context.ledger.effects) == 2


def test_lost_ack_rejects_a_target_without_commit_tracking():
    with pytest.raises(ValueError, match="ledger-backed"):
        configured("response_lost_after_commit")


def test_malformed_output_changes_the_response_but_preserves_committed_state():
    context, wrapped, fault, _ = configured("malformed_output")
    assert wrapped() == "{invalid-json"
    assert len(context.ledger.effects) == 1
    assert fault.events[0].effect_id == context.ledger.effects[0].effect_id


def test_slow_response_delays_before_execution_and_records_activation():
    slept = []
    context, wrapped, fault, calls = configured("slow_response", sleeper=slept.append, delay=0.1)
    wrapped()
    assert slept == [0.1]
    assert calls == [1]
    assert fault.triggered


def test_delay_that_exhausts_budget_prevents_the_operation_from_committing():
    context, wrapped, fault, calls = configured("slow_response", delay=0.1)
    fault._sleep = lambda seconds: context.exceed_limit("timeout_seconds")
    with pytest.raises(RunLimitExceeded):
        wrapped()
    assert fault.triggered
    assert calls == []
    assert context.ledger.effects == ()


def test_repeated_faults_cover_exactly_the_configured_attempt_window():
    context, wrapped, fault, calls = configured("timeout", times=3)
    for _ in range(3):
        with pytest.raises(TimeoutError):
            wrapped()
    wrapped()
    assert [event.attempt for event in fault.events] == [1, 2, 3]
    assert calls == [1]
    assert context.tool_calls == 4


def test_faults_do_not_affect_unselected_tools_or_claim_replayed_commits():
    context = RunContext(Limits())
    effect = context.ledger.commit("refund", "order", "original")
    wrapped = context.register_tool("payment", lambda: effect, tracks_commits=True)
    other = context.register_tool("other", lambda: "untouched")
    fault = FaultInjector(
        FaultSpec(target="tool:payment", type="response_lost_after_commit"), context
    )
    context.interceptor = fault
    assert other() == "untouched"
    assert wrapped() is effect
    assert not fault.triggered
