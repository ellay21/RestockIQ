"""
POS (Point-of-Sale) Adapter — stub for future integration.

This adapter is intentionally left unimplemented in the MVP.  It is a
placeholder documenting where a POS system integration would live so that
the architecture remains open for extension without modification.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from restockiq.shared_kernel.errors import AdapterError
from restockiq.signals.ports import SignalSourcePort

if TYPE_CHECKING:
    from restockiq.signals.domain import MerchantFinancialSignal


class PosAdapter(SignalSourcePort):
    """
    Future POS integration adapter — NOT IMPLEMENTED.

    When implemented, this adapter will translate point-of-sale transaction
    data (from a POS system API or export) into a MerchantFinancialSignal,
    enabling RestockIQ to work for merchants with a modern POS setup.
    """

    def build_signal(self, raw_input: object) -> MerchantFinancialSignal:
        raise AdapterError(
            "PosAdapter",
            "POS adapter is not implemented in this release. "
            "Use ManualEntryAdapter or CsvImportAdapter instead.",
        )
