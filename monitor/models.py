from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Listing:
    timestamp: str
    vendor: str
    vendor_key: str
    title: str
    chip: str | None = None
    ram_gb: int | None = None
    ssd_gb: int | None = None
    screen_size_in: float | None = None
    condition: str | None = None
    stock_status: str | None = None
    price_gbp: float | None = None
    warranty: str | None = None
    returns: str | None = None
    delivery_estimate: str | None = None
    keyboard_layout: str | None = None
    url: str | None = None
    seller_quality_score: float = 0.0
    spec_fit_score: float = 0.0
    value_score: float = 0.0
    total_score: float = 0.0
    notes: str | None = None
    buy_now: bool = False
    rationale: str | None = None
    source_url: str | None = None
    availability_text: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["raw"] = self.raw
        return data
