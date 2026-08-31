"""Shared utility helpers."""
from datetime import datetime


def now_str() -> str:
    """Return current local time as ISO-8601 string without microseconds."""
    return datetime.now().isoformat(timespec='seconds')


def sizeof_fmt(num: int) -> str:
    """Convert a byte count to a human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(num) < 1024.0:
            return f"{num:.1f}{unit}"
        num /= 1024.0
    return f"{num:.1f}TB"
