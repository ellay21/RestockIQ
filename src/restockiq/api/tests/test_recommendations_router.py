
# Recommendations router API tests.

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


class TestRecommendationsRouter:
    def test_get_recommendations_for_merchant_with_no_signals_returns_404(
        self, client: TestClient
    ) -> None:
        merchant_id = str(uuid.uuid4())
        response = client.post(f"/api/v1/merchants/{merchant_id}/recommendations")
        # Should 404 because there are no signals
        assert response.status_code == 404

    def test_list_recommendations_for_merchant_with_no_data_returns_empty_list(
        self, client: TestClient
    ) -> None:
        merchant_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/merchants/{merchant_id}/recommendations")
        assert response.status_code == 200
        assert response.json() == []
