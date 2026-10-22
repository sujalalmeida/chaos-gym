# ChaosGym

Local reliability tests for AI applications. Inject a controlled failure and check
the outcome against committed sandbox state.

## Development

Python 3.11 or newer is required.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
ruff check .
```

The first milestone is a deterministic refund workflow with a lost acknowledgment,
an authoritative side-effect ledger, and unsafe and protected agent variants.
