"""
Signal ports — abstract contracts for signal ingestion and persistence.

Both ABCs live here so the application service can depend on the abstraction
without knowing which concrete adapter is wired in.

Hexagonal rigor: FULL — no concrete adapter or framework imports permitted.
"""
from __future__ import annotations

import abc
from typing import TYPE_CHECKING

# Forward reference — domain is imported here because ports are "owned" by
# the domain side and are allowed to reference domain types.

if TYPE_CHECKING:
    from collections.abc import Sequence

    from restockiq.shared_kernel.value_objects import MerchantId
    from restockiq.signals.domain import MerchantFinancialSignal


class SignalSourcePort(abc.ABC):
    """
    Port: contract that every inbound signal adapter must implement.

    Adapters translate their specific raw input format into the canonical
    MerchantFinancialSignal shape.

    Implementations:
      - ManualEntryAdapter  — translates a merchant-filled form payload
      - CsvImportAdapter    — translates an uploaded CSV file
      - WeretAdapter        — translates a WERET webhook payload
      - PosAdapter          — not supported in this release (raises AdapterError)
    """

    @abc.abstractmethod
    def build_signal(self, raw_input: object) -> MerchantFinancialSignal:
        """
        Translate adapter-specific raw input into a MerchantFinancialSignal.

        Args:
            raw_input: The adapter-specific payload.  The type is `object`
                       here because each adapter has a different raw type
                       (dict for manual entry, bytes for CSV, etc.).

        Raises:
            AdapterError: if the raw input cannot be translated.
            SignalValidationError: if the produced signal fails domain invariants.
        """
        ...


class SignalRepository(abc.ABC):
    """
    Port: persistence contract for raw MerchantFinancialSignal records.

    Implementations:
      - InMemorySignalRepository  — in-memory fake for unit tests
      - PostgresSignalRepository  — production Postgres-backed implementation
    """

    @abc.abstractmethod
    async def save(self, signal: MerchantFinancialSignal) -> None:
        """Persist a signal snapshot."""
        ...

    @abc.abstractmethod
    async def get_history_for_merchant(
        self,
        merchant_id: MerchantId,
        limit: int = 30,
    ) -> Sequence[MerchantFinancialSignal]:
        """
        Return recent signal snapshots for a merchant, newest first.

        Args:
            merchant_id: The merchant to fetch history for.
            limit:       Maximum number of snapshots to return.
        """
        ...
