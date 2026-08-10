"""
MerchantService - application service for merchant registration and catalog management.

Orchestrates domain entities through the MerchantRepository port.  This class
has no direct knowledge of HTTP, databases, or external services; it only
speaks domain types.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from restockiq.merchants.domain import Merchant, Sku
from restockiq.shared_kernel.errors import ConflictError

if TYPE_CHECKING:
    from restockiq.merchants.repository import MerchantRepository
    from restockiq.shared_kernel.value_objects import MerchantId, SkuCode


class MerchantService:
    """
    Application service: orchestrates merchant and SKU catalog operations.

    All mutation methods persist changes through the injected repository so the
    caller never needs to call `repository.save()` directly.
    """

    def __init__(self, repository: MerchantRepository) -> None:
        self._repo = repository

    # Merchant lifecycle
    async def register_merchant(
        self,
        merchant_id: MerchantId,
        name: str,
        currency: str,
    ) -> Merchant:
        """
        Register a new merchant and persist them.

        Raises:
            ConflictError: if a merchant with this ID already exists.
            DomainValidationError: if name or currency fail invariants.
        """
        if await self._repo.exists(merchant_id):
            raise ConflictError("Merchant", str(merchant_id))
        merchant = Merchant(id=merchant_id, name=name, currency=currency)
        await self._repo.save(merchant)
        return merchant

    async def get_merchant(self, merchant_id: MerchantId) -> Merchant:
        """
        Fetch a merchant by ID.

        Raises:
            NotFoundError: if no merchant with this ID exists.
        """
        return await self._repo.get_by_id(merchant_id)

    async def list_merchants(self) -> list[Merchant]:
        """Return all registered merchants."""
        return list(await self._repo.list_all())

    # SKU catalog management

    async def add_sku(self, merchant_id: MerchantId, sku: Sku) -> Merchant:
        """
        Add a SKU to a merchant's catalog and persist the updated merchant.

        Raises:
            NotFoundError: if the merchant does not exist.
            ConflictError: if a SKU with the same code already exists.
            DomainValidationError: if the SKU fails catalog currency constraints.
        """
        merchant = await self._repo.get_by_id(merchant_id)
        merchant.add_sku(sku)
        await self._repo.save(merchant)
        return merchant

    async def update_sku(self, merchant_id: MerchantId, sku: Sku) -> Merchant:
        """
        Update an existing SKU in the catalog.

        Raises:
            NotFoundError: if the merchant or SKU does not exist.
        """
        merchant = await self._repo.get_by_id(merchant_id)
        merchant.update_sku(sku)
        await self._repo.save(merchant)
        return merchant

    async def remove_sku(self, merchant_id: MerchantId, code: SkuCode) -> Merchant:
        """
        Remove a SKU from the catalog.

        Raises:
            NotFoundError: if the merchant or SKU does not exist.
        """
        merchant = await self._repo.get_by_id(merchant_id)
        merchant.remove_sku(code)
        await self._repo.save(merchant)
        return merchant

    async def get_catalog(self, merchant_id: MerchantId) -> list[Sku]:
        """Return all SKUs in a merchant's catalog."""
        merchant = await self._repo.get_by_id(merchant_id)
        return merchant.list_skus()
