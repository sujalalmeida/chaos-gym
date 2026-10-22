from dataclasses import FrozenInstanceError

import pytest

from chaosgym.ledger import Ledger


def test_ledger_records_distinct_commits_and_filters_by_resource():
    ledger = Ledger()
    first = ledger.commit("refund", "ORD-1042", "request-1", amount_minor=2500)
    second = ledger.commit("refund", "ORD-1042", "request-2", amount_minor=2500)
    ledger.commit("refund", "ORD-2000", "request-3", amount_minor=1000)
    ledger.commit("email", "ORD-1042", "message-1")

    assert ledger.find("refund", "ORD-1042") == (first, second)
    assert first.effect_id != second.effect_id
    assert ledger.find("refund", "missing") == ()


def test_committed_evidence_cannot_be_mutated():
    ledger = Ledger()
    effect = ledger.commit("refund", "ORD-1042", "request-1")
    snapshot = ledger.effects
    with pytest.raises(FrozenInstanceError):
        effect.resource_id = "changed"
    ledger.commit("email", "ORD-1042", "message-1")

    assert snapshot == (effect,)
    assert len(ledger.effects) == 2


def test_ledgers_do_not_share_state():
    ledger = Ledger()
    ledger.commit("refund", "ORD-1042", "request-1")
    assert Ledger().effects == ()
