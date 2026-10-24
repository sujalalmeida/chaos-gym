import os
import sqlite3
from dataclasses import replace

import pytest

from chaosgym.history import HistoryError, HistoryStore
from chaosgym.refund.experiment import run_refund_experiment
from chaosgym.reporting import write_report


def saved(root, variant, *, created_at="2026-10-24T14:00:00+00:00", project="refund-agent"):
    run = replace(run_refund_experiment(variant), created_at=created_at, project=project)
    write_report(run, root)
    return run


def test_index_is_persistent_idempotent_and_filtered_without_sql_interpolation(tmp_path):
    failed = saved(tmp_path, "unsafe")
    passed = saved(tmp_path, "protected", created_at="2026-10-24T15:00:00+00:00", project="other")
    store = HistoryStore(tmp_path)
    for run in (failed, passed, failed):
        store.index(run.run_id)
    reopened = HistoryStore(tmp_path)
    assert [row.run_id for row in reopened.list_runs()] == [passed.run_id, failed.run_id]
    assert reopened.list_runs(status="failed")[0].run_id == failed.run_id
    assert reopened.list_runs(project="other")[0].run_id == passed.run_id
    assert reopened.list_runs(project="' OR 1=1 --") == ()
    assert reopened.list_runs(limit=1, offset=1)[0].run_id == failed.run_id
    assert reopened.load(passed.run_id) == passed
    if os.name == "posix":
        assert store.database.stat().st_mode & 0o777 == 0o600


def test_history_orders_timezone_offsets_by_instant_not_lexicographic_time(tmp_path):
    earlier = saved(tmp_path, "unsafe", created_at="2026-10-24T10:00:00-04:00")
    later = saved(tmp_path, "protected", created_at="2026-10-24T14:30:00+00:00")
    store = HistoryStore(tmp_path)
    assert store.rebuild().indexed == 2
    assert [row.run_id for row in store.list_runs()] == [later.run_id, earlier.run_id]


def test_rebuild_skips_corruption_and_removes_entries_without_canonical_artifacts(tmp_path):
    first = saved(tmp_path, "unsafe")
    second = saved(tmp_path, "protected")
    store = HistoryStore(tmp_path)
    assert store.rebuild().indexed == 2
    (tmp_path / first.run_id / "report.json").unlink()
    (tmp_path / second.run_id / "report.json").write_text('{"private-token":')
    result = store.rebuild()
    assert result.indexed == 0
    assert result.skipped[0].run_id == second.run_id
    assert "private-token" not in result.skipped[0].reason
    assert store.list_runs() == ()


def test_reading_empty_history_does_not_create_storage(tmp_path):
    store = HistoryStore(tmp_path / "missing")
    assert store.list_runs() == ()
    assert store.rebuild().indexed == 0
    assert not store.root.exists()


def test_future_database_versions_are_rejected_without_modification(tmp_path):
    database = tmp_path / "history.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version = 99")
    store = HistoryStore(tmp_path)
    with pytest.raises(HistoryError, match="schema version"):
        store.rebuild()
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 99


@pytest.mark.parametrize("options", [{"limit": 0}, {"limit": True}, {"offset": -1}])
def test_invalid_pagination_is_rejected(tmp_path, options):
    with pytest.raises(ValueError):
        HistoryStore(tmp_path).list_runs(**options)
