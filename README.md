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
and retains the generated reports as workflow artifacts.

## Current scope

The refund proof is implemented: sandbox ledger, lost-acknowledgment injection,
unsafe and protected workflows, state-based assertions, traces, and a CLI.

Next: reusable runner and scenario configuration, additional fault types, a local
history viewer, and a verified LangGraph adapter. Arbitrary applications, live
providers, YAML scenarios, and the dashboard are not supported yet.

See [development notes](docs/development.md) for the component boundaries and next milestone.
