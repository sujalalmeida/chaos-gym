"""Command-line entry point for local reliability experiments."""

import json
from dataclasses import asdict
from enum import StrEnum
from importlib.resources import files
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from chaosgym.core.models import RunResult
from chaosgym.core.supervisor import run_scenario
from chaosgym.refund.agent import AgentVariant
from chaosgym.refund.experiment import run_refund_experiment
from chaosgym.reporting import write_report
from chaosgym.results import RunStatus
from chaosgym.scenarios import load_scenario

app = typer.Typer(no_args_is_help=True, add_completion=False)
demo = typer.Typer(no_args_is_help=True)
app.add_typer(demo, name="demo", help="Run deterministic sandbox examples.")


class DemoVariant(StrEnum):
    BOTH = "both"
    UNSAFE = "unsafe"
    PROTECTED = "protected"


EXIT_CODES = {
    RunStatus.PASSED: 0,
    RunStatus.FAILED: 1,
    RunStatus.TEST_ERROR: 2,
    RunStatus.NOT_TRIGGERED: 3,
    RunStatus.INCONCLUSIVE: 4,
}


def _show_run(console: Console, run: RunResult, path: Path, show_trace: bool) -> None:
    console.print(f"{run.variant or run.scenario}: {run.status.value.upper()}")
    console.print(
        f"  Fault triggered: {run.fault.triggered} | Target attempts: {run.fault.attempts}"
    )
    checks = Table("Assertion", "Expected", "Actual", "Status")
    for check in run.assertions:
        checks.add_row(check.name, str(check.expected), str(check.actual), check.status.value)
    console.print(checks)
    if show_trace:
        for event in run.events:
            console.print(
                f"  {event.event_id} +{event.elapsed_ms}ms {event.event_type} {event.operation}",
                soft_wrap=True,
            )
            if event.attempt is not None or event.effect_id:
                console.print(
                    f"    attempt={event.attempt} effect={event.effect_id}", soft_wrap=True
                )
    if run.application_error:
        console.print(f"  Application error: {run.application_error}")
    if run.test_error:
        console.print(f"  Test error: {run.test_error}", soft_wrap=True)
    if run.limit_violation:
        console.print(f"  Limit exceeded: {run.limit_violation}")
    console.print(f"  Total tool calls: {run.tool_calls}")
    console.print(f"  Fault event: {run.fault.event_id or 'none'}")
    console.print(f"  Report: {path}", soft_wrap=True)


@demo.command("refund")
def refund_demo(
    variant: Annotated[DemoVariant, typer.Option(help="Agent variant to run.")] = DemoVariant.BOTH,
    output: Annotated[Path, typer.Option(help="Local run artifact directory.")] = Path(
        ".chaosgym/runs"
    ),
    on_call: Annotated[int, typer.Option(min=1, help="Refund call to fault.")] = 1,
    max_attempts: Annotated[int, typer.Option(min=1, help="Maximum refund attempts.")] = 2,
    order_id: Annotated[str, typer.Option(help="Sandbox order identifier.")] = "ORD-1042",
    trace: Annotated[bool, typer.Option(help="Print the event timeline.")] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Print JSON instead of tables.")
    ] = False,
) -> None:
    """Compare unsafe and protected refunds under the same lost acknowledgment."""
    variants = list(AgentVariant) if variant == DemoVariant.BOTH else [AgentVariant(variant.value)]
    runs = []
    artifacts = []
    try:
        for selected in variants:
            run = run_refund_experiment(
                selected, on_call=on_call, max_attempts=max_attempts, order_id=order_id
            )
            path = write_report(run, output)
            runs.append(run)
            artifacts.append(path)
    except (OSError, ValueError) as error:
        Console(stderr=True, markup=False).print(f"Test error: {error}")
        raise typer.Exit(2) from error

    if json_output:
        typer.echo(
            json.dumps(
                [
                    dict(asdict(run), report_path=str(path))
                    for run, path in zip(runs, artifacts, strict=True)
                ],
                indent=2,
            )
        )
    else:
        console = Console(markup=False)
        for run, path in zip(runs, artifacts, strict=True):
            _show_run(console, run, path, trace)

    if variant != DemoVariant.BOTH:
        raise typer.Exit(EXIT_CODES[runs[0].status])
    if (
        runs[0].status == RunStatus.FAILED
        and runs[0].assertions[0].actual == 2
        and runs[1].status == RunStatus.PASSED
    ):
        raise typer.Exit(0)
    for status in (RunStatus.TEST_ERROR, RunStatus.NOT_TRIGGERED, RunStatus.INCONCLUSIVE):
        if any(run.status == status for run in runs):
            raise typer.Exit(EXIT_CODES[status])
    raise typer.Exit(1)


@app.command("init")
def initialize(
    path: Annotated[Path, typer.Option(help="Scenario file to create.")] = Path("chaosgym.yaml"),
) -> None:
    """Create a runnable local refund scenario without overwriting existing files."""
    template = files("chaosgym").joinpath("templates/refund.yaml").read_text(encoding="utf-8")
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(template)
    except OSError as error:
        Console(stderr=True, markup=False).print(f"Cannot create scenario: {error}")
        raise typer.Exit(2) from error
    typer.echo(f"Created {path}")


@app.command("test")
def test_scenario(
    path: Annotated[Path, typer.Argument(help="Trusted local YAML scenario.")],
    output: Annotated[Path, typer.Option(help="Run artifact directory.")] = Path(".chaosgym/runs"),
    trace: Annotated[bool, typer.Option(help="Print the event timeline.")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Print a JSON result.")] = False,
) -> None:
    """Run a configured Python application with faults, assertions, and limits."""
    try:
        spec = load_scenario(path)
        run = run_scenario(spec, module_root=path.resolve().parent)
        report = write_report(run, output)
    except (OSError, ValueError) as error:
        Console(stderr=True, markup=False).print(f"Test error: {error}")
        raise typer.Exit(2) from error
    if json_output:
        typer.echo(json.dumps(dict(asdict(run), report_path=str(report)), indent=2))
    else:
        _show_run(Console(markup=False), run, report, trace)
    raise typer.Exit(EXIT_CODES[run.status])
