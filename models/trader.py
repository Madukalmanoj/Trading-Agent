from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class Trader:

    platform: str
    identifier: str
    display_name: Optional[str] = None

    win_rate: float = 0.0
    roi: float = 0.0
    total_trades: int = 0
    total_volume_usd: float = 0.0
    profit_loss_usd: float = 0.0

    last_active: Optional[datetime] = None
    active_markets: list[str] = field(default_factory=list)

    niche_scores: dict[str, float] = field(default_factory=dict)
    primary_niche: Optional[str] = None

    trust_score: float = 0.5

    def __repr__(self) -> str:
        niche = self.primary_niche or "Unknown"
        return (
            f"Trader({self.platform}:{self.identifier[:10]}… "
            f"wr={self.win_rate:.0%} roi={self.roi:.0%} "
            f"trades={self.total_trades} niche={niche})"
        )

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "identifier": self.identifier,
            "display_name": self.display_name or self.identifier[:12],
            "win_rate": round(self.win_rate, 4),
            "roi": round(self.roi, 4),
            "total_trades": self.total_trades,
            "total_volume_usd": round(self.total_volume_usd, 2),
            "profit_loss_usd": round(self.profit_loss_usd, 2),
            "last_active": self.last_active.isoformat() if self.last_active else None,
            "primary_niche": self.primary_niche,
            "niche_scores": self.niche_scores,
            "trust_score": round(self.trust_score, 4),
        }
