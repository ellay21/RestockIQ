"""
Signals router API tests.
Tests manual entry and CSV upload endpoints.
"""

from __future__ import annotations

import io
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

VALID_CSV = b"sku_code,quantity_sold,period_days\nSUGAR-1KG,50,7\nOIL-1L,20,7\n"


class TestSignalsRouter:
    def test_ingest_manual_signal_returns_201(self, client: TestClient) -> None:
        merchant_id = str(uuid.uuid4())
        response = client.post(
            f"/api/v1/merchants/{merchant_id}/signals/manual",
            json={
                "merchant_id": merchant_id,
                "currency": "ETB",
                "cash_on_hand": "500.00",
                "sales": [
                    {"sku_code": "SUGAR-1KG", "quantity_sold": 50, "period_days": 7},
                    {"sku_code": "OIL-1L", "quantity_sold": 20, "period_days": 7},
                ],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["input_method"] == "manual_entry"
        assert data["sales_record_count"] == 2

    def test_ingest_csv_signal_returns_201(self, client: TestClient) -> None:
        merchant_id = str(uuid.uuid4())
        response = client.post(
            f"/api/v1/merchants/{merchant_id}/signals/csv",
            data={"cash_on_hand": "500.00", "currency": "ETB"},
            files={"file": ("sales.csv", io.BytesIO(VALID_CSV), "text/csv")},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["input_method"] == "csv_import"
        assert data["sales_record_count"] == 2

    def test_manual_signal_with_empty_sales_returns_422(self, client: TestClient) -> None:
        merchant_id = str(uuid.uuid4())
        response = client.post(
            f"/api/v1/merchants/{merchant_id}/signals/manual",
            json={
                "merchant_id": merchant_id,
                "currency": "ETB",
                "cash_on_hand": "500.00",
                "sales": [],  # Violates min_length=1
            },
        )
        assert response.status_code == 422

    def test_manual_signal_missing_cash_returns_422(self, client: TestClient) -> None:
        merchant_id = str(uuid.uuid4())
        response = client.post(
            f"/api/v1/merchants/{merchant_id}/signals/manual",
            json={
                "merchant_id": merchant_id,
                "currency": "ETB",
                # cash_on_hand missing
                "sales": [{"sku_code": "SUGAR", "quantity_sold": 10, "period_days": 7}],
            },
        )
        assert response.status_code == 422
