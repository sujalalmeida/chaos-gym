"""Shared, additive version-one run artifact models."""

from dataclasses import dataclass

from chaosgym.assertions import AssertionResult
from chaosgym.ledger import Effect
from chaosgym.results import RunStatus
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
    activation_count: int = 0
    times: int = 1
    delay_seconds: float | None = None


@dataclass(frozen=True)
class RunResult:
    schema_version: int
    run_id: str
    created_at: str
    duration_ms: float
    scenario: str
    variant: str | None
    order_id: str | None
    request_id: str | None
    status: RunStatus
    completed: bool
    application_error: str | None
    fault: FaultResult
    assertions: tuple[AssertionResult, ...]
    effects: tuple[Effect, ...]
    events: tuple[Event, ...]
    project: str | None = None
    test_error: str | None = None
    tool_calls: int = 0
    limit_violation: str | None = None
    entrypoint: str | None = None
    fixture: str | None = None
    limits: dict[str, int | float] | None = None
