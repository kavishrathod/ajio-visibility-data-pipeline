from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RawResponse:
    """What an adapter returns. The parser consumes this; it never knows which adapter made it."""
    keyword: str
    page: int
    http_status: int
    body: str
    headers: dict = field(default_factory=dict)
    is_mock: bool = False
    fetched_at: str = ""   # UTC ISO-8601


@dataclass
class Unit:
    """One product unit as parsed, before ranks are assigned."""
    product_type: str                 # "Organic" | "SP" | "SB"
    product_name: Optional[str] = None
    product_url: Optional[str] = None
    product_id: Optional[str] = None
    sp: Optional[str] = None          # exact decimal string e.g. "1299.00" (null if not shown)
    mrp: Optional[str] = None
    rating: Optional[float] = None
    num_of_rating: Optional[int] = None
    tag: str = ""
    deal: str = ""
    product_image_url: Optional[str] = None
    campaign_id: Optional[str] = None


@dataclass
class ParseResult:
    # ok | zero_result | parse_failed
    status: str
    units: list = field(default_factory=list)
    reason: str = ""
