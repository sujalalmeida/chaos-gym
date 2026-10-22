"""Scripted workflows differing only in their payment retry protection."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from chaosgym.ledger import Effect
from chaosgym.refund.sandbox import Sandbox


class AgentVariant(StrEnum):
    UNSAFE = "unsafe"
    PROTECTED = "protected"


class RefundTool(Protocol):
    def __call__(
        self,
        order_id: str,
        *,
        operation_id: str,
        idempotency_key: str | None = None,
    ) -> Effect: ...


@dataclass(frozen=True)
class AgentOutcome:
    refund: Effect
    confirmation: Effect
    attempts: int


def run_agent(
    sandbox: Sandbox,
    refund: RefundTool,
    *,
    variant: AgentVariant,
    order_id: str,
    request_id: str,
    max_attempts: int = 2,
) -> AgentOutcome:
    variant = AgentVariant(variant)
    if type(max_attempts) is not int or max_attempts < 1:
        raise ValueError("max_attempts must be a positive integer")
    if not request_id:
        raise ValueError("request_id must not be empty")

    sandbox.trace.record("tool_started", "get_order")
    sandbox.get_order(order_id)
    sandbox.trace.record("tool_completed", "get_order")
    key = f"refund:{request_id}" if variant == AgentVariant.PROTECTED else None

    for attempt in range(1, max_attempts + 1):
        try:
            committed = refund(
                order_id,
                operation_id=f"{request_id}:attempt-{attempt}",
                idempotency_key=key,
            )
        except TimeoutError:
            if attempt == max_attempts:
                sandbox.trace.record("retries_exhausted", "refund_payment", attempt=attempt)
                raise
            sandbox.trace.record("retry_scheduled", "refund_payment", attempt=attempt)
        else:
            sandbox.trace.record("tool_started", "send_email")
            confirmation = sandbox.send_email(order_id)
            sandbox.trace.record("tool_completed", "send_email", effect_id=confirmation.effect_id)
            return AgentOutcome(committed, confirmation, attempt)

    raise AssertionError("Retry loop ended without a result or exception")
