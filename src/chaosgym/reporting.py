"""Versioned local artifacts for the terminal, future dashboard, and CI."""

import json
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from chaosgym.artifacts import validate_run_id
from chaosgym.core.models import RunResult


def _write_private(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def write_report(run: RunResult, root: Path = Path(".chaosgym/runs")) -> Path:
    validate_run_id(run.run_id)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = root / run.run_id
    if destination.exists():
        raise FileExistsError(f"Run artifacts already exist: {destination}")

    # Publish the folder only after every artifact has been written successfully.
    with TemporaryDirectory(dir=root, prefix=".pending-") as pending:
        staging = Path(pending)
        _write_private(staging / "report.json", json.dumps(asdict(run), indent=2) + "\n")
        events = "".join(json.dumps(asdict(event)) + "\n" for event in run.events)
        _write_private(staging / "events.jsonl", events)
        staging.rename(destination)
    return destination / "report.json"
