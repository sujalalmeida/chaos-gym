import pytest

from chaosgym.injectors.lost_ack import LostAcknowledgment
from chaosgym.refund.agent import AgentVariant, run_agent
from chaosgym.refund.sandbox import Sandbox


@pytest.mark.parametrize("variant,expected_refunds", [("unsafe", 2), ("protected", 1)])
def test_same_lost_ack_fault_exposes_unsafe_retry_and_preserves_protected_refund(
    variant, expected_refunds
):
    sandbox = Sandbox()
    tool = LostAcknowledgment(
        sandbox.refund_payment,
        name="refund_payment",
        ledger=sandbox.ledger,
        trace=sandbox.trace,
    )
    outcome = run_agent(
        sandbox, tool, variant=variant, order_id="ORD-1042", request_id="request-1042"
    )

    assert tool.triggered
    assert outcome.attempts == tool.attempts == 2
    assert len(sandbox.ledger.find("refund", "ORD-1042")) == expected_refunds
    assert len(sandbox.ledger.find("email", "ORD-1042")) == 1
    assert sandbox.ledger.effects[-1] == outcome.confirmation


@pytest.mark.parametrize("variant", list(AgentVariant))
def test_happy_path_commits_one_refund_and_one_confirmation(variant):
    sandbox = Sandbox()
    outcome = run_agent(
        sandbox,
        sandbox.refund_payment,
        variant=variant,
        order_id="ORD-1042",
        request_id="request-1042",
    )
    assert outcome.attempts == 1
    assert [effect.kind for effect in sandbox.ledger.effects] == ["refund", "email"]


def test_retry_exhaustion_terminates_without_a_confirmation():
    sandbox = Sandbox()
    calls = []

    def unavailable(*args, **kwargs):
        calls.append(kwargs)
        raise TimeoutError("Service unavailable")

    with pytest.raises(TimeoutError):
        run_agent(
            sandbox,
            unavailable,
            variant=AgentVariant.PROTECTED,
            order_id="ORD-1042",
            request_id="request-1042",
            max_attempts=3,
        )
    assert len(calls) == 3
    assert len({call["idempotency_key"] for call in calls}) == 1
    assert sandbox.ledger.effects == ()
    assert sandbox.trace.events[-1].event_type == "retries_exhausted"


def test_unknown_order_never_reaches_payment():
    sandbox = Sandbox()
    with pytest.raises(KeyError):
        run_agent(
            sandbox,
            sandbox.refund_payment,
            variant=AgentVariant.UNSAFE,
            order_id="missing",
            request_id="request-1042",
        )
    assert sandbox.ledger.effects == ()


@pytest.mark.parametrize("max_attempts", [0, -1, True])
def test_invalid_retry_limit_is_rejected_before_any_tool_call(max_attempts):
    sandbox = Sandbox()
    with pytest.raises(ValueError, match="positive integer"):
        run_agent(
            sandbox,
            sandbox.refund_payment,
            variant=AgentVariant.UNSAFE,
            order_id="ORD-1042",
            request_id="request-1042",
            max_attempts=max_attempts,
        )
    assert sandbox.trace.events == ()
