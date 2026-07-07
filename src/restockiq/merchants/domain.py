"""
Merchant and Sku domain entities with catalog invariants.

Hexagonal rigor: LIGHT — one repository port, otherwise pragmatic CRUD.
No imports from outer layers (adapters, ORM, FastAPI) are permitted here.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from restockiq.shared_kernel.errors import ConflictError, DomainValidationError, NotFoundError
from restockiq.shared_kernel.value_objects import MerchantId, Money, Quantity, SkuCode


@dataclass
class Sku:
    """
    A product in a merchant's catalog.

    Invariants:
      - sell_price must be strictly greater than cost_price (positive margin)
      - sell_price and cost_price must share the same currency
      - name must be non-empty
    """

    code: SkuCode
    name: str
    cost_price: Money   # What the merchant pays per unit to restock
    sell_price: Money   # What the merchant charges customers per unit
    reorder_point: Quantity | None = None  # Optional minimum stock level

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise DomainValidationError(f"SKU '{self.code}' name cannot be empty or whitespace")
        if self.sell_price.currency != self.cost_price.currency:
            raise DomainValidationError(
                f"SKU '{self.code}': sell_price currency ({self.sell_price.currency}) "
                f"and cost_price currency ({self.cost_price.currency}) must match"
            )
        if self.sell_price.amount <= self.cost_price.amount:
            raise DomainValidationError(
                f"SKU '{self.code}': sell_price ({self.sell_price.amount}) "
                f"must be strictly greater than cost_price ({self.cost_price.amount})"
            )

    @property
    def margin(self) -> Money:
        """Gross profit per unit sold (sell_price - cost_price)."""
        return Money(
            amount=self.sell_price.amount - self.cost_price.amount,
            currency=self.sell_price.currency,
        )

    @property
    def margin_rate(self) -> float:
        """Gross margin as a fraction of sell_price (0 < rate < 1)."""
        return float(self.margin.amount / self.sell_price.amount)

    @property
    def currency(self) -> str:
        return self.sell_price.currency


@dataclass
class Merchant:
    """
    A nanostore merchant with a named SKU catalog.

    The Merchant aggregate owns its catalog and enforces uniqueness of SKU
    codes within it.  All prices in the catalog must share the merchant's
    declared currency.
    """

    id: MerchantId
    name: str
    currency: str  # ISO 4217 — all SKU prices must use this currency
    _catalog: dict[SkuCode, Sku] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise DomainValidationError("Merchant name cannot be empty or whitespace")
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise DomainValidationError(
                f"Merchant currency must be a 3-letter ISO 4217 code, "
                f"got {self.currency!r}"
            )
        object.__setattr__(self, "currency", self.currency.upper())

    # Catalog mutations

    def add_sku(self, sku: Sku) -> None:
        """
        Add a SKU to the catalog.

        Raises:
            DomainValidationError: if the SKU's currency doesn't match the merchant's.
            ConflictError: if a SKU with the same code already exists.
        """
        if sku.currency != self.currency:
            raise DomainValidationError(
                f"SKU '{sku.code}' currency ({sku.currency}) does not match "
                f"merchant currency ({self.currency})"
            )
        if sku.code in self._catalog:
            raise ConflictError("Sku", str(sku.code))
        self._catalog[sku.code] = sku

    def update_sku(self, sku: Sku) -> None:
        """
        Replace an existing SKU with an updated version.

        Raises:
            NotFoundError: if no SKU with this code exists.
        """
        if sku.code not in self._catalog:
            raise NotFoundError("Sku", str(sku.code))
        self._catalog[sku.code] = sku

    def remove_sku(self, code: SkuCode) -> None:
        """
        Remove a SKU from the catalog.

        Raises:
            NotFoundError: if the SKU does not exist.
        """
        if code not in self._catalog:
            raise NotFoundError("Sku", str(code))
        del self._catalog[code]

    # Catalog queries

    def get_sku(self, code: SkuCode) -> Sku:
        """
        Return a SKU by code.

        Raises:
            NotFoundError: if the SKU does not exist.
        """
        try:
            return self._catalog[code]
        except KeyError:
            raise NotFoundError("Sku", str(code)) from None

    def list_skus(self) -> list[Sku]:
        """Return all SKUs in insertion order."""
        return list(self._catalog.values())

    @property
    def sku_count(self) -> int:
        return len(self._catalog)
