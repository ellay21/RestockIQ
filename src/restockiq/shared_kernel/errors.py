"""
Domain-level exception hierarchy shared across all RestockIQ modules.

All exceptions inherit from RestockIQError so callers can catch the broad
base type or the specific sub-type — whichever is appropriate.  No third-party
library types appear here; this module has zero external dependencies.
"""
from __future__ import annotations


class RestockIQError(Exception):
    """Base exception for every domain-level error in RestockIQ."""


# Validation 


class DomainValidationError(RestockIQError):
    """
    Raised when a domain invariant is violated during object construction
    or a state-changing operation.

    Examples:
        - Money amount is negative
        - SKU sell_price is below cost_price
        - MerchantFinancialSignal has no SKU records
    """


class SignalValidationError(DomainValidationError):
    """
    Raised specifically when a MerchantFinancialSignal fails validation.
    Subclass of DomainValidationError so callers can catch either.
    """


class AdapterError(RestockIQError):
    """
    Raised when a signal adapter cannot translate its raw input into a
    valid MerchantFinancialSignal.  Carries the offending field/row so the
    caller can surface a meaningful error message to the merchant.
    """

    def __init__(self, source: str, reason: str, *, field: str | None = None) -> None:
        detail = f"[{source}] {reason}"
        if field:
            detail += f" (field: {field})"
        super().__init__(detail)
        self.source = source
        self.reason = reason
        self.field = field


# Lookup


class NotFoundError(RestockIQError):
    """
    Raised when a requested entity does not exist in the repository.

    Attributes:
        entity_type: Human-readable name of the missing entity (e.g. "Merchant").
        identifier:  The ID or code that was looked up.
    """

    def __init__(self, entity_type: str, identifier: str) -> None:
        super().__init__(f"{entity_type} not found: {identifier}")
        self.entity_type = entity_type
        self.identifier = identifier


class ConflictError(RestockIQError):
    """
    Raised when an operation would violate a uniqueness constraint — for
    example, registering a merchant with an ID that already exists.

    Attributes:
        entity_type: Human-readable name of the conflicting entity.
        identifier:  The ID or code that caused the conflict.
    """

    def __init__(self, entity_type: str, identifier: str) -> None:
        super().__init__(f"{entity_type} already exists: {identifier}")
        self.entity_type = entity_type
        self.identifier = identifier


# External services


class ExternalServiceError(RestockIQError):
    """
    Raised when an outbound call to an external service (e.g. WERET API)
    fails in a way that is not a transient network error.

    Attributes:
        service:  Name of the external service (e.g. "WERET").
        message:  Description of the failure.
    """

    def __init__(self, service: str, message: str) -> None:
        super().__init__(f"External service error [{service}]: {message}")
        self.service = service


# Optimisation


class OptimizationError(RestockIQError):
    """
    Raised when the cash-constrained optimizer cannot produce a valid
    OrderPlan — for example, when the problem is infeasible.
    """
