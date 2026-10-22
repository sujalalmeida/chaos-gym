"""Run synchronous Python applications with fixture and assertion lifecycles."""

import importlib
import inspect
import signal
from datetime import UTC, datetime
from time import monotonic
from uuid import uuid4

from chaosgym.assertions import (
    AssertionResult,
    AssertionStatus,
    confirmation_after_refund,
    effect_count,
)
from chaosgym.core.context import RunContext, RunLimitExceeded
from chaosgym.core.models import FaultResult, RunResult
from chaosgym.injectors.configured import FaultInjector
from chaosgym.results import classify_run
from chaosgym.scenarios import ScenarioSpec


class AdapterError(ValueError):
    """An invalid integration contract, with a safe configuration diagnostic."""


def _resolve(path: str):
    module_name, name = path.split(":", 1)
    try:
        function = getattr(importlib.import_module(module_name), name)
    except (ImportError, AttributeError) as error:
        raise AdapterError(f"Cannot import {path} ({type(error).__name__})") from error
    if not callable(function) or inspect.iscoroutinefunction(function):
        raise AdapterError(f"Expected a synchronous callable: {path}")
    return function


def _evaluate(
    spec: ScenarioSpec, context: RunContext, completed: bool
) -> tuple[AssertionResult, ...]:
    results = []
    for assertion in spec.assertions:
        if assertion.type == "effect_count":
            result = effect_count(
                context.ledger,
                kind=assertion.effect,
                resource_id=assertion.resource_id,
                equals=assertion.equals,
            )
        elif assertion.type == "confirmation_after_refund":
            result = confirmation_after_refund(context.ledger, resource_id=assertion.resource_id)
        else:
            result = AssertionResult(
                "application_completed == 1",
                AssertionStatus.PASSED if completed else AssertionStatus.FAILED,
                1,
                int(completed),
                (),
            )
        results.append(result)
    for check in context.python_assertions:
        result = check(context)
        if not isinstance(result, AssertionResult):
            raise AdapterError("Python assertions must return AssertionResult")
        results.append(result)
    if context.limit_violation:
        results.append(
            AssertionResult("run_limits_respected == 1", AssertionStatus.FAILED, 1, 0, ())
        )
    return tuple(results)


def execute_scenario(spec: ScenarioSpec, *, enforce_deadline: bool = False) -> RunResult:
    """Execute in the current process; use the supervised entry point for CLI runs."""
    started = monotonic()
    created_at = datetime.now(UTC).isoformat()
    context = RunContext(spec.limits)
    completed = False
    application_error = None
    test_error = None
    assertions = ()
    injector = None
    stage = "setup"
    previous_handler = None
    if enforce_deadline and hasattr(signal, "setitimer"):

        def stop_run(signum, frame):
            context.exceed_limit("timeout_seconds")

        previous_handler = signal.signal(signal.SIGALRM, stop_run)
        signal.setitimer(signal.ITIMER_REAL, spec.limits.timeout_seconds)
    try:
        application = _resolve(spec.target.entrypoint)
        fixture = _resolve(spec.target.fixture)
        try:
            inspect.signature(application).bind(context, **spec.target.input)
        except TypeError as error:
            raise AdapterError("Entrypoint parameters do not match target.input") from error
        with fixture(context):
            context.trace.record("fixture_ready", spec.target.fixture)
            try:
                injector = FaultInjector(spec.scenario.fault, context)
            except ValueError as error:
                raise AdapterError(str(error)) from error
            context.interceptor = injector
            stage = "application"
            try:
                context.check_limits()
                application(context, **spec.target.input)
                context.check_limits()
                completed = context.limit_violation is None
            except RunLimitExceeded:
                context.trace.record("application_stopped", spec.target.entrypoint)
            except Exception as error:
                application_error = type(error).__name__
                context.trace.record("application_failed", spec.target.entrypoint)
            stage = "assertions"
            assertions = _evaluate(spec, context, completed)
            stage = "teardown"
        context.trace.record("fixture_closed", spec.target.fixture)
    except (Exception, RunLimitExceeded) as error:
        diagnostic = str(error) if isinstance(error, AdapterError) else type(error).__name__
        test_error = f"{stage}: {diagnostic}"
        context.trace.record("test_error", stage)
    finally:
        if previous_handler is not None:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)

    triggered = injector.triggered if injector else False
    return RunResult(
        schema_version=1,
        run_id=f"run-{uuid4().hex}",
        created_at=created_at,
        duration_ms=round((monotonic() - started) * 1000, 3),
        scenario=spec.scenario.name,
        project=spec.project,
        variant=context.metadata.get("variant"),
        order_id=context.metadata.get("order_id"),
        request_id=context.metadata.get("request_id"),
        status=classify_run(
            triggered=triggered, assertions=assertions, test_error=test_error is not None
        ),
        completed=completed,
        application_error=application_error,
        test_error=test_error,
        fault=FaultResult(
            type=spec.scenario.fault.type,
            target=spec.scenario.fault.target,
            on_call=spec.scenario.fault.on_call,
            target_reached=bool(injector and injector.attempts),
            triggered=triggered,
            attempts=injector.attempts if injector else 0,
            event_id=injector.events[0].event_id if triggered else None,
            activation_count=len(injector.events) if injector else 0,
        ),
        assertions=assertions,
        effects=context.ledger.effects,
        events=context.trace.events,
        tool_calls=context.tool_calls,
        limit_violation=context.limit_violation,
    )
