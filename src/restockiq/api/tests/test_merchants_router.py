"""
Merchants router API tests.
Uses FastAPI TestClient with in-memory fakes (see tests/conftest.py).
No database, no HTTP to external services.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


class TestMerchantsRouter:
    def test_register_merchant_returns_201(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/merchants",
            json={"name": "Corner Shop", "currency": "ETB"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Corner Shop"
        assert data["currency"] == "ETB"
        assert "id" in data

    def test_get_merchant_returns_registered_merchant(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api/v1/merchants",
            json={"name": "My Shop", "currency": "ETB"},
        )
        merchant_id = create_resp.json()["id"]

        get_resp = client.get(f"/api/v1/merchants/{merchant_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "My Shop"

    def test_get_nonexistent_merchant_returns_404(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/merchants/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_add_sku_to_catalog_returns_201(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api/v1/merchants",
            json={"name": "Shop", "currency": "ETB"},
        )
        merchant_id = create_resp.json()["id"]

        sku_resp = client.post(
            f"/api/v1/merchants/{merchant_id}/catalog",
            json={
                "code": "SUGAR-1KG",
                "name": "Sugar 1kg",
                "cost_price": "20.00",
                "sell_price": "25.00",
            },
        )
        assert sku_resp.status_code == 201
        catalog = sku_resp.json()
        assert len(catalog) == 1
        assert catalog[0]["code"] == "SUGAR-1KG"

    def test_add_duplicate_sku_returns_409(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api/v1/merchants",
            json={"name": "Shop", "currency": "ETB"},
        )
        merchant_id = create_resp.json()["id"]
        sku_payload = {
            "code": "SUGAR",
            "name": "Sugar",
            "cost_price": "20.00",
            "sell_price": "25.00",
        }
        client.post(f"/api/v1/merchants/{merchant_id}/catalog", json=sku_payload)
        resp = client.post(f"/api/v1/merchants/{merchant_id}/catalog", json=sku_payload)
        assert resp.status_code == 409

    def test_health_endpoint_returns_200(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
