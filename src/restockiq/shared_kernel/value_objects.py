"""
Immutable, self-validating value objects used throughout RestockIQ.

All value objects are frozen dataclasses — they enforce their invariants in
__post_init__ and cannot be mutated after construction.  They carry no I/O
dependencies; every import in this module is from the standard library.

Value objects defined here:
  Money      — a monetary amount + ISO 4217 currency code
  Quantity   — a positive integer count of units
  SkuCode    — a normalised (uppercase) product identifier
  MerchantId — a UUID that uniquely identifies a merchant
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from restockiq.shared_kernel.errors import DomainValidationError

# Money


@dataclass(frozen=True)
class Money:
    """
    Represents a non-negative monetary amount denominated in a single currency.

    Invariants:
      - amount   >= 0
      - currency is a non-empty 3-letter ISO 4217 code (e.g. "ETB", "USD")

    Arithmetic operations (+, -, *) return new Money instances and raise
    DomainValidationError when currencies differ or the result would be
    negative.
    """

    amount: Decimal
    currency: str  # 3-letter ISO 4217 code, e.g. "ETB"

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            # Accept int / float inputs and coerce gracefully
            try:
                object.__setattr__(self, "amount", Decimal(str(self.amount)))
            except InvalidOperation as exc:
                raise DomainValidationError(
                    f"Money amount must be a valid decimal, got {self.amount!r}"
                ) from exc
        if self.amount < Decimal(0):
            raise DomainValidationError(f"Money amount cannot be negative, got {self.amount}")
        if not self.currency or len(self.currency) != 3 or not self.currency.isalpha():
            raise DomainValidationError(
                f"currency must be a 3-letter ISO 4217 code (e.g. 'ETB'), got {self.currency!r}"
            )
        # Normalise currency to uppercase
        object.__setattr__(self, "currency", self.currency.upper())

    #  Arithmetic

    def __add__(self, other: Money) -> Money:
        self._assert_same_currency(other, "add")
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: Money) -> Money:
        self._assert_same_currency(other, "subtract")
        result = self.amount - other.amount
        if result < Decimal(0):
            raise DomainValidationError(
                f"Subtraction would produce a negative amount: "
                f"{self.amount} - {other.amount} = {result}"
            )
        return Money(amount=result, currency=self.currency)

    def __mul__(self, factor: int | float | Decimal) -> Money:
        try:
            decimal_factor = Decimal(str(factor))
        except InvalidOperation as exc:
            raise DomainValidationError(f"Cannot multiply Money by {factor!r}") from exc
        if decimal_factor < Decimal(0):
            raise DomainValidationError(f"Cannot multiply Money by a negative factor ({factor})")
        return Money(amount=self.amount * decimal_factor, currency=self.currency)

    # Comparison

    def __lt__(self, other: Money) -> bool:
        self._assert_same_currency(other, "compare")
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        self._assert_same_currency(other, "compare")
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        self._assert_same_currency(other, "compare")
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        self._assert_same_currency(other, "compare")
        return self.amount >= other.amount

    # Helpers

    def _assert_same_currency(self, other: Money, op: str) -> None:
        if self.currency != other.currency:
            raise DomainValidationError(
                f"Cannot {op} {self.currency} and {other.currency}: currency mismatch"
            )

    @classmethod
    def zero(cls, currency: str) -> Money:
        """Convenience constructor: Money with amount=0 in the given currency."""
        return cls(amount=Decimal(0), currency=currency)

    def __str__(self) -> str:
        return f"{self.amount:.2f} {self.currency}"


# Quantity


@dataclass(frozen=True)
class Quantity:
    """
    A positive integer count of physical units (e.g. "12 bags of sugar").

    Invariant: units must be strictly positive (> 0).

    Use raw `int` for zero-quantity contexts (e.g. "0 units ordered") —
    Quantity is intentionally NOT allowed to be zero because a "quantity of
    zero of something" is semantically a non-entity.
    """

    units: int

    def __post_init__(self) -> None:
        if not isinstance(self.units, int):
            raise DomainValidationError(
                f"Quantity.units must be an integer, got {type(self.units).__name__}"
            )
        if self.units <= 0:
            raise DomainValidationError(f"Quantity must be strictly positive, got {self.units}")

    def __add__(self, other: Quantity) -> Quantity:
        return Quantity(units=self.units + other.units)

    def __lt__(self, other: Quantity) -> bool:
        return self.units < other.units

    def __le__(self, other: Quantity) -> bool:
        return self.units <= other.units

    def __gt__(self, other: Quantity) -> bool:
        return self.units > other.units

    def __ge__(self, other: Quantity) -> bool:
        return self.units >= other.units

    def __str__(self) -> str:
        return str(self.units)


# SkuCode


@dataclass(frozen=True)
class SkuCode:
    """
    An identifier for a product SKU, normalised to uppercase.

    Invariants:
      - Non-empty after stripping whitespace
      - Only alphanumeric characters, hyphens (-), and underscores (_) are
        allowed.  This keeps codes safely embeddable in URLs and filenames.

    Normalisation: the code is converted to uppercase on construction, so
    SkuCode("sugar-1kg") == SkuCode("SUGAR-1KG").
    """

    code: str

    def __post_init__(self) -> None:
        normalised = self.code.strip().upper()
        if not normalised:
            raise DomainValidationError("SkuCode cannot be empty or whitespace-only")
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
        invalid = set(normalised) - allowed
        if invalid:
            raise DomainValidationError(
                f"SkuCode contains invalid characters {sorted(invalid)!r}. "
                "Only alphanumerics, hyphens, and underscores are allowed."
            )
        # Store the normalised value in the frozen dataclass field
        object.__setattr__(self, "code", normalised)

    def __str__(self) -> str:
        return self.code


# MerchantId


@dataclass(frozen=True)
class MerchantId:
    """
    Unique identifier for a merchant, backed by a UUID.

    Invariant: the wrapped value must be a uuid.UUID instance.
    Use MerchantId.generate() to create a new random ID.
    """

    id: uuid.UUID

    def __post_init__(self) -> None:
        if not isinstance(self.id, uuid.UUID):
            raise DomainValidationError(
                f"MerchantId.id must be a uuid.UUID instance, got {type(self.id).__name__!r}"
            )

    @classmethod
    def generate(cls) -> MerchantId:
        """Create a new MerchantId backed by a random UUID4."""
        return cls(id=uuid.uuid4())

    @classmethod
    def from_str(cls, value: str) -> MerchantId:
        """Parse a UUID string into a MerchantId."""
        try:
            return cls(id=uuid.UUID(value))
        except ValueError as exc:
            raise DomainValidationError(f"Cannot parse {value!r} as a MerchantId: {exc}") from exc

    def __str__(self) -> str:
        return str(self.id)
