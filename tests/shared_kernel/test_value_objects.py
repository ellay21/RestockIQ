"""
Shared Kernel unit tests.
All tests are pure: no I/O, no mocks, no fixtures beyond simple construction.
These are the fastest tests in the project and must remain that way forever.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from restockiq.shared_kernel.errors import DomainValidationError
from restockiq.shared_kernel.value_objects import MerchantId, Money, Quantity, SkuCode

# Money


class TestMoney:
    def test_money_rejects_negative_amount(self) -> None:
        with pytest.raises(DomainValidationError, match="negative"):
            Money(amount=Decimal("-1"), currency="ETB")

    def test_money_zero_amount_is_valid(self) -> None:
        m = Money(amount=Decimal("0"), currency="ETB")
        assert m.amount == Decimal("0")

    def test_money_addition_preserves_currency(self) -> None:
        a = Money(Decimal("10"), "ETB")
        b = Money(Decimal("5"), "ETB")
        result = a + b
        assert result.amount == Decimal("15")
        assert result.currency == "ETB"

    def test_money_addition_raises_on_currency_mismatch(self) -> None:
        with pytest.raises(DomainValidationError, match="currency"):
            Money(Decimal("10"), "ETB") + Money(Decimal("5"), "USD")

    def test_money_subtraction_valid(self) -> None:
        result = Money(Decimal("20"), "ETB") - Money(Decimal("5"), "ETB")
        assert result.amount == Decimal("15")

    def test_money_subtraction_would_be_negative_raises(self) -> None:
        with pytest.raises(DomainValidationError, match="negative"):
            Money(Decimal("5"), "ETB") - Money(Decimal("10"), "ETB")

    def test_money_multiplication_by_integer(self) -> None:
        result = Money(Decimal("10"), "ETB") * 3
        assert result.amount == Decimal("30")

    def test_money_multiplication_by_negative_raises(self) -> None:
        with pytest.raises(DomainValidationError, match="negative"):
            Money(Decimal("10"), "ETB") * -1

    def test_money_invalid_currency_code_raises(self) -> None:
        with pytest.raises(DomainValidationError, match="ISO 4217"):
            Money(Decimal("10"), "ETBI")  # 4 letters

    def test_money_empty_currency_raises(self) -> None:
        with pytest.raises(DomainValidationError):
            Money(Decimal("10"), "")

    def test_money_currency_normalised_to_uppercase(self) -> None:
        m = Money(Decimal("10"), "etb")
        assert m.currency == "ETB"

    def test_money_zero_classmethod(self) -> None:
        m = Money.zero("ETB")
        assert m.amount == Decimal("0")
        assert m.currency == "ETB"

    def test_money_comparison_less_than(self) -> None:
        assert Money(Decimal("5"), "ETB") < Money(Decimal("10"), "ETB")

    def test_money_comparison_cross_currency_raises(self) -> None:
        with pytest.raises(DomainValidationError):
            _ = Money(Decimal("5"), "ETB") < Money(Decimal("10"), "USD")

    def test_money_is_immutable(self) -> None:
        m = Money(Decimal("10"), "ETB")
        with pytest.raises((AttributeError, TypeError)):
            m.amount = Decimal("999")  # type: ignore[misc]


# Quantity
class TestQuantity:
    def test_quantity_rejects_non_positive_values(self) -> None:
        with pytest.raises(DomainValidationError, match="positive"):
            Quantity(0)

    def test_quantity_rejects_negative_values(self) -> None:
        with pytest.raises(DomainValidationError, match="positive"):
            Quantity(-5)

    def test_quantity_positive_is_valid(self) -> None:
        q = Quantity(10)
        assert q.units == 10

    def test_quantity_addition(self) -> None:
        assert (Quantity(3) + Quantity(4)).units == 7

    def test_quantity_comparison(self) -> None:
        assert Quantity(3) < Quantity(5)
        assert Quantity(5) >= Quantity(5)

    def test_quantity_is_immutable(self) -> None:
        q = Quantity(5)
        with pytest.raises((AttributeError, TypeError)):
            q.units = 99  # type: ignore[misc]


# SkuCode


class TestSkuCode:
    def test_sku_code_normalises_case_to_uppercase(self) -> None:
        code = SkuCode("sugar-1kg")
        assert code.code == "SUGAR-1KG"

    def test_sku_code_strips_surrounding_whitespace(self) -> None:
        code = SkuCode("  OIL_1L  ")
        assert code.code == "OIL_1L"

    def test_sku_code_empty_raises(self) -> None:
        with pytest.raises(DomainValidationError, match="empty"):
            SkuCode("")

    def test_sku_code_whitespace_only_raises(self) -> None:
        with pytest.raises(DomainValidationError, match="empty"):
            SkuCode("   ")

    def test_sku_code_invalid_characters_raise(self) -> None:
        with pytest.raises(DomainValidationError, match="invalid characters"):
            SkuCode("sugar 1kg")  # space is not allowed

    def test_sku_code_equality_is_case_insensitive(self) -> None:
        assert SkuCode("SUGAR") == SkuCode("sugar")

    def test_sku_code_is_immutable(self) -> None:
        code = SkuCode("SUGAR")
        with pytest.raises((AttributeError, TypeError)):
            code.code = "OIL"  # type: ignore[misc]


# MerchantId
class TestMerchantId:
    def test_merchant_id_generate_produces_unique_ids(self) -> None:
        a = MerchantId.generate()
        b = MerchantId.generate()
        assert a != b

    def test_merchant_id_from_str_roundtrip(self) -> None:
        original = MerchantId.generate()
        restored = MerchantId.from_str(str(original))
        assert restored == original

    def test_merchant_id_from_str_invalid_raises(self) -> None:
        with pytest.raises(DomainValidationError):
            MerchantId.from_str("not-a-uuid")

    def test_merchant_id_is_immutable(self) -> None:
        mid = MerchantId.generate()
        import uuid
        with pytest.raises((AttributeError, TypeError)):
            mid.id = uuid.uuid4()  # type: ignore[misc]
