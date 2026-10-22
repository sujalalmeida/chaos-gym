# Development notes

## Refund proof

The first milestone exercises one failure with enough evidence to explain it:

1. Create a fresh sandbox for each agent variant.
2. Record the refund in the ledger.
3. Verify that the wrapped call returned a newly committed effect.
4. Hide the first acknowledgment and raise a timeout to the agent.
5. Let the agent retry within its attempt limit.
6. Evaluate committed effects independently of the injector.

The payment simulator deliberately allows repeated unkeyed refunds. Its role is
to expose the caller's retry behavior, rather than enforce a remaining balance or
prevent the duplicate on the caller's behalf. Idempotency keys belong to logical
refund requests; separate requests for one order remain distinct operations.

## Component boundaries

| Module | Responsibility |
| --- | --- |
| `ledger` | Immutable records of committed simulated operations |
| `tracing` | Ordered metadata events with effect links and elapsed timing |
| `scenarios` | Strict versioned YAML validation and fault/assertion configuration |
| `core.context` | Registered tools, shared budgets, and run-local state |
| `core.runner` | Fixture lifecycle, application invocation, and assertion evaluation |
| `core.supervisor` | Fresh workers, deadline enforcement, and hard termination |
| `core.models` | Shared versioned report models |
| `refund.sandbox` | In-memory orders, payments, idempotency, and confirmations |
| `injectors.configured` | Deterministic scheduling and the six supported faults |
| `injectors.lost_ack` | Standalone ledger-backed acknowledgment-loss wrapper |
| `refund.agent` | Scripted workflow and bounded retries |
| `assertions` | Evaluate counts and ordering from ledger state |
| `results` | Classify outcomes without counting untriggered faults as passes |
| `refund.integration` | Register refund services as a normal fixture and entry point |
| `refund.experiment` | Construct the built-in scenario and call the shared engine |
| `reporting` | Publish complete local artifact folders |
| `cli` | Present results and map outcomes to exit codes |

The injector does not choose the run outcome. A missing ledger is inconclusive;
an available ledger containing zero matching effects is a known count of zero.
Confirmation ordering is checked against ledger order, not the agent's final text.

Run identifiers and timing differ between executions. With the same fixture and
configuration, semantic events, effects, and assertions remain repeatable.

## Artifact contract

Schema version `1` includes run and project identity, integration imports,
optional demo identifiers, completion state, application and infrastructure
errors, limits, tool-call counts, fault parameters and activation, assertions,
committed effects, and trace events. The lost-ack fault event links to its
committed effect. Assertion evidence lists relevant effect identifiers; assertion
events retain outcomes. Raw application inputs and output are not saved.

Artifacts are written to a temporary directory and published after both files
are complete. Existing run folders are not overwritten. On POSIX systems, new
run folders use mode `0700` and report files use `0600`.

## Boundaries

The built-in examples make no payment, email, or model network requests.
Configured integrations run in supervised processes, but they retain local
filesystem and network access. The runner supports synchronous callables; only
lost acknowledgment requires a newly committed ledger result. HTTP interception,
async adapters, concurrency control, and external reconciliation are future work.

Normal completion, application errors, and cooperative budget interruption unwind
fixture cleanup. A hard-killed worker cannot guarantee cleanup or deliver its
evidence, and is reported as a test error. See [scenario configuration](scenarios.md)
for deadline and watchdog semantics.

The confirmation service rejects confirmation without a refund. The independent
ordering assertion is also tested against deliberately invalid ledger histories.

## Next milestone

- Index saved run artifacts in local SQLite storage.
- Add history listing and run inspection without opening files manually.
- Expose local history and trace details through a loopback-only FastAPI service.
- Build a basic trace viewer from stored outcomes and events.
- Add async support before verifying a LangGraph integration.

Keep each working change in a focused commit and push it with its relevant checks.
