"""Committed sandbox effects, independent of tool attempts."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Effect:
    effect_id: str
    kind: str
    resource_id: str
    operation_id: str
    amount_minor: int | None = None


class Ledger:
    def __init__(self) -> None:
        self._effects: list[Effect] = []

    @property
    def effects(self) -> tuple[Effect, ...]:
        return tuple(self._effects)

    def commit(
        self,
        kind: str,
        resource_id: str,
        operation_id: str,
        *,
        amount_minor: int | None = None,
    ) -> Effect:
        effect = Effect(
            effect_id=f"effect-{len(self._effects) + 1:04d}",
            kind=kind,
            resource_id=resource_id,
            operation_id=operation_id,
            amount_minor=amount_minor,
        )
        self._effects.append(effect)
        return effect

    def find(self, kind: str, resource_id: str) -> tuple[Effect, ...]:
        return tuple(
            effect
            for effect in self._effects
            if effect.kind == kind and effect.resource_id == resource_id
        )
