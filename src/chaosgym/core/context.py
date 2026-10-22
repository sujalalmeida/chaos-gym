"""Explicit tool registration, run-local state, and execution budgets."""

import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import Any, ParamSpec, TypeVar

from chaosgym.assertions import AssertionResult
from chaosgym.ledger import Ledger
from chaosgym.scenarios import Limits
from chaosgym.tracing import Trace

P = ParamSpec("P")
R = TypeVar("R")


class RunLimitExceeded(BaseException):
    """Control signal kept separate from application/tool exceptions."""


@dataclass(frozen=True)
class Tool:
    name: str
    function: Callable[..., Any]
    tracks_commits: bool


class RunContext:
    def __init__(self, limits: Limits, *, clock: Callable[[], float] = monotonic) -> None:
        self.ledger = Ledger()
        self.trace = Trace(clock)
        self.state: dict[str, Any] = {}
        self.metadata: dict[str, str] = {}
        self.limits = limits
        self.tool_calls = 0
        self.limit_violation: str | None = None
        self._clock = clock
        self._deadline = clock() + limits.timeout_seconds
        self._tools: dict[str, Tool] = {}
        self._wrappers: dict[str, Callable[..., Any]] = {}
        self.python_assertions: list[Callable[[RunContext], AssertionResult]] = []
        self.interceptor: Callable[[Tool, int, tuple, dict], Any] | None = None
        self.attempts: dict[str, int] = {}

    def check_limits(self) -> None:
        if self.limit_violation is not None:
            raise RunLimitExceeded(self.limit_violation)
        if self._clock() >= self._deadline:
            self.exceed_limit("timeout_seconds")

    def exceed_limit(self, name: str) -> None:
        if self.limit_violation is None:
            self.limit_violation = name
            self.trace.record("limit_exceeded", name)
        raise RunLimitExceeded(name)

    def register_tool(
        self, name: str, function: Callable[P, R], *, tracks_commits: bool = False
    ) -> Callable[P, R]:
        if re.fullmatch(r"[A-Za-z_][\w.-]*", name) is None:
            raise ValueError(f"Invalid tool name: {name}")
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        if not callable(function) or inspect.iscoroutinefunction(function):
            raise ValueError(f"Tool must be a synchronous callable: {name}")
        tool = Tool(name, function, tracks_commits)
        self._tools[name] = tool

        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            self.check_limits()
            if self.tool_calls >= self.limits.max_tool_calls:
                self.exceed_limit("max_tool_calls")
            self.tool_calls += 1
            attempt = self.attempts.get(name, 0) + 1
            self.attempts[name] = attempt
            self.trace.record("tool_started", name, attempt=attempt)
            try:
                result = (
                    self.interceptor(tool, attempt, args, kwargs)
                    if self.interceptor is not None
                    else function(*args, **kwargs)
                )
                self.check_limits()
            except BaseException:
                self.trace.record("tool_failed", name, attempt=attempt)
                raise
            self.trace.record("tool_completed", name, attempt=attempt)
            return result

        self._wrappers[name] = wrapped
        return wrapped

    def tool(self, name: str) -> Callable[..., Any]:
        return self._wrappers[name]

    def registration(self, name: str) -> Tool:
        return self._tools[name]
