from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class Market:

    platform: str
    market_id: str
    title: str
    description: str = ""
    category: str = "Other"

    yes_price: float = 0.0
    no_price: float = 0.0
    volume_usd: float = 0.0
    liquidity_usd: float = 0.0

    created_at: Optional[datetime] = None
    closes_at: Optional[datetime] = None
    resolved: bool = False
    outcome: Optional[str] = None

    related_news: list[str] = field(default_factory=list)
    rag_doc_ids: list[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return (
            f"Market({self.platform}:{self.market_id} "
            f"'{self.title[:40]}' yes={self.yes_price:.0%} vol=${self.volume_usd:,.0f})"
        )

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "market_id": self.market_id,
            "title": self.title,
            "description": self.description[:300],
            "category": self.category,
            "yes_price": round(self.yes_price, 4),
            "no_price": round(self.no_price, 4),
            "volume_usd": round(self.volume_usd, 2),
            "liquidity_usd": round(self.liquidity_usd, 2),
            "closes_at": self.closes_at.isoformat() if self.closes_at else None,
            "resolved": self.resolved,
            "outcome": self.outcome,
        }
