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
| `refund.sandbox` | In-memory orders, payments, idempotency, and confirmations |
| `injectors.lost_ack` | Verify a fresh commit, then suppress the selected response |
| `refund.agent` | Scripted workflow and bounded retries |
| `assertions` | Evaluate counts and ordering from ledger state |
| `results` | Classify outcomes without counting untriggered faults as passes |
| `refund.experiment` | Assemble the built-in experiment and collect evidence |
| `reporting` | Publish complete local artifact folders |
| `cli` | Present results and map outcomes to exit codes |

The injector does not choose the run outcome. A missing ledger is inconclusive;
an available ledger containing zero matching effects is a known count of zero.
Confirmation ordering is checked against ledger order, not the agent's final text.

Run identifiers and timing differ between executions. With the same fixture and
configuration, semantic events, effects, and assertions remain repeatable.

## Artifact contract

Schema version `1` includes the run identity, scenario and variant, input
identifiers, completion state, application exception type, fault activation,
assertions, committed effects, and trace events. The fault event links to its
committed effect. Assertion evidence lists the relevant effect identifiers.

Artifacts are written to a temporary directory and published after both files
are complete. Existing run folders are not overwritten. On POSIX systems, new
run folders use mode `0700` and report files use `0600`.

## Boundaries

The built-in demo makes no payment, email, or model network requests. It is a
single-process simulation, not a security sandbox for arbitrary Python code.
The current wrapper is synchronous and expects a ledger-backed result. It does
not implement provider interception, concurrency control, wall-clock deadlines,
or external payment reconciliation.

The confirmation service rejects confirmation without a refund. The independent
ordering assertion is also tested against deliberately invalid ledger histories.

## Next milestone

- Extract run context and target registration from the refund experiment.
- Validate versioned YAML scenarios and supported target/fault combinations.
- Add fixture setup and teardown with separate infrastructure error evidence.
- Enforce runtime and tool-call limits across adapters.
- Add timeout, delay, malformed output, rate limit, and provider outage faults.
- Keep fault activation and evidence semantics consistent across scenarios.

Build local history and the dashboard after these contracts are stable. Keep
each working change in a focused commit and push it with its relevant checks.
