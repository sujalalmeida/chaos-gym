from chaosgym.tracing import Trace


def test_trace_preserves_order_timing_and_effect_links():
    ticks = iter([10.0, 10.025, 10.05])
    trace = Trace(clock=lambda: next(ticks))
    call = trace.record("tool_started", "refund_payment", attempt=1)
    commit = trace.record("effect_committed", "refund_payment", attempt=1, effect_id="effect-0001")

    assert trace.events == (call, commit)
    assert (call.event_id, commit.event_id) == ("evt-0001", "evt-0002")
    assert (call.elapsed_ms, commit.elapsed_ms) == (25.0, 50.0)
    assert commit.effect_id == "effect-0001"
    assert commit.attempt == 1
