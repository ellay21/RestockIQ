"""
MerchantService tests against the in-memory fake repository.

No database, no FastAPI — the service is tested in isolation through the
port abstraction.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from restockiq.merchants.domain import Sku
from restockiq.merchants.repository import InMemoryMerchantRepository
from restockiq.merchants.service import MerchantService
from restockiq.shared_kernel.errors import ConflictError, NotFoundError
from restockiq.shared_kernel.value_objects import MerchantId, Money, SkuCode

# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def service() -> MerchantService:
    """Fresh service backed by an in-memory repository for each test."""
    return MerchantService(repository=InMemoryMerchantRepository())


@pytest.fixture
def merchant_id() -> MerchantId:
    return MerchantId.generate()


@pytest.fixture
def sugar_sku() -> Sku:
    return Sku(
        code=SkuCode("SUGAR"),
        name="Sugar 1kg",
        cost_price=Money(Decimal("20"), "ETB"),
        sell_price=Money(Decimal("25"), "ETB"),
    )


import pytest
import pytest_asyncio

# ──────────────────────────────────────────────────────────────────────────────
# Registration
# ──────────────────────────────────────────────────────────────────────────────

pytestmark = pytest.mark.asyncio


class TestRegistration:
    async def test_registering_merchant_persists_via_repository(
        self, service: MerchantService, merchant_id: MerchantId
    ) -> None:
        await service.register_merchant(merchant_id, "Corner Shop", "ETB")
        fetched = await service.get_merchant(merchant_id)
        assert fetched.id == merchant_id
        assert fetched.name == "Corner Shop"
        assert fetched.currency == "ETB"

    async def test_duplicate_merchant_raises_conflict(
        self, service: MerchantService, merchant_id: MerchantId
    ) -> None:
        await service.register_merchant(merchant_id, "Shop A", "ETB")
        with pytest.raises(ConflictError):
            await service.register_merchant(merchant_id, "Shop B", "ETB")

    async def test_get_nonexistent_merchant_raises_not_found(
        self, service: MerchantService
    ) -> None:
        with pytest.raises(NotFoundError):
            await service.get_merchant(MerchantId.generate())


# ──────────────────────────────────────────────────────────────────────────────
# Catalog management through service
# ──────────────────────────────────────────────────────────────────────────────


class TestCatalogManagement:
    async def test_add_sku_to_catalog(
        self, service: MerchantService, merchant_id: MerchantId, sugar_sku: Sku
    ) -> None:
        await service.register_merchant(merchant_id, "Corner Shop", "ETB")
        merchant = await service.add_sku(merchant_id, sugar_sku)
        assert merchant.sku_count == 1

    async def test_get_catalog_returns_added_skus(
        self, service: MerchantService, merchant_id: MerchantId, sugar_sku: Sku
    ) -> None:
        await service.register_merchant(merchant_id, "Corner Shop", "ETB")
        await service.add_sku(merchant_id, sugar_sku)
        catalog = await service.get_catalog(merchant_id)
        assert len(catalog) == 1
        assert catalog[0].code == SkuCode("SUGAR")

    async def test_add_sku_to_nonexistent_merchant_raises(
        self, service: MerchantService, sugar_sku: Sku
    ) -> None:
        with pytest.raises(NotFoundError):
            await service.add_sku(MerchantId.generate(), sugar_sku)

    async def test_remove_sku(
        self, service: MerchantService, merchant_id: MerchantId, sugar_sku: Sku
    ) -> None:
        await service.register_merchant(merchant_id, "Corner Shop", "ETB")
        await service.add_sku(merchant_id, sugar_sku)
        await service.remove_sku(merchant_id, SkuCode("SUGAR"))
        assert await service.get_catalog(merchant_id) == []
