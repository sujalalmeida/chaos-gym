"""Suppress a selected response only after verifying a fresh ledger commit."""

from collections.abc import Callable
from typing import Generic, ParamSpec

from chaosgym.ledger import Effect, Ledger
from chaosgym.tracing import Event, Trace

P = ParamSpec("P")


class AcknowledgmentLost(TimeoutError):
    """The sandbox committed, but the caller did not receive the response."""


class LostAcknowledgment(Generic[P]):
    def __init__(
        self,
        operation: Callable[P, Effect],
        *,
        name: str,
        ledger: Ledger,
        trace: Trace,
        on_call: int | None = 1,
    ) -> None:
        if on_call is not None and (type(on_call) is not int or on_call < 1):
            raise ValueError("on_call must be a positive integer or None")
        self._operation = operation
        self._name = name
        self._ledger = ledger
        self._trace = trace
        self.on_call = on_call
        self.attempts = 0
        self.fault_event: Event | None = None

    @property
    def triggered(self) -> bool:
        return self.fault_event is not None

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Effect:
        self.attempts += 1
        attempt = self.attempts
        before = self._ledger.effects
        self._trace.record("tool_started", self._name, attempt=attempt)
        try:
            result = self._operation(*args, **kwargs)
        except Exception:
            self._trace.record("tool_failed", self._name, attempt=attempt)
            raise

        fresh_commit = any(result is effect for effect in self._ledger.effects) and not any(
            result is effect for effect in before
        )
        if attempt == self.on_call and fresh_commit:
            self.fault_event = self._trace.record(
                "fault_injected", self._name, attempt=attempt, effect_id=result.effect_id
            )
            self._trace.record("tool_failed", self._name, attempt=attempt)
            raise AcknowledgmentLost(f"Acknowledgment lost for {self._name}")

        self._trace.record(
            "tool_completed", self._name, attempt=attempt, effect_id=result.effect_id
        )
        return result
