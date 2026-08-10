"""
Injectable time source for deterministic, testable time logic.

Anywhere the domain or application services need "the current time" they
must accept a Clock dependency — never call datetime.now() directly.
This lets tests freeze time to a known value and remove all flakiness
from time-sensitive assertions.
"""

from __future__ import annotations

import abc
from datetime import UTC, datetime, timedelta


class Clock(abc.ABC):
    """Abstract injectable time source."""

    @abc.abstractmethod
    def now(self) -> datetime:
        """Return the current moment as a timezone-aware UTC datetime."""
        ...


class SystemClock(Clock):
    """
    Real wall-clock time source backed by datetime.now(UTC).
    Use this in production dependency injection.
    """

    def now(self) -> datetime:
        return datetime.now(tz=UTC)


class FakeClock(Clock):
    """
    Deterministic, injectable time source for unit tests.

    The clock is initialised to a fixed point in time (default: 2024-01-01 UTC)
    and can be advanced manually via `advance()`.  This makes time-sensitive
    tests completely deterministic regardless of when they actually run.

    Example::

        clock = FakeClock()
        assert clock.now().year == 2024
        clock.advance(days=7)
        assert clock.now().day == 8
    """

    _DEFAULT_START = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)

    def __init__(self, fixed_time: datetime | None = None) -> None:
        if fixed_time is not None and fixed_time.tzinfo is None:
            raise ValueError("FakeClock fixed_time must be timezone-aware.")
        self._time: datetime = fixed_time or self._DEFAULT_START

    def now(self) -> datetime:
        return self._time

    def advance(self, **kwargs: int) -> None:
        """
        Advance the clock by a timedelta.  Accepts the same keyword arguments
        as datetime.timedelta (days, hours, minutes, seconds, etc.).

        Example::

            clock.advance(days=1, hours=6)
        """
        self._time = self._time + timedelta(**kwargs)

    def set(self, new_time: datetime) -> None:
        """Jump the clock to an arbitrary datetime (must be timezone-aware)."""
        if new_time.tzinfo is None:
            raise ValueError("Clock.set() requires a timezone-aware datetime.")
        self._time = new_time
