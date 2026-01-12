"""
Core Module - System Clock.

============================================================
RESPONSIBILITY
============================================================
Provides a unified, testable clock abstraction for the entire system.

- All time-related operations MUST use this clock
- Enables deterministic testing and replay
- Ensures consistent timestamps across all modules
- Supports time freezing for backtesting

============================================================
DESIGN PRINCIPLES
============================================================
- Single source of truth for system time
- UTC only - no timezone conversions in business logic
- Mockable for testing
- Thread-safe

============================================================
"""

from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Generator, Optional
import threading
import time


# ============================================================
# CLOCK PROTOCOL
# ============================================================

class ClockProtocol(ABC):
    """Abstract interface for system clock."""
    
    @abstractmethod
    def now(self) -> datetime:
        """Get current UTC datetime."""
        pass
    
    @abstractmethod
    def timestamp(self) -> float:
        """Get current Unix timestamp."""
        pass
    
    @abstractmethod
    def today(self) -> date:
        """Get current UTC date."""
        pass
    
    def is_trading_hours(self) -> bool:
        """Check if within trading hours (crypto = always)."""
        return True  # Crypto markets are 24/7
    
    def time_until_next_hour(self) -> timedelta:
        """Get time until next hour boundary."""
        now = self.now()
        next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        return next_hour - now
    
    def format_iso(self, dt: Optional[datetime] = None) -> str:
        """Format datetime as ISO 8601."""
        dt = dt or self.now()
        return dt.isoformat()
    
    @staticmethod
    def parse_iso(iso_string: str) -> datetime:
        """Parse ISO 8601 string to datetime."""
        return datetime.fromisoformat(iso_string)


# ============================================================
# SYSTEM CLOCK (PRODUCTION)
# ============================================================

class SystemClock(ClockProtocol):
    """
    Production clock using actual system time.
    
    All times are in UTC.
    """
    
    def now(self) -> datetime:
        """Get current UTC datetime."""
        return datetime.now(timezone.utc)
    
    def timestamp(self) -> float:
        """Get current Unix timestamp."""
        return time.time()
    
    def today(self) -> date:
        """Get current UTC date."""
        return datetime.now(timezone.utc).date()


# ============================================================
# MOCK CLOCK (TESTING)
# ============================================================

class MockClock(ClockProtocol):
    """
    Mock clock for testing.
    
    Allows time manipulation for deterministic tests.
    """
    
    def __init__(self, initial_time: Optional[datetime] = None):
        """
        Initialize mock clock.
        
        Args:
            initial_time: Starting time (defaults to current UTC)
        """
        self._time = initial_time or datetime.now(timezone.utc)
        self._lock = threading.Lock()
    
    def now(self) -> datetime:
        """Get current (mocked) datetime."""
        with self._lock:
            return self._time
    
    def timestamp(self) -> float:
        """Get current (mocked) timestamp."""
        with self._lock:
            return self._time.timestamp()
    
    def today(self) -> date:
        """Get current (mocked) date."""
        with self._lock:
            return self._time.date()
    
    def set_time(self, new_time: datetime) -> None:
        """Set the current time."""
        with self._lock:
            if new_time.tzinfo is None:
                new_time = new_time.replace(tzinfo=timezone.utc)
            self._time = new_time
    
    def advance(self, seconds: float = 0, **kwargs) -> None:
        """
        Advance time by the specified amount.
        
        Args:
            seconds: Number of seconds to advance
            **kwargs: Passed to timedelta (hours, minutes, days, etc.)
        """
        with self._lock:
            delta = timedelta(seconds=seconds, **kwargs)
            self._time = self._time + delta
    
    @contextmanager
    def freeze(self, at_time: Optional[datetime] = None) -> Generator[None, None, None]:
        """
        Context manager to freeze time.
        
        Args:
            at_time: Time to freeze at (defaults to current)
        """
        with self._lock:
            original_time = self._time
            if at_time:
                if at_time.tzinfo is None:
                    at_time = at_time.replace(tzinfo=timezone.utc)
                self._time = at_time
        
        try:
            yield
        finally:
            with self._lock:
                self._time = original_time


# ============================================================
# REPLAY CLOCK (BACKTESTING)
# ============================================================

