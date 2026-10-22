import pytest

from chaosgym.core.context import IntegrationError, RunContext, RunLimitExceeded
from chaosgym.scenarios import Limits


def test_call_limit_blocks_the_next_operation_before_it_executes():
    context = RunContext(Limits(max_tool_calls=2))
    calls = []
    first = context.register_tool("first", lambda: calls.append("first"))
    second = context.register_tool("second", lambda: calls.append("second"))
    first()
    second()
    with pytest.raises(RunLimitExceeded, match="max_tool_calls"):
        first()
    assert calls == ["first", "second"]
    assert context.tool_calls == 2
    assert context.limit_violation == "max_tool_calls"


def test_deadline_is_checked_before_and_after_tool_execution():
    now = [0.0]
    context = RunContext(Limits(timeout_seconds=1.0), clock=lambda: now[0])

    def slow_tool():
        now[0] = 2.0
        return "late"

    wrapped = context.register_tool("slow", slow_tool)
    with pytest.raises(RunLimitExceeded, match="timeout_seconds"):
        wrapped()
    with pytest.raises(RunLimitExceeded):
        wrapped()
    assert context.tool_calls == 1
    assert context.trace.events[-1].event_type == "tool_failed"


def test_wrapper_preserves_arguments_result_and_application_exception():
    context = RunContext(Limits())
    add = context.register_tool("add", lambda x, *, y: x + y)
    assert context.tool("add")(1, y=2) == 3
    assert add(3, y=4) == 7
    with pytest.raises(TypeError):
        add(1)
    assert context.attempts == {"add": 3}
    assert context.trace.events[-1].event_type == "tool_failed"


def test_registration_rejects_duplicates_and_invalid_names():
    context = RunContext(Limits())
    context.register_tool("valid", lambda: None)
    with pytest.raises(ValueError, match="already registered"):
        context.register_tool("valid", lambda: None)
    with pytest.raises(ValueError, match="Invalid tool"):
        context.register_tool("tool:invalid", lambda: None)


def test_contexts_do_not_share_tools_state_or_evidence():
    first, second = RunContext(Limits()), RunContext(Limits())
    first.state["value"] = 1
    first.register_tool("tool", lambda: 1)()
    assert second.state == {}
    assert second.trace.events == ()
    with pytest.raises(KeyError):
        second.tool("tool")


def test_async_tools_are_rejected_before_a_coroutine_can_be_treated_as_a_result():
    context = RunContext(Limits())

    async def operation():
        return 1

    with pytest.raises(ValueError, match="synchronous"):
        context.register_tool("async_tool", operation)


def test_a_synchronous_wrapper_cannot_smuggle_an_unexecuted_coroutine_as_its_result():
    context = RunContext(Limits())

    async def operation():
        return 1

    wrapped = context.register_tool("disguised_async", lambda: operation())
    with pytest.raises(IntegrationError, match="asynchronous"):
        wrapped()
    assert context.integration_error
    assert context.trace.events[-1].event_type == "tool_failed"
