"""
Merchant & SKU Catalog domain unit tests.

Tests are pure: no I/O, no database, no HTTP.  Every invariant defined in
merchants/domain.py has a corresponding test here.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from restockiq.merchants.domain import Merchant, Sku
from restockiq.shared_kernel.errors import ConflictError, DomainValidationError, NotFoundError
from restockiq.shared_kernel.value_objects import MerchantId, Money, SkuCode

# Fixtures


@pytest.fixture
def merchant() -> Merchant:
    return Merchant(id=MerchantId.generate(), name="Corner Shop", currency="ETB")


@pytest.fixture
def sugar_sku() -> Sku:
    return Sku(
        code=SkuCode("SUGAR-1KG"),
        name="Sugar 1kg",
        cost_price=Money(Decimal("20"), "ETB"),
        sell_price=Money(Decimal("25"), "ETB"),
    )


@pytest.fixture
def oil_sku() -> Sku:
    return Sku(
        code=SkuCode("OIL-1L"),
        name="Oil 1L",
        cost_price=Money(Decimal("60"), "ETB"),
        sell_price=Money(Decimal("75"), "ETB"),
    )


# Sku invariants


class TestSkuInvariants:
    def test_cannot_add_sku_with_sell_price_below_cost_price(self) -> None:
        with pytest.raises(DomainValidationError, match="sell_price"):
            Sku(
                code=SkuCode("BAD-ITEM"),
                name="Bad Item",
                cost_price=Money(Decimal("30"), "ETB"),
                sell_price=Money(Decimal("20"), "ETB"),
            )

    def test_cannot_add_sku_with_equal_sell_and_cost_price(self) -> None:
        """Zero-margin SKUs are not permitted — they bring no value."""
        with pytest.raises(DomainValidationError, match="sell_price"):
            Sku(
                code=SkuCode("ZERO-MARGIN"),
                name="Zero Margin",
                cost_price=Money(Decimal("25"), "ETB"),
                sell_price=Money(Decimal("25"), "ETB"),
            )

    def test_sku_margin_computation(self) -> None:
        sku = Sku(
            code=SkuCode("OIL-1L"),
            name="Oil 1L",
            cost_price=Money(Decimal("60"), "ETB"),
            sell_price=Money(Decimal("75"), "ETB"),
        )
        assert sku.margin == Money(Decimal("15"), "ETB")

    def test_sku_margin_rate_computation(self) -> None:
        sku = Sku(
            code=SkuCode("OIL-1L"),
            name="Oil 1L",
            cost_price=Money(Decimal("60"), "ETB"),
            sell_price=Money(Decimal("75"), "ETB"),
        )
        # margin = 15, sell = 75 → rate = 0.2
        assert abs(sku.margin_rate - 0.2) < 1e-9

    def test_sku_empty_name_raises(self) -> None:
        with pytest.raises(DomainValidationError):
            Sku(
                code=SkuCode("SUGAR"),
                name="   ",
                cost_price=Money(Decimal("20"), "ETB"),
                sell_price=Money(Decimal("25"), "ETB"),
            )

    def test_sku_currency_mismatch_between_prices_raises(self) -> None:
        with pytest.raises(DomainValidationError, match="currency"):
            Sku(
                code=SkuCode("IMPORT"),
                name="Imported Good",
                cost_price=Money(Decimal("20"), "ETB"),
                sell_price=Money(Decimal("25"), "USD"),
            )


# Merchant catalog operations


class TestMerchantCatalog:
    def test_catalog_lookup_by_sku_code(self, merchant: Merchant, sugar_sku: Sku) -> None:
        merchant.add_sku(sugar_sku)
        found = merchant.get_sku(SkuCode("SUGAR-1KG"))
        assert found.name == "Sugar 1kg"

    def test_catalog_lookup_case_insensitive_code(self, merchant: Merchant, sugar_sku: Sku) -> None:
        merchant.add_sku(sugar_sku)
        # SkuCode normalises to uppercase, so lowercase lookup should match
        found = merchant.get_sku(SkuCode("sugar-1kg"))
        assert found.code == SkuCode("SUGAR-1KG")

    def test_catalog_lookup_missing_sku_raises_not_found(self, merchant: Merchant) -> None:
        with pytest.raises(NotFoundError):
            merchant.get_sku(SkuCode("NONEXISTENT"))

    def test_duplicate_sku_raises_conflict(self, merchant: Merchant, sugar_sku: Sku) -> None:
        merchant.add_sku(sugar_sku)
        with pytest.raises(ConflictError):
            merchant.add_sku(sugar_sku)

    def test_list_skus_returns_all_added(
        self, merchant: Merchant, sugar_sku: Sku, oil_sku: Sku
    ) -> None:
        merchant.add_sku(sugar_sku)
        merchant.add_sku(oil_sku)
        assert merchant.sku_count == 2
        codes = {s.code for s in merchant.list_skus()}
        assert SkuCode("SUGAR-1KG") in codes
        assert SkuCode("OIL-1L") in codes

    def test_remove_sku_reduces_count(self, merchant: Merchant, sugar_sku: Sku) -> None:
        merchant.add_sku(sugar_sku)
        merchant.remove_sku(SkuCode("SUGAR-1KG"))
        assert merchant.sku_count == 0

    def test_remove_nonexistent_sku_raises_not_found(self, merchant: Merchant) -> None:
        with pytest.raises(NotFoundError):
            merchant.remove_sku(SkuCode("GHOST"))

    def test_update_sku_replaces_existing(self, merchant: Merchant, sugar_sku: Sku) -> None:
        merchant.add_sku(sugar_sku)
        updated = Sku(
            code=SkuCode("SUGAR-1KG"),
            name="Premium Sugar 1kg",
            cost_price=Money(Decimal("22"), "ETB"),
            sell_price=Money(Decimal("28"), "ETB"),
        )
        merchant.update_sku(updated)
        assert merchant.get_sku(SkuCode("SUGAR-1KG")).name == "Premium Sugar 1kg"

    def test_update_nonexistent_sku_raises_not_found(
        self, merchant: Merchant, sugar_sku: Sku
    ) -> None:
        with pytest.raises(NotFoundError):
            merchant.update_sku(sugar_sku)


# Merchant-level invariants


class TestMerchantInvariants:
    def test_empty_merchant_name_raises(self) -> None:
        with pytest.raises(DomainValidationError):
            Merchant(id=MerchantId.generate(), name="  ", currency="ETB")

    def test_invalid_currency_code_raises(self) -> None:
        with pytest.raises(DomainValidationError):
            Merchant(id=MerchantId.generate(), name="Shop", currency="ET")

    def test_adding_sku_with_wrong_currency_raises(self, merchant: Merchant) -> None:
        usd_sku = Sku(
            code=SkuCode("IMPORT"),
            name="USD Item",
            cost_price=Money(Decimal("1"), "USD"),
            sell_price=Money(Decimal("2"), "USD"),
        )
        with pytest.raises(DomainValidationError, match="currency"):
            merchant.add_sku(usd_sku)
