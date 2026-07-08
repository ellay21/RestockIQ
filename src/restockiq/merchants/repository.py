"""
MerchantRepository port (ABC) + InMemoryMerchantRepository for unit tests.

Implementations:
  - InMemoryMerchantRepository  — in-memory fake for unit tests
  - PostgresMerchantRepository  — production Postgres-backed implementation

Service code must never reference a concrete repository class directly
— only the abstract port.
"""
from __future__ import annotations

import abc
from typing import TYPE_CHECKING

from restockiq.shared_kernel.errors import NotFoundError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from restockiq.merchants.domain import Merchant
    from restockiq.shared_kernel.value_objects import MerchantId


class MerchantRepository(abc.ABC):
    """
    Port: persistence contract for Merchant aggregates.

    Implementations:
      - InMemoryMerchantRepository (unit tests)
      - PostgresMerchantRepository (production)
    """

    @abc.abstractmethod
    async def save(self, merchant: Merchant) -> None:
        """Persist a new or updated Merchant aggregate."""
        ...

    @abc.abstractmethod
    async def get_by_id(self, merchant_id: MerchantId) -> Merchant:
        """
        Return the Merchant with the given ID.

        Raises:
            NotFoundError: if no Merchant with this ID exists.
        """
        ...

    @abc.abstractmethod
    async def list_all(self) -> Sequence[Merchant]:
        """Return all persisted Merchants in an unspecified order."""
        ...

    @abc.abstractmethod
    async def exists(self, merchant_id: MerchantId) -> bool:
        """Return True if a Merchant with this ID is already persisted."""
        ...


class InMemoryMerchantRepository(MerchantRepository):
    """
    In-memory fake implementation of MerchantRepository.
    """

    def __init__(self) -> None:
        self._store: dict[MerchantId, Merchant] = {}

    async def save(self, merchant: Merchant) -> None:
        self._store[merchant.id] = merchant

    async def get_by_id(self, merchant_id: MerchantId) -> Merchant:
        try:
            return self._store[merchant_id]
        except KeyError:
            raise NotFoundError("Merchant", str(merchant_id)) from None

    async def list_all(self) -> Sequence[Merchant]:
        return list(self._store.values())

    async def exists(self, merchant_id: MerchantId) -> bool:
        return merchant_id in self._store

    # Test helpers

    def count(self) -> int:
        """Return the total number of persisted merchants (useful in assertions)."""
        return len(self._store)

    def clear(self) -> None:
        """Reset the store - useful between test cases that share a fixture."""
        self._store.clear()
