"""Base classes and data structures for all collectors."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class CollectedData:
    """
    Normalized output from any data collector.

    Key design principle — availability_time:
    The time at which this data point was first publicly available.
    This is critical for avoiding look-ahead bias in backtesting.
    """

    source: str                    # e.g. "bloomberg", "fred", "cftc"
    symbol: str | None             # e.g. "XAUUSD", "DXY"
    event_time: datetime | None    # when the event/price actually happened
    available_time: datetime       # when this data became publicly available
    fetched_at: datetime          # when we fetched it
    raw_payload: dict[str, Any]    # original API response
    normalized_payload: dict[str, Any] | None = None


class BaseCollector(ABC):
    """
    Abstract base for all data collectors.

    Each collector is responsible for fetching one category of data
    and returning a list of CollectedData items.
    """

    name: str

    @abstractmethod
    async def collect(self) -> list[CollectedData]:
        """Fetch data and return a list of CollectedData items."""
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"
