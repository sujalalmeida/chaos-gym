import pytest

from chaosgym.assertions import AssertionStatus, confirmation_after_refund, effect_count
from chaosgym.ledger import Ledger


@pytest.mark.parametrize("commits,expected_status", [(0, "failed"), (1, "passed"), (2, "failed")])
def test_exactly_one_refund_uses_committed_state(commits, expected_status):
    ledger = Ledger()
    for attempt in range(commits):
        ledger.commit("refund", "ORD-1042", f"attempt-{attempt}")
    ledger.commit("refund", "other-order", "unrelated")
    result = effect_count(ledger, kind="refund", resource_id="ORD-1042", equals=1)

    assert result.status == expected_status
    assert result.actual == commits
    assert len(result.effect_ids) == commits


def test_missing_evidence_is_inconclusive_rather_than_zero_commits():
    result = effect_count(None, kind="refund", resource_id="ORD-1042", equals=0)
    assert result.status == AssertionStatus.INCONCLUSIVE
    assert result.actual is None


def test_email_before_refund_fails_even_if_a_refund_commits_later():
    ledger = Ledger()
    early = ledger.commit("email", "ORD-1042", "early")
    ledger.commit("refund", "ORD-1042", "refund")
    ledger.commit("email", "ORD-1042", "late")
    result = confirmation_after_refund(ledger, resource_id="ORD-1042")
    assert result.status == AssertionStatus.FAILED
    assert result.effect_ids == (early.effect_id,)


def test_another_orders_refund_cannot_justify_confirmation():
    ledger = Ledger()
    ledger.commit("refund", "other-order", "unrelated")
    ledger.commit("email", "ORD-1042", "confirmation")
    assert confirmation_after_refund(ledger, resource_id="ORD-1042").actual == 1


def test_email_assertion_handles_missing_evidence_and_valid_ordering():
    assert confirmation_after_refund(None, resource_id="ORD-1042").status == "inconclusive"
    ledger = Ledger()
    ledger.commit("refund", "ORD-1042", "refund")
    ledger.commit("email", "ORD-1042", "confirmation")
    assert confirmation_after_refund(ledger, resource_id="ORD-1042").status == "passed"
