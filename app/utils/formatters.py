"""Utility functions for formatting data for display."""

from datetime import date, datetime
from typing import Optional, Union


def format_date(d: Optional[Union[date, datetime]], fmt: str = "%m/%d/%Y") -> str:
    if not hasattr(d, "strftime"):
        return "N/A"
    try:
        return d.strftime(fmt)
    except (ValueError, AttributeError):
        return "N/A"


def format_percent(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}%"


def format_hours(hours: float) -> str:
    if hours < 1:
        return f"{int(hours * 60)}m"
    h = int(hours)
    m = int((hours - h) * 60)
    return f"{h}h {m}m" if m else f"{h}h"


def truncate(text: str, max_len: int = 50) -> str:
    return text if len(text) <= max_len else text[: max_len - 3] + "..."
