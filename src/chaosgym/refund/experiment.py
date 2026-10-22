"""Convenience API for the refund scenario, using the shared runner."""

from chaosgym.core.models import RunResult
from chaosgym.core.runner import execute_scenario
from chaosgym.refund.agent import AgentVariant
from chaosgym.scenarios import (
    AssertionSpec,
    ExperimentSpec,
    FaultSpec,
    Limits,
    ScenarioSpec,
    TargetSpec,
)


def run_refund_experiment(
    variant: AgentVariant,
    *,
    order_id: str = "ORD-1042",
    request_id: str = "request-1042",
    on_call: int = 1,
    max_attempts: int = 2,
) -> RunResult:
    variant = AgentVariant(variant)
    if type(max_attempts) is not int or max_attempts < 1:
        raise ValueError("max_attempts must be a positive integer")
    if not request_id:
        raise ValueError("request_id must not be empty")
    spec = ScenarioSpec(
        project="refund-agent",
        target=TargetSpec(
            entrypoint="chaosgym.refund.integration:run",
            fixture="chaosgym.refund.integration:fixture",
            input=dict(
                variant=variant.value,
                order_id=order_id,
                request_id=request_id,
                max_attempts=max_attempts,
            ),
        ),
        scenario=ExperimentSpec(
            name="lost-refund-acknowledgment",
            fault=FaultSpec(
                target="tool:refund_payment", type="response_lost_after_commit", on_call=on_call
            ),
        ),
        assertions=(
            AssertionSpec(type="effect_count", effect="refund", resource_id=order_id, equals=1),
            AssertionSpec(type="effect_count", effect="email", resource_id=order_id, equals=1),
            AssertionSpec(type="confirmation_after_refund", resource_id=order_id),
            AssertionSpec(type="completed"),
        ),
        limits=Limits(max_tool_calls=max_attempts + 2),
    )
    return execute_scenario(spec)
