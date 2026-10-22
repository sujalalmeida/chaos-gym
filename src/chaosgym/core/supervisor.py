"""Bound a scenario worker even when application code ignores cancellation."""

import multiprocessing
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from uuid import uuid4

from chaosgym.core.models import FaultResult, RunResult
from chaosgym.core.runner import execute_scenario
from chaosgym.results import RunStatus
from chaosgym.scenarios import ScenarioSpec

WORKER_GRACE_SECONDS = 3.0


def _worker(sender, spec: ScenarioSpec, module_root: str) -> None:
    # Application output must not corrupt the CLI's structured JSON stream.
    with open(os.devnull, "w") as sink:
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)
    sys.path.insert(0, module_root)
    os.chdir(module_root)
    try:
        sender.send(execute_scenario(spec, enforce_deadline=True))
    finally:
        sender.close()


def _worker_error(spec: ScenarioSpec, error: str, started: float) -> RunResult:
    return RunResult(
        schema_version=1,
        run_id=f"run-{uuid4().hex}",
        created_at=datetime.now(UTC).isoformat(),
        duration_ms=round((monotonic() - started) * 1000, 3),
        project=spec.project,
        scenario=spec.scenario.name,
        variant=None,
        order_id=None,
        request_id=None,
        status=RunStatus.TEST_ERROR,
        completed=False,
        application_error=None,
        test_error=f"supervision: {error}",
        limit_violation="worker_timeout" if error == "WorkerTimeout" else None,
        entrypoint=spec.target.entrypoint,
        fixture=spec.target.fixture,
        limits=spec.limits.model_dump(),
        fault=FaultResult(
            type=spec.scenario.fault.type,
            target=spec.scenario.fault.target,
            on_call=spec.scenario.fault.on_call,
            target_reached=False,
            triggered=False,
            attempts=0,
            event_id=None,
            times=spec.scenario.fault.times,
            delay_seconds=spec.scenario.fault.delay_seconds,
        ),
        assertions=(),
        effects=(),
        events=(),
    )


def run_scenario(spec: ScenarioSpec, *, module_root: Path | None = None) -> RunResult:
    """Run trusted local integration code in a fresh, supervised process."""
    root = (module_root or Path.cwd()).resolve()
    started = monotonic()
    process_context = multiprocessing.get_context("spawn")
    receiver, sender = process_context.Pipe(duplex=False)
    process = process_context.Process(target=_worker, args=(sender, spec, str(root)))
    try:
        process.start()
        sender.close()
        if not receiver.poll(spec.limits.timeout_seconds + WORKER_GRACE_SECONDS):
            return _worker_error(spec, "WorkerTimeout", started)
        result = receiver.recv()
        if not isinstance(result, RunResult):
            return _worker_error(spec, "InvalidWorkerResult", started)
        return result
    except (EOFError, OSError, RuntimeError):
        return _worker_error(spec, "WorkerFailure", started)
    finally:
        sender.close()
        receiver.close()
        if process.pid is not None:
            process.join(timeout=0.2)
            if process.is_alive():
                process.terminate()
                process.join(timeout=1)
            if process.is_alive():
                process.kill()
                process.join(timeout=1)
            process.close()
