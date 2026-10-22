"""Run outcomes keep fault activation separate from assertion success."""

from collections.abc import Sequence
from enum import StrEnum

from chaosgym.assertions import AssertionResult, AssertionStatus


class RunStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_TRIGGERED = "not_triggered"
    INCONCLUSIVE = "inconclusive"
    TEST_ERROR = "test_error"


def classify_run(
    *,
    triggered: bool,
    assertions: Sequence[AssertionResult],
    test_error: bool = False,
) -> RunStatus:
    if test_error:
        return RunStatus.TEST_ERROR
    if not triggered:
        return RunStatus.NOT_TRIGGERED
    if any(result.status == AssertionStatus.FAILED for result in assertions):
        return RunStatus.FAILED
    if not assertions or any(
        result.status == AssertionStatus.INCONCLUSIVE for result in assertions
    ):
        return RunStatus.INCONCLUSIVE
    return RunStatus.PASSED
