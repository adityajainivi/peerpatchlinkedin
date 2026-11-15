"""HTML shaped like LinkedIn's pages, with the content swapped for test data."""
from __future__ import annotations

import html
from datetime import datetime


def urn_for(when: datetime, kind: str = "activity", salt: int = 12345) -> str:
    """Build a post URN whose top 41 bits hold `when`, the way LinkedIn's do."""
    ms = round(when.timestamp() * 1000)
    return f"urn:li:{kind}:{(ms << 22) | (salt & 0x3FFFFF)}"
