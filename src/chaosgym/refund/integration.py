"""Refund fixture and entry point for the shared scenario runner."""

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass

from chaosgym.core.context import RunContext
from chaosgym.ledger import Effect
from chaosgym.refund.agent import AgentVariant, run_agent
from chaosgym.refund.sandbox import Order, Sandbox
from chaosgym.tracing import Trace


@dataclass
class Services:
    get_order: Callable[[str], Order]
    send_email: Callable[[str], Effect]
    trace: Trace


@contextmanager
def fixture(context: RunContext):
    sandbox = Sandbox(ledger=context.ledger, trace=context.trace)
    get_order = context.register_tool("get_order", sandbox.get_order)
    send_email = context.register_tool("send_email", sandbox.send_email, tracks_commits=True)
    context.register_tool("refund_payment", sandbox.refund_payment, tracks_commits=True)
    context.state["services"] = Services(get_order, send_email, context.trace)
    yield


def run(
    context: RunContext,
    *,
    variant: str = "protected",
    order_id: str = "ORD-1042",
    request_id: str = "request-1042",
    max_attempts: int = 2,
) -> None:
    context.metadata.update(variant=variant, order_id=order_id, request_id=request_id)
    run_agent(
        context.state["services"],
        context.tool("refund_payment"),
        variant=AgentVariant(variant),
        order_id=order_id,
        request_id=request_id,
        max_attempts=max_attempts,
        record_tool_events=False,
    )