class ReplayClock(ClockProtocol):
    """
    Replay clock for backtesting.
    
    Reads time from historical data replay.
    """
    
    def __init__(
        self,
        start_time: datetime,
        speed_multiplier: float = 1.0,
    ):
        """
        Initialize replay clock.
        
        Args:
            start_time: Replay start time
            speed_multiplier: Replay speed (1.0 = real-time)
        """
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        
        self._start_time = start_time
        self._current_time = start_time
        self._speed_multiplier = speed_multiplier
        self._real_start = time.time()
        self._paused = False
        self._lock = threading.Lock()
    
    def now(self) -> datetime:
        """Get current replay time."""
        with self._lock:
            if self._paused:
                return self._current_time
            
            # Calculate elapsed real time
            elapsed_real = time.time() - self._real_start
            elapsed_replay = elapsed_real * self._speed_multiplier
            
            return self._start_time + timedelta(seconds=elapsed_replay)
    
    def timestamp(self) -> float:
        """Get current replay timestamp."""
        return self.now().timestamp()
    
    def today(self) -> date:
        """Get current replay date."""
        return self.now().date()
    
    def set_time(self, new_time: datetime) -> None:
        """Jump to a specific time in the replay."""
        with self._lock:
            if new_time.tzinfo is None:
                new_time = new_time.replace(tzinfo=timezone.utc)
            self._current_time = new_time
            self._start_time = new_time
            self._real_start = time.time()
    
    def pause(self) -> None:
        """Pause the replay."""
        with self._lock:
            self._current_time = self.now()
            self._paused = True
    
    def resume(self) -> None:
        """Resume the replay."""
        with self._lock:
            self._start_time = self._current_time
            self._real_start = time.time()
            self._paused = False
    
    def set_speed(self, multiplier: float) -> None:
        """Set replay speed multiplier."""
        with self._lock:
            # Preserve current position
            current = self.now()
            self._current_time = current
            self._start_time = current
            self._real_start = time.time()
            self._speed_multiplier = multiplier
    
    @property
    def is_paused(self) -> bool:
        """Check if replay is paused."""
        return self._paused
    
    @property
    def speed_multiplier(self) -> float:
        """Get current speed multiplier."""
        return self._speed_multiplier


# ============================================================
# CLOCK FACTORY
# ============================================================

class ClockFactory:
    """Factory for creating clock instances."""
    
    _instance: Optional[ClockProtocol] = None
    _lock = threading.Lock()
    
    @classmethod
    def get_clock(cls) -> ClockProtocol:
        """Get the global clock instance."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = SystemClock()
            return cls._instance
    
    @classmethod
    def set_clock(cls, clock: ClockProtocol) -> None:
        """Set the global clock instance."""
        with cls._lock:
            cls._instance = clock
    
    @classmethod
    def reset(cls) -> None:
        """Reset to default system clock."""
        with cls._lock:
            cls._instance = SystemClock()
    
    @classmethod
    @contextmanager
    def use_mock(
        cls,
        initial_time: Optional[datetime] = None,
    ) -> Generator[MockClock, None, None]:
        """
        Context manager to use mock clock temporarily.
        
        Args:
            initial_time: Initial time for mock clock
        """
        original = cls._instance
        mock = MockClock(initial_time)
        cls.set_clock(mock)
        try:
            yield mock
        finally:
            cls._instance = original
    
    @classmethod
    @contextmanager
    def use_replay(
        cls,
        start_time: datetime,
        speed_multiplier: float = 1.0,
    ) -> Generator[ReplayClock, None, None]:
        """
        Context manager to use replay clock temporarily.
        
        Args:
            start_time: Replay start time
            speed_multiplier: Replay speed
        """
        original = cls._instance
        replay = ReplayClock(start_time, speed_multiplier)
        cls.set_clock(replay)
        try:
            yield replay
        finally:
            cls._instance = original


# ============================================================
# TIMESTAMP UTILITIES
# ============================================================

def to_iso8601(dt: datetime) -> str:
    """Convert datetime to ISO 8601 string."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def from_iso8601(iso_string: str) -> datetime:
    """Parse ISO 8601 string to datetime."""
    dt = datetime.fromisoformat(iso_string)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def now_utc() -> datetime:
    """Get current UTC time using global clock."""
    return ClockFactory.get_clock().now()


def today_utc() -> date:
    """Get current UTC date using global clock."""
    return ClockFactory.get_clock().today()


def timestamp_now() -> float:
    """Get current timestamp using global clock."""
    return ClockFactory.get_clock().timestamp()


# ============================================================
# EXPORTS
# ============================================================

__all__ = [
    # Protocols
    "ClockProtocol",
    
    # Implementations
    "SystemClock",
    "MockClock",
    "ReplayClock",
    
    # Factory
    "ClockFactory",
    
    # Utilities
    "to_iso8601",
    "from_iso8601",
    "now_utc",
    "today_utc",
    "timestamp_now",
]
