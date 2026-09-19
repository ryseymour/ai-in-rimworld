"""Currency, and the purses that hold it.

Trade settles in coin where there is coin to settle with, and falls back to
barter where there is not -- see `trade.settle`. Currency is its own object so
a second one can be added later without the trade code caring.
"""
from __future__ import annotations

from dataclasses import dataclass

#: Coin is tracked to this precision. Anything finer is rounded away at the
#: point of payment, so a purse can never drift a fraction below zero.
PRECISION = 0.001


@dataclass(frozen=True)
class Currency:
    """A kind of money. `value` is what one unit is worth in the prices that
    `goods` quotes, which lets a second currency be introduced at a rate."""

    name: str
    symbol: str
    value: float = 1.0

    def format(self, amount: float) -> str:
        return f"{amount:,.2f} {self.symbol}"


SILVER = Currency("silver", "ag")


@dataclass
class Purse:
    """Coin held by a colony or carried by a caravan."""

    currency: Currency = SILVER
    amount: float = 0.0

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError("a purse cannot start overdrawn")

    def can_pay(self, price: float) -> bool:
        return self.amount + PRECISION >= price

    def withdraw(self, up_to: float) -> float:
        """Take out as much as is asked for, or everything, whichever is less.

        Returning what was actually taken rather than refusing is what lets a
        part-paid trade fall back to barter for the remainder.
        """
        if up_to <= 0:
            return 0.0
        taken = min(self.amount, up_to)
        self.amount = round(self.amount - taken, 6)
        if self.amount < PRECISION:
            self.amount = 0.0
        return taken

    def deposit(self, amount: float) -> None:
        if amount < 0:
            raise ValueError("deposit a negative amount by withdrawing it")
        self.amount = round(self.amount + amount, 6)

    def transfer_to(self, other: Purse, amount: float) -> float:
        """Move coin between purses. Returns what actually moved."""
        if other.currency is not self.currency:
            raise ValueError("no exchange rate between currencies yet")
        moved = self.withdraw(amount)
        other.deposit(moved)
        return moved

    def __str__(self) -> str:
        return self.currency.format(self.amount)
