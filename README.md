# ChaosGym

Local reliability tests for AI applications. Inject a controlled failure and check
the outcome against committed sandbox state.

## Run locally

Python 3.11 or newer is required.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
chaosgym demo refund
```

The demo runs two isolated workflows with the same fault: the payment service
commits a refund, then its acknowledgment is lost on the first call.

- The unsafe agent retries without an idempotency key and commits two refunds.
- The protected agent retries with the same key and commits one refund.

Both agents make two refund calls. Assertions count committed effects, check that
confirmation follows a refund, and verify that the workflow completes. The demo
uses scripted decisions and in-memory services; no model API key is required.

The comparison exits successfully when the unsafe agent exposes the duplicate
refund and the protected agent passes the same scenario. Each run retains its own
`failed` or `passed` result.

## Run a scenario

```sh
chaosgym init
chaosgym test chaosgym.yaml --trace
```

`init` creates a protected refund scenario and refuses to overwrite an existing
file. Change `target.input.variant` to `unsafe` to expose the duplicate refund.
`test` validates the YAML, starts a fresh worker, runs the fixture and application,
checks committed state, and saves the result.

The scenario library covers six faults:

| Fault | Runnable scenario |
| --- | --- |
| Lost acknowledgment after commit | `scenarios/refund-lost-ack.yaml` |
| Timeout before execution | `scenarios/refund-timeout.yaml` |
| Slow response | `scenarios/refund-slow-response.yaml` |
| Simulated provider rate limit | `examples/provider-agent/rate-limit.yaml` |
| Simulated provider outage | `examples/provider-agent/provider-outage.yaml` |
| Malformed response | `examples/provider-agent/malformed-output.yaml` |

```sh
chaosgym test examples/provider-agent/rate-limit.yaml --json
```

Applications register synchronous Python tools with a run context. Scenarios
select an exact invocation or a range of repeated faults. Shared tool-call and
runtime budgets stop runaway workflows. See [scenario configuration](docs/scenarios.md)
for the integration contract, assertion semantics, and execution boundaries.

## Inspect a run

```sh
chaosgym demo refund --trace
chaosgym demo refund --variant protected
chaosgym demo refund --variant unsafe
chaosgym demo refund --json
```

The unsafe variant exits with code `1`. Reports are saved under
`.chaosgym/runs/<run-id>/`:

- `report.json`: versioned result, fault activation, assertions, effects, and events.
- `events.jsonl`: the same timeline as one event per line.

Use `--output <directory>` to change the artifact location. Every value in the
report comes from that execution. Raw prompts, tool payloads, and exception
messages are not captured.

## Saved history

Each saved run is indexed in local SQLite storage alongside its JSON artifacts.

```sh
chaosgym history
chaosgym history --status failed --project refund-agent --json
chaosgym show latest --trace
chaosgym show <run-id> --json
```

History lists the newest runs first and supports `--limit` and `--offset`.
Use `--root <directory>` for artifacts saved with a custom `--output` directory.
`show` reads recorded evidence without rerunning the application; a successful
inspection exits with `0`, including when the stored test outcome is `failed`.

```sh
chaosgym history --rebuild
```

The index can be rebuilt from reports and is created automatically for older
artifact folders. Invalid reports are skipped with diagnostics. JSON reports
remain the source of truth. See [history storage](docs/history.md) for recovery
and compatibility details.

To check an untriggered fault:

```sh
chaosgym demo refund --variant protected --on-call 2
```

The workflow succeeds on its first attempt, so the second-call fault never fires.
The result is `not_triggered`, with exit code `3`.

| Exit code | Meaning |
| --- | --- |
| `0` | Single run passed, or the before/after demonstration was verified |
| `1` | Assertion failed, or the comparison did not demonstrate the expected correction |
| `2` | Invalid arguments or test infrastructure error |
| `3` | Intended fault did not trigger |
| `4` | Evidence was inconclusive |

## Development

```sh
pytest -q
ruff check .
ruff format --check .
```

GitHub Actions runs the tests and demonstration on Python 3.11, 3.12, and 3.13,
and retains the generated reports as workflow artifacts. CI also checks history
listing and inspection against the reports produced by the installed package.

## Current scope

The shared runner, validated YAML configuration, six deterministic fault types,
registered Python tools, execution budgets, fixture lifecycle, state-based and
Python assertions, traces, JSON reports, and CLI are implemented. The refund demo
uses the same engine as configured scenarios.

Saved runs have a rebuildable SQLite index, filtered CLI history, and direct
assertion and timeline inspection. Existing schema-one reports remain readable.

Next: a local history API, a trace viewer, and a verified LangGraph adapter.
Async integrations, HTTP/provider interception, live-model evaluation, and the
dashboard are not supported yet. Scenario integrations execute trusted Python;
worker supervision is not an operating-system security sandbox.

See [development notes](docs/development.md) for the component boundaries and next milestone.
