# Local run history

Every artifact root has an independent `history.sqlite3` index. The default is
`.chaosgym/runs/history.sqlite3`. Run folders still contain `report.json` and
`events.jsonl`; the database stores only listing summaries.

## Listing and inspection

```sh
chaosgym history --status failed --project refund-agent --limit 10
chaosgym history --limit 10 --offset 10 --json
chaosgym show latest --trace
chaosgym show run-0123456789abcdef0123456789abcdef --json
```

Replace the example identifier with a full identifier from history. Identifiers
are not abbreviated, so they can be copied into `show`. A custom artifact root
is selected with `--root` on both commands.

History uses exact project and outcome filters. Rows are ordered by UTC creation
time, newest first, with the run identifier breaking ties. Pagination describes
the returned page; its length is not presented as the total number of stored runs.

`history --json` returns `runs`, `limit`, `offset`, and optional `rebuild`
diagnostics. `show --json` returns the full stored result and its report path.
Neither command imports the fixture or runs application code. Successful reads
exit with zero regardless of the stored test outcome. Missing identifiers,
incompatible artifacts, and inaccessible storage exit with two.

## Publication and indexing

The report folder is published before its summary is indexed. If SQLite is
unavailable, the completed JSON artifacts remain intact and the run keeps its
original outcome and exit code. A warning identifies the history problem.

New databases use mode `0600`, and newly created artifact roots use `0700` on
POSIX systems. Existing directory permissions are left in place. Only one writer
updates an index at a time; queries use read-only SQLite connections.

## Rebuilding and recovery

```sh
chaosgym history --rebuild --json
```

Rebuilding validates saved reports and replaces the summary index in one
transaction. It removes summaries for deleted reports, incorporates changes to
saved metadata, and returns the identifiers and reasons for skipped reports.
Invalid artifacts are left untouched. Errors and skip notices go to stderr, so
stdout remains valid JSON.

When an index is missing, history discovers existing report folders and rebuilds
automatically. Listing a nonexistent artifact root creates no files. If an index
is corrupted, keep a backup and move that index aside before rebuilding from the
reports. Future database schema versions are rejected without modifying them.

The index is a cache: external edits or deletions are reflected after a rebuild.
`show` always rereads the canonical report and does not reconstruct evidence from
cached summary rows.

## Artifact compatibility

The reader accepts report schema one and validates field types, timezone-aware
timestamps, timing values, unique evidence identifiers, and links between fault
events, effects, and assertions. Mismatched directory identifiers and symbolic
links to individual run folders or report files are rejected.

Early schema-one reports lack explicit tool-call and activation counters. Those
missing values are derived from their stored trace events. Explicitly stored
values are preserved. Application inputs and raw output are not added to history.

Validation checks artifact structure and evidence links. It is not a signature
or a guarantee that someone has not edited the contents of a local report.
