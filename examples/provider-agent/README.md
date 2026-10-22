# Provider agent

This example registers a scripted model response and a simulated notification
service with the runner. It retries transient errors and validates the response
before committing a notification.

From the repository root:

```sh
chaosgym test examples/provider-agent/rate-limit.yaml --trace
chaosgym test examples/provider-agent/provider-outage.yaml
chaosgym test examples/provider-agent/malformed-output.yaml --json
```

The first two scenarios require recovery and one committed notification. The
malformed-output scenario requires zero notifications: the application raises a
validation error, and the run passes because the specified safe-failure property
holds. Add a `completed` assertion when successful task completion is required.

`agent.py` is loaded from the scenario directory. A fixture registers wrapped
tools, and the entry point calls them through `context.tool(name)`. Neither the
model response nor the notification uses a network service.
