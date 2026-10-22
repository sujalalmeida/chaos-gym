"""In-memory services. No payment or email network clients are used."""

from dataclasses import dataclass

from chaosgym.ledger import Effect, Ledger
from chaosgym.tracing import Trace


@dataclass(frozen=True)
class Order:
    order_id: str
    amount_minor: int


class Sandbox:
    def __init__(self) -> None:
        self.ledger = Ledger()
        self.trace = Trace()
        self._orders = {
            "ORD-1042": Order("ORD-1042", 2500),
            "ORD-2000": Order("ORD-2000", 1000),
        }
        self._idempotency: dict[str, Effect] = {}

    def get_order(self, order_id: str) -> Order:
        return self._orders[order_id]

    def refund_payment(
        self,
        order_id: str,
        *,
        operation_id: str,
        idempotency_key: str | None = None,
    ) -> Effect:
        order = self.get_order(order_id)
        if idempotency_key is not None:
            if not idempotency_key:
                raise ValueError("Idempotency key must not be empty")
            previous = self._idempotency.get(idempotency_key)
            if previous is not None:
                if previous.resource_id != order_id:
                    raise ValueError("Idempotency key already belongs to another order")
                self.trace.record(
                    "idempotency_reused", "refund_payment", effect_id=previous.effect_id
                )
                return previous

        effect = self.ledger.commit(
            "refund", order_id, operation_id, amount_minor=order.amount_minor
        )
        if idempotency_key is not None:
            self._idempotency[idempotency_key] = effect
        self.trace.record("effect_committed", "refund_payment", effect_id=effect.effect_id)
        return effect

    def send_email(self, order_id: str) -> Effect:
        self.get_order(order_id)
        if not self.ledger.find("refund", order_id):
            raise ValueError("Cannot confirm an order without a committed refund")
        effect = self.ledger.commit(
            "email", order_id, f"confirmation-{len(self.ledger.effects) + 1}"
        )
        self.trace.record("effect_committed", "send_email", effect_id=effect.effect_id)
        return effect
