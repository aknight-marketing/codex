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
    stock_evidence: str | None = None
    review_reason: str | None = None
    status_label: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MonitorResult:
    generated_at: str
    mode: str
    shortlist: list[Listing]
    needs_review: list[Listing]
    unavailable: list[Listing]
    vendor_errors: list[dict[str, str]]
    vendor_status: list[dict[str, Any]] = field(default_factory=list)
    state_changes: list[dict[str, Any]] = field(default_factory=list)
    used_test_mode: bool = False
    degraded: bool = False
    trust_label: str = "unknown"
    production_readiness: str = "unknown"
    readiness_reasons: list[str] = field(default_factory=list)
