"""
In-memory fake RecommendationRepository for cross-module tests.

Re-exports InMemoryRecommendationRepository for import from tests/fakes/.
"""

from __future__ import annotations

from restockiq.recommendations.repository import InMemoryRecommendationRepository

__all__ = ["InMemoryRecommendationRepository"]
