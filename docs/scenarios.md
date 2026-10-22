# Scenario configuration

Create a runnable configuration with `chaosgym init`, then run it with
`chaosgym test chaosgym.yaml`. The complete initial configuration is in
[`templates/refund.yaml`](../src/chaosgym/templates/refund.yaml).

## Target and fixture

`target.entrypoint` and `target.fixture` use `module:function` imports. Installed
modules and Python files beside the scenario are supported. The worker starts
in the scenario directory; relative application paths resolve there. YAML files
execute trusted local code with the user's filesystem and network permissions.

A fixture is a synchronous context manager accepting a `RunContext`. It registers
tools and prepares isolated state. An entry point accepts that same context and
the keyword arguments in `target.input`.

```python
from contextlib import contextmanager

from chaosgym.core.context import RunContext


@contextmanager
def fixture(context: RunContext):
    context.register_tool(
        "save",
        lambda: context.ledger.commit("write", "record-1", "request-1"),
        tracks_commits=True,
    )
    yield


def run(context: RunContext):
    try:
        context.tool("save")()
    except TimeoutError:
        context.tool("save")()
```

Save that code as `app.py` beside this YAML file:

```yaml
version: 1
project: example
target:
  entrypoint: app:run
  fixture: app:fixture
scenario:
  name: duplicate-write
  fault:
    target: tool:save
    type: response_lost_after_commit
    on_call: 1
assertions:
  - type: effect_count
    effect: write
    resource_id: record-1
    equals: 1
  - type: completed
limits:
  timeout_seconds: 5
  max_tool_calls: 5
```

The scenario fails with two committed writes, exposing the unsafe retry. Adding
an idempotency mechanism belongs in the simulated service or application.

Only calls through registered wrappers are counted or faulted. A wrapper returned
by `register_tool` can be passed directly to an application. Register tools during
fixture setup, before the runner validates the configured fault target.

## Fault semantics

`on_call` is one-based and counts calls to the selected tool only. `times`, which
defaults to one, selects consecutive calls beginning at `on_call`. Unrelated tool
calls consume the shared budget but do not advance the selected tool's trigger.

| Type | Execution behavior |
| --- | --- |
| `timeout` | Raise `TimeoutError` before invoking the operation |
| `rate_limit` | Raise `RateLimitError` with `status_code = 429` before execution |
| `provider_outage` | Raise `ProviderUnavailable` with `status_code = 503` before execution |
| `slow_response` | Record activation, delay, check the deadline, then invoke the operation |
| `malformed_output` | Invoke the operation, then replace its response with invalid JSON text |
| `response_lost_after_commit` | Verify a new ledger-backed effect, then raise `AcknowledgmentLost` |

`slow_response` requires `delay_seconds` between zero and sixty seconds, excluding
zero. Other faults reject that field. Repeated failures use `times`, for example
`type: timeout`, `on_call: 1`, `times: 3`.

Lost acknowledgment requires `tracks_commits=True` and an operation returning the
new `Effect` from the context's ledger. A failed operation, an untracked result,
or an idempotent replay does not claim a new commit or activate this fault.

Malformed output can occur after a side effect commits. Assertions should check
that state, not assume invalid output means the operation never executed.
Provider errors simulate failures at a wrapped boundary; they do not intercept
HTTP traffic or reproduce an SDK's exception classes.

## Assertions and outcomes

- `effect_count` requires `effect`, `resource_id`, and a nonnegative `equals`.
- `confirmation_after_refund` requires `resource_id` and rejects an email committed
  before the first refund for that resource.
- `completed` requires the application to return without an exception or limit violation.

For an application-specific oracle, append a callable to
`context.python_assertions` during fixture setup. It receives the context and
returns an `AssertionResult`; use `AssertionStatus.PASSED`, `FAILED`, or
`INCONCLUSIVE` and include relevant effect identifiers. A callback exception or
invalid return type is an assertion-infrastructure error.

A triggered fault passes only when every required assertion passes. Include
`completed` when recovery is required. Omit it when checking a defined safe
failure, such as zero notifications after malformed model output. An application
exception alone does not determine whether its specified properties held.

Fault activation is separate from assertion success. An untriggered scenario is
`not_triggered`, even when all assertions pass. Missing evidence is inconclusive;
known violations fail. Setup, teardown, assertion, and worker errors are
`test_error`. JSON reports retain the phase and exception type without arbitrary
exception messages or application output.

## Limits and cleanup

`max_tool_calls` counts every registered tool across the run. The next call is
blocked before its operation executes. `timeout_seconds` defaults to thirty,
with checks before and after wrapped calls. Limits are enforced independently of
application retry logic, and any observed budget violation adds a failed assertion.

The CLI runs each scenario in a fresh spawned process. On macOS and Linux, a
deadline interrupt stops stalled synchronous Python code and unwinds normal
fixture cleanup. The parent watchdog terminates workers that do not return within
the runtime budget plus a three-second startup/termination grace period.

A forcibly killed or crashed worker cannot guarantee fixture cleanup or return
its ledger. That produces a test error with unavailable evidence, rather than a
fabricated passing report. Keep fixture side effects isolated and reversible.
Workers are not network, filesystem, or subprocess security sandboxes.

## Validation and artifacts

Unknown fields, duplicate YAML keys, aliases, invalid trigger positions, and
unsupported target/fault combinations are rejected. Scenario documents are limited
to 1 MiB. Configuration diagnostics identify fields or YAML locations without
echoing input values. Use JSON-compatible values in `target.input`.

Report schema version one gains additive fields for project identity, tool-call
counts, execution limits, integration imports, fault parameters and activations,
and assertion events. Raw inputs are not saved. Keep the original scenario and
fixture sources when reproducing a run.
