import pytest

from chaosgym.scenarios import ScenarioError, load_scenario

SCENARIO = """version: 1
project: refund-agent
target:
  entrypoint: chaosgym.refund.integration:run
  fixture: chaosgym.refund.integration:fixture
scenario:
  name: duplicate-refund
  fault:
    target: tool:refund_payment
    type: response_lost_after_commit
assertions:
  - type: effect_count
    effect: refund
    resource_id: ORD-1042
    equals: 1
"""


def test_valid_scenario_has_bounded_defaults(tmp_path):
    path = tmp_path / "scenario.yaml"
    path.write_text(SCENARIO)
    scenario = load_scenario(path)
    assert scenario.limits.max_tool_calls == 15
    assert scenario.scenario.fault.on_call == 1
    assert scenario.assertions[0].equals == 1


@pytest.mark.parametrize(
    "before,after",
    [
        ("version: 1", "version: 2"),
        ("version: 1", "version: true"),
        ("version: 1", "version: 1\nunknown: true"),
        ("version: 1", "version: 1\nversion: 1"),
        ("equals: 1", "equals: true"),
        ("equals: 1", "equals: -1"),
        ("equals: 1", "equals: '1'"),
        ("type: response_lost_after_commit", "type: unsupported"),
        ("type: response_lost_after_commit", "type: timeout\n    on_call: 0"),
        ("type: response_lost_after_commit", "type: slow_response"),
        ("type: response_lost_after_commit", "type: timeout\n    delay_seconds: 1"),
        ("tool:refund_payment", "provider:anything"),
        ("equals: 1", "unexpected: 1"),
        ("version: 1", "version: &v 1\nproject: *v"),
        ("version: 1", "version: 1\nlimits:\n  timeout_seconds: .inf"),
        ("entrypoint: chaosgym.refund.integration:run", "entrypoint: ./app.py"),
    ],
)
def test_invalid_or_ambiguous_configuration_is_rejected(tmp_path, before, after):
    path = tmp_path / "scenario.yaml"
    path.write_text(SCENARIO.replace(before, after))
    with pytest.raises(ScenarioError):
        load_scenario(path)


def test_oversized_or_missing_scenarios_are_reported_as_configuration_errors(tmp_path):
    path = tmp_path / "missing.yaml"
    with pytest.raises(ScenarioError):
        load_scenario(path)
    path.write_bytes(b"#" * 1_048_577)
    with pytest.raises(ScenarioError, match="size limit"):
        load_scenario(path)


def test_validation_errors_do_not_echo_input_payloads(tmp_path):
    path = tmp_path / "invalid.yaml"
    path.write_text(SCENARIO.replace("equals: 1", "equals: private-api-token"))
    with pytest.raises(ScenarioError) as error:
        load_scenario(path)
    assert "private-api-token" not in str(error.value)
    assert "assertions.0.equals" in str(error.value)


def test_yaml_syntax_errors_report_location_without_echoing_document_content(tmp_path):
    path = tmp_path / "invalid.yaml"
    path.write_text("private-api-token: [unterminated")
    with pytest.raises(ScenarioError) as error:
        load_scenario(path)
    assert "private-api-token" not in str(error.value)
    assert "line" in str(error.value)
