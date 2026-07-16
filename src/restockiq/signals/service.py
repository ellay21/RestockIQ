"""
SignalService — application service: receive, validate, and persist signals.

Orchestrates: raw input → adapter.build_signal() → validate → repository.save().
The service is adapter-agnostic — it accepts any SignalSourcePort implementation.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from restockiq.signals.domain import MerchantFinancialSignal
    from restockiq.signals.ports import SignalRepository, SignalSourcePort


class SignalService:
    """
    Orchestrates signal ingestion from any source.

    This service is intentionally thin: validation is the responsibility of
    the domain value objects and the adapter; the service just connects them.
    """

    def __init__(self, repository: SignalRepository) -> None:
        self._repo = repository

    async def ingest_from_adapter(
        self,
        adapter: SignalSourcePort,
        raw_input: object,
    ) -> MerchantFinancialSignal:
        """
        Translate raw adapter input into a signal, validate it, and persist it.

        Args:
            adapter:    The adapter that knows how to parse `raw_input`.
            raw_input:  The adapter-specific raw payload.

        Returns:
            The validated and persisted MerchantFinancialSignal.

        Raises:
            AdapterError:          if the adapter cannot translate the input.
            SignalValidationError:  if the domain invariants are violated.
        """
        signal = adapter.build_signal(raw_input)
        await self._repo.save(signal)
        return signal

    async def ingest_signal(self, signal: MerchantFinancialSignal) -> MerchantFinancialSignal:
        """
        Persist an already-constructed signal (e.g. built directly in tests).

        Raises:
            SignalValidationError: if the signal fails domain invariants.
        """
        await self._repo.save(signal)
        return signal
