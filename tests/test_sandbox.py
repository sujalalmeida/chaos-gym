import pytest

from chaosgym.refund.sandbox import Sandbox


def test_unprotected_retries_create_two_committed_refunds():
    sandbox = Sandbox()
    first = sandbox.refund_payment("ORD-1042", operation_id="attempt-1")
    second = sandbox.refund_payment("ORD-1042", operation_id="attempt-2")

    assert sandbox.ledger.find("refund", "ORD-1042") == (first, second)
    assert first.amount_minor == second.amount_minor == 2500


def test_stable_key_reuses_the_committed_effect():
    sandbox = Sandbox()
    first = sandbox.refund_payment(
        "ORD-1042", operation_id="attempt-1", idempotency_key="refund-request-1"
    )
    second = sandbox.refund_payment(
        "ORD-1042", operation_id="attempt-2", idempotency_key="refund-request-1"
    )

    assert second is first
    assert sandbox.ledger.find("refund", "ORD-1042") == (first,)
    assert sandbox.trace.events[-1].event_type == "idempotency_reused"


def test_key_cannot_be_reused_for_another_order():
    sandbox = Sandbox()
    sandbox.refund_payment("ORD-1042", operation_id="first", idempotency_key="same-key")
    with pytest.raises(ValueError, match="another order"):
        sandbox.refund_payment("ORD-2000", operation_id="second", idempotency_key="same-key")
    assert sandbox.ledger.find("refund", "ORD-2000") == ()


def test_distinct_refund_requests_are_not_deduplicated_by_order():
    sandbox = Sandbox()
    for request in ("request-1", "request-2"):
        sandbox.refund_payment("ORD-1042", operation_id=request, idempotency_key=request)
    assert len(sandbox.ledger.find("refund", "ORD-1042")) == 2


@pytest.mark.parametrize("order_id", ["ORD-1042", "missing"])
def test_email_cannot_commit_without_a_refund(order_id):
    sandbox = Sandbox()
    with pytest.raises((ValueError, KeyError)):
        sandbox.send_email(order_id)
    assert sandbox.ledger.effects == ()


def test_confirmation_is_recorded_after_the_refund():
    sandbox = Sandbox()
    refund = sandbox.refund_payment("ORD-1042", operation_id="request-1")
    email = sandbox.send_email("ORD-1042")
    assert sandbox.ledger.effects == (refund, email)


def test_unknown_order_never_commits_and_fixtures_are_isolated():
    sandbox = Sandbox()
    with pytest.raises(KeyError):
        sandbox.refund_payment("missing", operation_id="request-1")
    assert sandbox.ledger.effects == ()
    sandbox.refund_payment("ORD-1042", operation_id="request-1", idempotency_key="request-1")
    fresh = Sandbox()
    fresh.refund_payment("ORD-1042", operation_id="request-1", idempotency_key="request-1")
    assert len(fresh.ledger.effects) == 1
