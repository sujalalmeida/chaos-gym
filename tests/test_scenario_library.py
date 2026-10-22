from pathlib import Path

import pytest

from chaosgym.core.supervisor import run_scenario
from chaosgym.scenarios import load_scenario

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = [
    "scenarios/refund-lost-ack.yaml",
    "scenarios/refund-timeout.yaml",
    "scenarios/refund-slow-response.yaml",
    "examples/provider-agent/rate-limit.yaml",
    "examples/provider-agent/provider-outage.yaml",
    "examples/provider-agent/malformed-output.yaml",
]


@pytest.mark.parametrize("relative_path", SCENARIOS)
def test_each_initial_fault_has_a_runnable_scenario_with_authoritative_assertions(relative_path):
    path = ROOT / relative_path
    run = run_scenario(load_scenario(path), module_root=path.parent)
    assert run.status == "passed", run
    assert run.fault.triggered
    assert run.fault.activation_count == 1
    if run.fault.type == "malformed_output":
        assert not run.completed
        assert run.application_error == "ValueError"
        assert run.effects == ()
    else:
        assert run.completed
        assert run.effects


def test_scenario_library_covers_six_distinct_fault_types():
    assert len({load_scenario(ROOT / path).scenario.fault.type for path in SCENARIOS}) == 6
