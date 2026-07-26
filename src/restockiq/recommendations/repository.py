"""
RecommendationRepository port + InMemoryRecommendationRepository.
"""
from __future__ import annotations

import abc
from typing import TYPE_CHECKING

from restockiq.shared_kernel.errors import NotFoundError

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from restockiq.recommendations.domain import RestockRecommendation
    from restockiq.shared_kernel.value_objects import MerchantId


class RecommendationRepository(abc.ABC):
    """Port: persistence contract for RestockRecommendation aggregates."""

    @abc.abstractmethod
    async def save(self, recommendation: RestockRecommendation) -> None:
        """Persist a new or updated recommendation."""
        ...

    @abc.abstractmethod
    async def get_by_id(self, recommendation_id: uuid.UUID) -> RestockRecommendation:
        """
        Return a recommendation by ID.

        Raises:
            NotFoundError: if no recommendation with this ID exists.
        """
        ...

    @abc.abstractmethod
    async def get_latest_for_merchant(
        self,
        merchant_id: MerchantId,
        limit: int = 10,
    ) -> Sequence[RestockRecommendation]:
        """Return the N most recent recommendations for a merchant, newest first."""
        ...


class InMemoryRecommendationRepository(RecommendationRepository):
    """In-memory fake for unit tests — not for production use."""

    def __init__(self) -> None:
        self._store: dict[uuid.UUID, RestockRecommendation] = {}

    async def save(self, recommendation: RestockRecommendation) -> None:
        self._store[recommendation.id] = recommendation

    async def get_by_id(self, recommendation_id: uuid.UUID) -> RestockRecommendation:
        try:
            return self._store[recommendation_id]
        except KeyError:
            raise NotFoundError("RestockRecommendation", str(recommendation_id)) from None

    async def get_latest_for_merchant(
        self,
        merchant_id: MerchantId,
        limit: int = 10,
    ) -> Sequence[RestockRecommendation]:
        matching = [
            r for r in self._store.values() if r.merchant_id == merchant_id
        ]
        matching.sort(key=lambda r: r.created_at, reverse=True)
        return matching[:limit]

    def count(self) -> int:
        return len(self._store)
