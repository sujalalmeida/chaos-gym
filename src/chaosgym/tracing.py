"""Ordered trace metadata without application payload capture."""

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic


@dataclass(frozen=True)
class Event:
    event_id: str
    event_type: str
    operation: str
    elapsed_ms: float
    attempt: int | None = None
    effect_id: str | None = None


class Trace:
    def __init__(self, clock: Callable[[], float] = monotonic) -> None:
        self._clock = clock
        self._started = clock()
        self._events: list[Event] = []

    @property
    def events(self) -> tuple[Event, ...]:
        return tuple(self._events)

    def record(
        self,
        event_type: str,
        operation: str,
        *,
        attempt: int | None = None,
        effect_id: str | None = None,
    ) -> Event:
        event = Event(
            event_id=f"evt-{len(self._events) + 1:04d}",
            event_type=event_type,
            operation=operation,
            elapsed_ms=round((self._clock() - self._started) * 1000, 3),
            attempt=attempt,
            effect_id=effect_id,
        )
        self._events.append(event)
        return event
