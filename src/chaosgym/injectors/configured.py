"""Deterministic faults for explicitly registered tools and simulated providers."""

from collections.abc import Callable
from time import sleep
from typing import Any

from chaosgym.core.context import RunContext, Tool
from chaosgym.injectors.lost_ack import AcknowledgmentLost
from chaosgym.ledger import Effect
from chaosgym.scenarios import FaultSpec
from chaosgym.tracing import Event


class RateLimitError(RuntimeError):
    status_code = 429


class ProviderUnavailable(ConnectionError):
    status_code = 503


class FaultInjector:
    def __init__(
        self, spec: FaultSpec, context: RunContext, *, sleeper: Callable[[float], None] = sleep
    ) -> None:
        self.spec = spec
        self.context = context
        self.name = spec.target.removeprefix("tool:")
        self.events: list[Event] = []
        self._sleep = sleeper
        try:
            tool = context.registration(self.name)
        except KeyError as error:
            raise ValueError(f"Fault target is not registered: {self.name}") from error
        if spec.type == "response_lost_after_commit" and not tool.tracks_commits:
            raise ValueError("Lost acknowledgment requires a ledger-backed tool")

    @property
    def triggered(self) -> bool:
        return bool(self.events)

    @property
    def attempts(self) -> int:
        return self.context.attempts.get(self.name, 0)

    def _activate(self, attempt: int, effect: Effect | None = None) -> None:
        self.events.append(
            self.context.trace.record(
                "fault_injected",
                self.name,
                attempt=attempt,
                effect_id=effect.effect_id if effect else None,
            )
        )

    def __call__(self, tool: Tool, attempt: int, args: tuple, kwargs: dict) -> Any:
        selected = (
            tool.name == self.name
            and self.spec.on_call <= attempt < self.spec.on_call + self.spec.times
        )
        if not selected:
            return tool.function(*args, **kwargs)

        if self.spec.type == "response_lost_after_commit":
            before = self.context.ledger.effects
            result = tool.function(*args, **kwargs)
            fresh = any(result is e for e in self.context.ledger.effects) and not any(
                result is e for e in before
            )
            if fresh:
                self._activate(attempt, result)
                raise AcknowledgmentLost(f"Acknowledgment lost for {tool.name}")
            return result

        if self.spec.type == "malformed_output":
            result = tool.function(*args, **kwargs)
            effect = result if any(result is e for e in self.context.ledger.effects) else None
            self._activate(attempt, effect)
            return "{invalid-json"

        self._activate(attempt)
        if self.spec.type == "timeout":
            raise TimeoutError(f"Injected timeout for {tool.name}")
        if self.spec.type == "rate_limit":
            raise RateLimitError(f"Injected rate limit for {tool.name}")
        if self.spec.type == "provider_outage":
            raise ProviderUnavailable(f"Injected outage for {tool.name}")
        self._sleep(self.spec.delay_seconds)
        self.context.check_limits()
        return tool.function(*args, **kwargs)
