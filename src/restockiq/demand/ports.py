"""
Demand ports — read-only view over signal history for demand estimation.

This port is intentionally narrow: the demand estimator only needs a
filtered, flattened view of SkuSalesRecords.  It does not need to know
about the full signal structure or mutation capabilities.

Hexagonal rigor: FULL — no I/O or adapter imports.
"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from restockiq.shared_kernel.value_objects import MerchantId, SkuCode
    from restockiq.signals.domain import SkuSalesRecord


class DemandHistoryRepository(abc.ABC):
    """
    Port: read-only view over a merchant's historical SKU sales data.

    This is a projection of SignalRepository tailored for the demand estimator.
    The Postgres implementation will query the signals table and
    return flattened SkuSalesRecord rows.

    Implementations:
      - InMemoryDemandHistoryRepository  (unit tests, supplied via FakeSignalSource)
      - PostgresDemandHistoryRepository
    """

    @abc.abstractmethod
    def get_sales_records_for_sku(
        self,
        merchant_id: MerchantId,
        sku_code: SkuCode,
        limit: int = 52,  # 52 weeks ≈ 1 year of weekly snapshots
    ) -> Sequence[SkuSalesRecord]:
        """
        Return historical sales records for a specific SKU.

        Records should be returned newest-first so the caller can easily
        take the N most recent observations.

        Args:
            merchant_id: The merchant to scope the query to.
            sku_code:    The SKU to fetch records for.
            limit:       Maximum number of records to return.
        """
        ...

    @abc.abstractmethod
    def get_all_sku_codes_for_merchant(
        self,
        merchant_id: MerchantId,
    ) -> Sequence[SkuCode]:
        """
        Return all SKU codes that appear in a merchant's signal history.

        Used to enumerate the SKUs the demand estimator should compute
        distributions for.
        """
        ...
