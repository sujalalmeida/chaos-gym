"""Execute one isolated refund experiment and retain its evidence."""

from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from uuid import uuid4

from chaosgym.assertions import (
    AssertionResult,
    AssertionStatus,
    confirmation_after_refund,
    effect_count,
)
from chaosgym.injectors.lost_ack import LostAcknowledgment
from chaosgym.ledger import Effect
from chaosgym.refund.agent import AgentVariant, run_agent
from chaosgym.refund.sandbox import Sandbox
from chaosgym.results import RunStatus, classify_run
from chaosgym.tracing import Event


@dataclass(frozen=True)
class FaultResult:
    type: str
    target: str
    on_call: int
    target_reached: bool
    triggered: bool
    attempts: int
    event_id: str | None


@dataclass(frozen=True)
class RunResult:
    schema_version: int
    run_id: str
    created_at: str
    duration_ms: float
    scenario: str
    variant: AgentVariant
    order_id: str
    request_id: str
    status: RunStatus
    completed: bool
    application_error: str | None
    fault: FaultResult
    assertions: tuple[AssertionResult, ...]
    effects: tuple[Effect, ...]
    events: tuple[Event, ...]


def run_refund_experiment(
    variant: AgentVariant,
    *,
    order_id: str = "ORD-1042",
    request_id: str = "request-1042",
    on_call: int = 1,
    max_attempts: int = 2,
) -> RunResult:
    variant = AgentVariant(variant)
    if type(on_call) is not int or on_call < 1:
        raise ValueError("on_call must be a positive integer")
    if type(max_attempts) is not int or max_attempts < 1:
        raise ValueError("max_attempts must be a positive integer")
    if not request_id:
        raise ValueError("request_id must not be empty")
    started = monotonic()
    created_at = datetime.now(UTC).isoformat()
    sandbox = Sandbox()
    tool = LostAcknowledgment(
        sandbox.refund_payment,
        name="refund_payment",
        ledger=sandbox.ledger,
        trace=sandbox.trace,
        on_call=on_call,
    )
    completed = False
    application_error = None
    try:
        run_agent(
            sandbox,
            tool,
            variant=variant,
            order_id=order_id,
            request_id=request_id,
            max_attempts=max_attempts,
        )
        completed = True
    except Exception as error:
        # Keep application payloads and exception messages out of saved telemetry.
        application_error = type(error).__name__
        sandbox.trace.record("application_failed", "refund_agent")

    assertions = (
        effect_count(sandbox.ledger, kind="refund", resource_id=order_id, equals=1),
        effect_count(sandbox.ledger, kind="email", resource_id=order_id, equals=1),
        confirmation_after_refund(sandbox.ledger, resource_id=order_id),
        AssertionResult(
            "application_completed == 1",
            AssertionStatus.PASSED if completed else AssertionStatus.FAILED,
            1,
            int(completed),
            (),
        ),
    )
    status = classify_run(triggered=tool.triggered, assertions=assertions)
    return RunResult(
        schema_version=1,
        run_id=f"run-{uuid4().hex}",
        created_at=created_at,
        duration_ms=round((monotonic() - started) * 1000, 3),
        scenario="lost-refund-acknowledgment",
        variant=variant,
        order_id=order_id,
        request_id=request_id,
        status=status,
        completed=completed,
        application_error=application_error,
        fault=FaultResult(
            type="response_lost_after_commit",
            target="tool:refund_payment",
            on_call=on_call,
            target_reached=tool.attempts > 0,
            triggered=tool.triggered,
            attempts=tool.attempts,
            event_id=tool.fault_event.event_id if tool.fault_event else None,
        ),
        assertions=assertions,
        effects=sandbox.ledger.effects,
        events=sandbox.trace.events,
    )
