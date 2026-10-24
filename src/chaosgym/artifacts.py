"""Read saved execution evidence without importing application code."""

import math
import re
from datetime import datetime
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from chaosgym.core.models import RunResult

MAX_REPORT_BYTES = 64 * 1024 * 1024
_REPORT = TypeAdapter(RunResult)


class ArtifactError(ValueError):
    """Saved evidence is unavailable or incompatible."""


def validate_run_id(run_id: str) -> None:
    if re.fullmatch(r"run-[0-9a-f]{32}", run_id) is None:
        raise ArtifactError("Invalid run identifier")


def report_path(root: Path, run_id: str) -> Path:
    validate_run_id(run_id)
    path = root / run_id / "report.json"
    if path.parent.is_symlink() or path.is_symlink():
        raise ArtifactError("Run artifacts must not be symbolic links")
    return path


def read_report(path: Path, *, expected_run_id: str | None = None) -> RunResult:
    if path.is_symlink() or path.parent.is_symlink():
        raise ArtifactError("Run artifacts must not be symbolic links")
    try:
        with path.open("rb") as stream:
            content = stream.read(MAX_REPORT_BYTES + 1)
    except OSError as error:
        raise ArtifactError(f"Cannot read report ({type(error).__name__})") from None
    if len(content) > MAX_REPORT_BYTES:
        raise ArtifactError("Report exceeds the 64 MiB size limit")
    try:
        run = _REPORT.validate_json(content, strict=True)
    except ValidationError:
        raise ArtifactError("Invalid report JSON or field types") from None
    validate_run_id(run.run_id)
    if expected_run_id is not None and run.run_id != expected_run_id:
        raise ArtifactError("Report identifier does not match its run directory")
    if run.schema_version != 1:
        raise ArtifactError("Unsupported report schema version")
    try:
        timestamp = datetime.fromisoformat(run.created_at)
    except ValueError:
        raise ArtifactError("Invalid report timestamp") from None
    if timestamp.utcoffset() is None:
        raise ArtifactError("Report timestamp must include a timezone")
    if not math.isfinite(run.duration_ms) or run.duration_ms < 0:
        raise ArtifactError("Invalid report duration")
    effects = {effect.effect_id for effect in run.effects}
    events = {event.event_id for event in run.events}
    if len(effects) != len(run.effects) or len(events) != len(run.events):
        raise ArtifactError("Duplicate evidence identifiers")
    if run.fault.triggered and run.fault.event_id not in events:
        raise ArtifactError("Fault event evidence is missing")
    if any(event.effect_id is not None and event.effect_id not in effects for event in run.events):
        raise ArtifactError("Trace references a missing committed effect")
    if any(not set(check.effect_ids) <= effects for check in run.assertions):
        raise ArtifactError("Assertion references a missing committed effect")
    return run
