"""A scripted provider workflow; no model SDK or credentials are needed."""

from contextlib import contextmanager

from chaosgym.core.context import RunContext
from chaosgym.injectors.configured import ProviderUnavailable, RateLimitError


@contextmanager
def fixture(context: RunContext):
    context.register_tool("model", lambda: {"action": "notify"})
    context.register_tool(
        "notify",
        lambda request_id: context.ledger.commit("notification", request_id, request_id),
        tracks_commits=True,
    )
    yield


def run(context: RunContext, *, request_id: str) -> None:
    for attempt in range(1, 4):
        try:
            response = context.tool("model")()
        except (RateLimitError, ProviderUnavailable, TimeoutError):
            if attempt == 3:
                raise
        else:
            if not isinstance(response, dict) or response.get("action") != "notify":
                raise ValueError("Provider response does not match the expected schema")
            context.tool("notify")(request_id)
            return
