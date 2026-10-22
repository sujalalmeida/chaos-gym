"""Assertions over authoritative committed state."""

from dataclasses import dataclass
from enum import StrEnum

from chaosgym.ledger import Ledger


class AssertionStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class AssertionResult:
    name: str
    status: AssertionStatus
    expected: int
    actual: int | None
    effect_ids: tuple[str, ...]


def effect_count(
    ledger: Ledger | None, *, kind: str, resource_id: str, equals: int
) -> AssertionResult:
    if type(equals) is not int or equals < 0:
        raise ValueError("Expected effect count must be a nonnegative integer")
    name = f"effect_count({kind}, {resource_id}) == {equals}"
    if ledger is None:
        return AssertionResult(name, AssertionStatus.INCONCLUSIVE, equals, None, ())
    effects = ledger.find(kind, resource_id)
    actual = len(effects)
    status = AssertionStatus.PASSED if actual == equals else AssertionStatus.FAILED
    return AssertionResult(name, status, equals, actual, tuple(e.effect_id for e in effects))


def confirmation_after_refund(ledger: Ledger | None, *, resource_id: str) -> AssertionResult:
    name = f"confirmation_without_refund({resource_id}) == 0"
    if ledger is None:
        return AssertionResult(name, AssertionStatus.INCONCLUSIVE, 0, None, ())
    refunded = False
    violations = []
    for effect in ledger.effects:
        if effect.resource_id != resource_id:
            continue
        if effect.kind == "refund":
            refunded = True
        elif effect.kind == "email" and not refunded:
            violations.append(effect.effect_id)
    status = AssertionStatus.FAILED if violations else AssertionStatus.PASSED
    return AssertionResult(name, status, 0, len(violations), tuple(violations))
