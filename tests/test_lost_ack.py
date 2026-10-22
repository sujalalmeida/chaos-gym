import pytest

from chaosgym.injectors.lost_ack import AcknowledgmentLost, LostAcknowledgment
from chaosgym.ledger import Effect
from chaosgym.refund.sandbox import Sandbox


def wrap(sandbox, on_call=1, operation=None):
    return LostAcknowledgment(
        operation or sandbox.refund_payment,
        name="refund_payment",
        ledger=sandbox.ledger,
        trace=sandbox.trace,
        on_call=on_call,
    )


def test_acknowledgment_is_lost_only_after_the_commit():
    sandbox = Sandbox()
    tool = wrap(sandbox)
    with pytest.raises(AcknowledgmentLost):
        tool("ORD-1042", operation_id="request-1")

    (effect,) = sandbox.ledger.effects
    assert tool.triggered
    assert tool.fault_event.effect_id == effect.effect_id
    kinds = [event.event_type for event in sandbox.trace.events]
    assert kinds == ["tool_started", "effect_committed", "fault_injected", "tool_failed"]


def test_selected_attempt_fires_once_and_subsequent_calls_succeed():
    sandbox = Sandbox()
    tool = wrap(sandbox, on_call=2)
    tool("ORD-1042", operation_id="first")
    assert not tool.triggered
    with pytest.raises(AcknowledgmentLost):
        tool("ORD-1042", operation_id="second")
    tool("ORD-1042", operation_id="third")
    assert tool.attempts == 3
    assert len(sandbox.ledger.effects) == 3
    assert sum(event.event_type == "fault_injected" for event in sandbox.trace.events) == 1


def test_failed_operation_does_not_activate_fault():
    sandbox = Sandbox()
    tool = wrap(sandbox)
    with pytest.raises(KeyError):
        tool("missing", operation_id="request-1")
    assert not tool.triggered
    assert sandbox.ledger.effects == ()


def test_an_untracked_result_cannot_be_claimed_as_a_committed_fault():
    sandbox = Sandbox()
    tool = wrap(sandbox, operation=lambda: Effect("fake", "refund", "ORD-1042", "request-1"))
    tool()
    assert not tool.triggered
    assert sandbox.ledger.effects == ()


def test_idempotent_replay_does_not_claim_a_fresh_commit():
    sandbox = Sandbox()
    sandbox.refund_payment("ORD-1042", operation_id="first", idempotency_key="stable")
    tool = wrap(sandbox)
    tool("ORD-1042", operation_id="second", idempotency_key="stable")
    assert not tool.triggered
    assert len(sandbox.ledger.effects) == 1


def test_baseline_does_not_inject_a_fault():
    sandbox = Sandbox()
    tool = wrap(sandbox, on_call=None)
    tool("ORD-1042", operation_id="request-1")
    assert not tool.triggered


@pytest.mark.parametrize("on_call", [0, -1, True, 1.5])
def test_invalid_trigger_is_rejected(on_call):
    with pytest.raises(ValueError, match="positive integer"):
        wrap(Sandbox(), on_call=on_call)
