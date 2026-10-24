"""Rebuildable SQLite summaries backed by authoritative JSON artifacts."""

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from chaosgym.artifacts import ArtifactError, read_report, report_path
from chaosgym.core.models import RunResult
from chaosgym.results import RunStatus


class HistoryError(ValueError):
    """The local history index cannot be accessed safely."""


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    created_at: str
    project: str | None
    scenario: str
    variant: str | None
    status: RunStatus
    fault_type: str
    fault_triggered: bool
    duration_ms: float


@dataclass(frozen=True)
class SkippedReport:
    run_id: str
    reason: str


@dataclass(frozen=True)
class RebuildResult:
    indexed: int
    skipped: tuple[SkippedReport, ...]


class HistoryStore:
    def __init__(self, root: Path = Path(".chaosgym/runs")) -> None:
        self.root = root
        self.database = root / "history.sqlite3"

    @contextmanager
    def _connect(self, *, write: bool):
        connection = None
        try:
            if self.database.is_symlink():
                raise HistoryError("History database must not be a symbolic link")
            if write:
                self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
                try:
                    descriptor = os.open(self.database, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                except FileExistsError:
                    pass
                else:
                    os.close(descriptor)
                connection = sqlite3.connect(self.database, timeout=5)
            else:
                connection = sqlite3.connect(
                    self.database.resolve().as_uri() + "?mode=ro", uri=True, timeout=5
                )
            connection.row_factory = sqlite3.Row
            with connection:
                if write:
                    connection.execute("BEGIN IMMEDIATE")
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version not in ((0, 1) if write else (1,)):
                    raise HistoryError("Unsupported history schema version")
                if write:
                    connection.execute("""
                        CREATE TABLE IF NOT EXISTS runs (
                            run_id TEXT PRIMARY KEY,
                            created_at TEXT NOT NULL,
                            project TEXT,
                            scenario TEXT NOT NULL,
                            variant TEXT,
                            status TEXT NOT NULL,
                            fault_type TEXT NOT NULL,
                            fault_triggered INTEGER NOT NULL,
                            duration_ms REAL NOT NULL
                        )
                    """)
                    connection.execute(
                        "CREATE INDEX IF NOT EXISTS runs_by_time "
                        "ON runs(created_at DESC, run_id DESC)"
                    )
                    connection.execute("PRAGMA user_version = 1")
                yield connection
        except (sqlite3.Error, OSError) as error:
            raise HistoryError(f"Cannot access run history ({type(error).__name__})") from None
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _insert(connection, run: RunResult) -> None:
        summary = RunSummary(
            run.run_id,
            datetime.fromisoformat(run.created_at).astimezone(UTC).isoformat(),
            run.project,
            run.scenario,
            run.variant,
            run.status,
            run.fault.type,
            run.fault.triggered,
            run.duration_ms,
        )
        connection.execute(
            """INSERT INTO runs VALUES (
                :run_id, :created_at, :project, :scenario, :variant, :status,
                :fault_type, :fault_triggered, :duration_ms
            ) ON CONFLICT(run_id) DO UPDATE SET
                created_at=excluded.created_at, project=excluded.project,
                scenario=excluded.scenario, variant=excluded.variant, status=excluded.status,
                fault_type=excluded.fault_type, fault_triggered=excluded.fault_triggered,
                duration_ms=excluded.duration_ms""",
            asdict(summary),
        )

    def index(self, run_id: str) -> None:
        run = self.load(run_id)
        with self._connect(write=True) as connection:
            self._insert(connection, run)

    def load(self, run_id: str) -> RunResult:
        return read_report(report_path(self.root, run_id), expected_run_id=run_id)

    def rebuild(self) -> RebuildResult:
        if not self.root.exists():
            return RebuildResult(0, ())
        skipped = []
        indexed = 0
        with self._connect(write=True) as connection:
            connection.execute("DELETE FROM runs")
            for path in sorted(self.root.glob("run-*/report.json")):
                run_id = path.parent.name
                try:
                    run = self.load(run_id)
                except ArtifactError as error:
                    skipped.append(SkippedReport(run_id, str(error)))
                else:
                    self._insert(connection, run)
                    indexed += 1
        return RebuildResult(indexed, tuple(skipped))

    def list_runs(
        self,
        *,
        status: RunStatus | None = None,
        project: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[RunSummary, ...]:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("History limit must be between 1 and 1000")
        if type(offset) is not int or offset < 0:
            raise ValueError("History offset must be a nonnegative integer")
        if not self.database.exists():
            return ()
        conditions, parameters = [], []
        if status is not None:
            conditions.append("status = ?")
            parameters.append(RunStatus(status).value)
        if project is not None:
            conditions.append("project = ?")
            parameters.append(project)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        with self._connect(write=False) as connection:
            rows = connection.execute(
                "SELECT * FROM runs"
                + where
                + " ORDER BY created_at DESC, run_id DESC LIMIT ? OFFSET ?",
                [*parameters, limit, offset],
            ).fetchall()
        try:
            return tuple(
                RunSummary(
                    **dict(
                        row,
                        status=RunStatus(row["status"]),
                        fault_triggered=bool(row["fault_triggered"]),
                    )
                )
                for row in rows
            )
        except (TypeError, ValueError):
            raise HistoryError("Invalid history entries; rebuild from saved reports") from None
