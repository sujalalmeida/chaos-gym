"""Scripted workflows differing only in their payment retry protection."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from chaosgym.ledger import Effect
from chaosgym.refund.sandbox import Order
from chaosgym.tracing import Trace


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


class RefundServices(Protocol):
    trace: Trace

    def get_order(self, order_id: str) -> Order: ...

    def send_email(self, order_id: str) -> Effect: ...


@dataclass(frozen=True)
class AgentOutcome:
    refund: Effect
    confirmation: Effect
    attempts: int


def run_agent(
    sandbox: RefundServices,
    refund: RefundTool,
    *,
    variant: AgentVariant,
    order_id: str,
    request_id: str,
    max_attempts: int = 2,
    record_tool_events: bool = True,
) -> AgentOutcome:
    variant = AgentVariant(variant)
    if type(max_attempts) is not int or max_attempts < 1:
        raise ValueError("max_attempts must be a positive integer")
    if not request_id:
        raise ValueError("request_id must not be empty")

    if record_tool_events:
        sandbox.trace.record("tool_started", "get_order")
    sandbox.get_order(order_id)
    if record_tool_events:
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
            if not isinstance(committed, Effect):
                raise ValueError("Refund tool returned an invalid result")
            if record_tool_events:
                sandbox.trace.record("tool_started", "send_email")
            confirmation = sandbox.send_email(order_id)
            if record_tool_events:
                sandbox.trace.record(
                    "tool_completed", "send_email", effect_id=confirmation.effect_id
                )
            return AgentOutcome(committed, confirmation, attempt)

    raise AssertionError("Retry loop ended without a result or exception")
