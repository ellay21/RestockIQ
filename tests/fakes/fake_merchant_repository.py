"""
In-memory fake MerchantRepository for use in cross-module tests.

This is a re-export of InMemoryMerchantRepository from merchants/repository.py,
living in tests/fakes/ so cross-module test files can import it from a single
known location without depending on merchant-module internals.
"""

from __future__ import annotations

from restockiq.merchants.repository import InMemoryMerchantRepository

__all__ = ["InMemoryMerchantRepository"]
