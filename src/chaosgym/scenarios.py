"""Versioned scenario configuration with explicit, validated fault semantics."""

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt, model_validator
from yaml.tokens import AliasToken

PositiveInt = Annotated[StrictInt, Field(ge=1)]
NonnegativeInt = Annotated[StrictInt, Field(ge=0)]
Name = Annotated[str, Field(min_length=1, pattern=r"^[A-Za-z_][\w.-]*$")]
ImportPath = Annotated[str, Field(pattern=r"^[A-Za-z_]\w*(?:\.\w+)*:[A-Za-z_]\w*$")]


class Spec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


class TargetSpec(Spec):
    entrypoint: ImportPath
    fixture: ImportPath
    input: dict[str, JsonValue] = Field(default_factory=dict)


class FaultSpec(Spec):
    target: Annotated[str, Field(pattern=r"^tool:[A-Za-z_][\w.-]*$")]
    type: Literal[
        "response_lost_after_commit",
        "timeout",
        "slow_response",
        "malformed_output",
        "rate_limit",
        "provider_outage",
    ]
    on_call: PositiveInt = 1
    times: PositiveInt = 1
    delay_seconds: Annotated[float, Field(gt=0, le=60)] | None = None

    @model_validator(mode="after")
    def validate_delay(self) -> "FaultSpec":
        if (self.type == "slow_response") != (self.delay_seconds is not None):
            raise ValueError("delay_seconds is required only for slow_response")
        return self


class ExperimentSpec(Spec):
    name: Name
    fault: FaultSpec


class AssertionSpec(Spec):
    type: Literal["effect_count", "confirmation_after_refund", "completed"]
    effect: Name | None = None
    resource_id: Annotated[str, Field(min_length=1)] | None = None
    equals: NonnegativeInt | None = None

    @model_validator(mode="after")
    def validate_fields(self) -> "AssertionSpec":
        if self.type == "effect_count":
            if self.effect is None or self.resource_id is None or self.equals is None:
                raise ValueError("effect_count requires effect, resource_id, and equals")
        elif self.type == "confirmation_after_refund":
            if self.resource_id is None or self.effect is not None or self.equals is not None:
                raise ValueError("confirmation_after_refund requires only resource_id")
        elif any(value is not None for value in (self.effect, self.resource_id, self.equals)):
            raise ValueError("completed accepts no additional fields")
        return self


class Limits(Spec):
    timeout_seconds: Annotated[float, Field(gt=0, le=3600)] = 30.0
    max_tool_calls: PositiveInt = 15


class ScenarioSpec(Spec):
    version: Annotated[StrictInt, Field(ge=1, le=1)] = 1
    project: Name
    target: TargetSpec
    scenario: ExperimentSpec
    assertions: Annotated[tuple[AssertionSpec, ...], Field(min_length=1)]
    limits: Limits = Field(default_factory=Limits)


class ScenarioError(ValueError):
    """A scenario cannot be loaded or validated."""


class _UniqueLoader(yaml.SafeLoader):
    pass


def _unique_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise ScenarioError("YAML mapping keys must be strings")
        if key in mapping:
            raise ScenarioError(f"Duplicate YAML key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def load_scenario(path: Path) -> ScenarioSpec:
    try:
        with path.open("rb") as stream:
            content = stream.read(1_048_577)
        if len(content) > 1_048_576:
            raise ScenarioError("Scenario exceeds the 1 MiB size limit")
        if any(isinstance(token, AliasToken) for token in yaml.scan(content)):
            raise ScenarioError("YAML aliases are not supported")
        data = yaml.load(content, Loader=_UniqueLoader)
        if isinstance(data, dict) and isinstance(data.get("assertions"), list):
            data["assertions"] = tuple(data["assertions"])
        return ScenarioSpec.model_validate(data)
    except (OSError, UnicodeError, yaml.YAMLError, ValueError, RecursionError) as error:
        raise ScenarioError(f"Invalid scenario {path}: {error}") from error
