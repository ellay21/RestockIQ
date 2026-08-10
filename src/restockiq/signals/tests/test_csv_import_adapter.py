"""
CsvImportAdapter tests.

Both adapters (ManualEntry and Csv) must produce structurally identical
MerchantFinancialSignal objects — this proves the port abstraction works, not
just that each adapter works in isolation.
"""

from __future__ import annotations

import pytest

from restockiq.shared_kernel.errors import AdapterError
from restockiq.shared_kernel.value_objects import MerchantId, SkuCode
from restockiq.signals.adapters.csv_import_adapter import CsvImportAdapter
from restockiq.signals.adapters.manual_entry_adapter import ManualEntryAdapter
from restockiq.signals.domain import MerchantFinancialSignal, SignalInputMethod

WELL_FORMED_CSV = """\
sku_code,quantity_sold,period_days
SUGAR-1KG,50,7
OIL-1L,20,7
"""

MALFORMED_ROW_CSV = """\
sku_code,quantity_sold,period_days
SUGAR-1KG,50,7
OIL-1L,not-a-number,7
"""

MISSING_COLUMN_CSV = """\
sku_code,quantity_sold
SUGAR-1KG,50
"""


@pytest.fixture
def csv_adapter() -> CsvImportAdapter:
    return CsvImportAdapter()


@pytest.fixture
def merchant_id_str() -> str:
    return str(MerchantId.generate())


@pytest.fixture
def valid_csv_input(merchant_id_str: str) -> dict:
    return {
        "merchant_id": merchant_id_str,
        "currency": "ETB",
        "cash_on_hand": "500.00",
        "csv_content": WELL_FORMED_CSV,
    }


class TestCsvImportAdapter:
    def test_csv_import_adapter_parses_well_formed_csv(
        self, csv_adapter: CsvImportAdapter, valid_csv_input: dict
    ) -> None:
        signal = csv_adapter.build_signal(valid_csv_input)
        assert isinstance(signal, MerchantFinancialSignal)
        assert signal.input_method == SignalInputMethod.CSV_IMPORT
        assert len(signal.sales_records) == 2

    def test_csv_sku_codes_are_normalised_to_uppercase(
        self, csv_adapter: CsvImportAdapter, merchant_id_str: str
    ) -> None:
        csv_content = "sku_code,quantity_sold,period_days\nsugar-1kg,50,7\n"
        signal = csv_adapter.build_signal(
            {
                "merchant_id": merchant_id_str,
                "currency": "ETB",
                "cash_on_hand": "500",
                "csv_content": csv_content,
            }
        )
        assert SkuCode("SUGAR-1KG") in signal.sku_codes

    def test_csv_import_adapter_rejects_malformed_row_with_clear_error(
        self, csv_adapter: CsvImportAdapter, merchant_id_str: str
    ) -> None:
        with pytest.raises(AdapterError) as exc_info:
            csv_adapter.build_signal(
                {
                    "merchant_id": merchant_id_str,
                    "currency": "ETB",
                    "cash_on_hand": "500",
                    "csv_content": MALFORMED_ROW_CSV,
                }
            )
        err = exc_info.value
        # Must identify the row and the problem field
        assert "row 3" in err.reason or "quantity_sold" in (err.field or "")

    def test_csv_missing_required_column_raises(
        self, csv_adapter: CsvImportAdapter, merchant_id_str: str
    ) -> None:
        with pytest.raises(AdapterError) as exc_info:
            csv_adapter.build_signal(
                {
                    "merchant_id": merchant_id_str,
                    "currency": "ETB",
                    "cash_on_hand": "500",
                    "csv_content": MISSING_COLUMN_CSV,
                }
            )
        assert "period_days" in exc_info.value.reason

    def test_csv_bytes_input_is_accepted(
        self, csv_adapter: CsvImportAdapter, merchant_id_str: str
    ) -> None:
        signal = csv_adapter.build_signal(
            {
                "merchant_id": merchant_id_str,
                "currency": "ETB",
                "cash_on_hand": "500",
                "csv_content": WELL_FORMED_CSV.encode("utf-8"),
            }
        )
        assert len(signal.sales_records) == 2

    def test_empty_csv_body_raises(
        self, csv_adapter: CsvImportAdapter, merchant_id_str: str
    ) -> None:
        """A CSV with a header but no data rows is rejected."""
        with pytest.raises(AdapterError, match="no data rows"):
            csv_adapter.build_signal(
                {
                    "merchant_id": merchant_id_str,
                    "currency": "ETB",
                    "cash_on_hand": "500",
                    "csv_content": "sku_code,quantity_sold,period_days\n",
                }
            )


class TestBothAdaptersProduceIdenticalSignalShape:
    """
    both adapters produce the same
    MerchantFinancialSignal shape from equivalent inputs.  This is the key
    proof that the SignalSourcePort abstraction actually works.
    """

    def test_manual_and_csv_signals_are_structurally_identical(self, merchant_id_str: str) -> None:
        manual_adapter = ManualEntryAdapter()
        csv_adapter = CsvImportAdapter()

        manual_signal = manual_adapter.build_signal(
            {
                "merchant_id": merchant_id_str,
                "currency": "ETB",
                "cash_on_hand": "500",
                "sales": [
                    {"sku_code": "SUGAR-1KG", "quantity_sold": 50, "period_days": 7},
                ],
            }
        )
        csv_signal = csv_adapter.build_signal(
            {
                "merchant_id": merchant_id_str,
                "currency": "ETB",
                "cash_on_hand": "500",
                "csv_content": "sku_code,quantity_sold,period_days\nSUGAR-1KG,50,7\n",
            }
        )

        # Structural equivalence: same merchant, same cash, same SKU, same sales
        assert manual_signal.merchant_id == csv_signal.merchant_id
        assert manual_signal.cash_on_hand == csv_signal.cash_on_hand
        assert manual_signal.sku_codes == csv_signal.sku_codes
        manual_rec = manual_signal.sales_records[0]
        csv_rec = csv_signal.sales_records[0]
        assert manual_rec.sku_code == csv_rec.sku_code
        assert manual_rec.quantity_sold == csv_rec.quantity_sold
        assert manual_rec.period_days == csv_rec.period_days
