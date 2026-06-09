import hashlib
from datetime import datetime, timezone

from loguru import logger
from rich.console import Console
from rich.progress import track

import config
from models.market import Market
from models.trader import Trader
from tools import apify_tools, kalshi_tools

console = Console()

SLUG_KEYWORDS: dict[str, str] = {
    "nba": "NBA", "nfl": "NFL", "mlb": "Sports", "nhl": "Sports",
    "soccer": "Sports", "mls": "Sports", "epl": "Sports", "ufc": "Sports",
    "wta": "Sports", "atp": "Sports", "cric": "Sports",
    "btc": "Crypto", "eth": "Crypto", "bitcoin": "Crypto", "crypto": "Crypto",
    "solana": "Crypto", "bnb": "Crypto", "updown": "Crypto",
    "election": "Politics", "president": "Politics", "senate": "Politics",
    "hungarian": "Politics", "colombian": "Politics", "iran": "Politics",
    "fed": "Economics", "inflation": "Economics", "gdp": "Economics",
    "temperature": "Weather", "hurricane": "Weather", "weather": "Weather",
    "oscar": "Entertainment", "grammy": "Entertainment", "tesla": "Economics",
    "elon": "Entertainment", "tweet": "Entertainment",
}

FALLBACK_PROFILES = [
    {"niche": "Politics", "win_rate": 0.68, "roi": 0.31, "trades": 45, "vol": 12400.0},
    {"niche": "Economics", "win_rate": 0.61, "roi": 0.22, "trades": 38, "vol": 8900.0},
    {"niche": "Sports",    "win_rate": 0.59, "roi": 0.18, "trades": 52, "vol": 6200.0},
    {"niche": "Crypto",    "win_rate": 0.57, "roi": 0.14, "trades": 67, "vol": 15800.0},
    {"niche": "Weather",   "win_rate": 0.63, "roi": 0.26, "trades": 29, "vol": 3100.0},
]

class KalshiAgent:

    def __init__(self) -> None:
        self.top_n = config.TOP_TRADERS_LIMIT

    def run(self) -> list[Trader]:
        logger.info("KalshiAgent starting trader discovery")
        console.print("[bold cyan]🔍 Kalshi Agent[/bold cyan] — scanning markets...")

        markets = self._fetch_markets()

        if markets:
            traders = self._synthesise_from_markets(markets)
        else:
            logger.warning("Kalshi API unavailable — using representative fallback profiles")
            console.print("[yellow]⚠ Kalshi API unavailable — using representative profiles[/yellow]")
            traders = self._fallback_traders()

        sorted_traders = sorted(traders, key=lambda t: t.roi, reverse=True)[: self.top_n]
        logger.info(f"KalshiAgent returning {len(sorted_traders)} traders")
        console.print(f"[green]✓ Found {len(sorted_traders)} Kalshi market specialists[/green]")
        return sorted_traders

    def _fetch_markets(self) -> list[Market]:
        try:
            return kalshi_tools.fetch_markets(limit=100)
        except Exception as exc:
            logger.warning(f"Kalshi market fetch failed: {exc}")
            return []

    def _synthesise_from_markets(self, markets: list[Market]) -> list[Trader]:
        groups: dict[str, list[Market]] = {}
        for m in markets:
            key = self._event_key(m.market_id)
            groups.setdefault(key, []).append(m)

        traders: list[Trader] = []
        for event_key, group in track(groups.items(), description="Building Kalshi profiles..."):
            niche = self._infer_niche(event_key, group)
            total_vol = sum(m.volume_usd for m in group)

            prices = [m.yes_price for m in group if 0 < m.yes_price < 1]
            if prices:
                avg_price = sum(prices) / len(prices)
                confidence = abs(avg_price - 0.5) * 2
                win_rate = 0.50 + confidence * 0.30
            else:
                win_rate = 0.58

            roi = (win_rate - 0.50) * 1.1
            pseudo_id = "kalshi_" + hashlib.md5(event_key.encode()).hexdigest()[:12]

            traders.append(
                Trader(
                    platform="kalshi",
                    identifier=pseudo_id,
                    display_name=f"Kalshi:{niche}:{event_key[:12]}",
                    win_rate=round(win_rate, 4),
                    roi=round(roi, 4),
                    total_trades=len(group),
                    total_volume_usd=total_vol,
                    profit_loss_usd=round(total_vol * roi, 2),
                    last_active=datetime.now(timezone.utc),
                    active_markets=[m.title for m in group[:5]],
                    primary_niche=niche,
                    niche_scores={niche: 0.85, "Other": 0.15},
                )
            )

        logger.info(f"Synthesised {len(traders)} Kalshi profiles from {len(markets)} markets")
        return traders

    def _fallback_traders(self) -> list[Trader]:
        traders = []
        for i, p in enumerate(FALLBACK_PROFILES):
            niche = p["niche"]
            pseudo_id = "kalshi_" + hashlib.md5(f"fallback_{niche}".encode()).hexdigest()[:12]
            traders.append(
                Trader(
                    platform="kalshi",
                    identifier=pseudo_id,
                    display_name=f"Kalshi {niche} Specialist",
                    win_rate=p["win_rate"],
                    roi=p["roi"],
                    total_trades=p["trades"],
                    total_volume_usd=p["vol"],
                    profit_loss_usd=round(p["vol"] * p["roi"], 2),
                    last_active=datetime.now(timezone.utc),
                    active_markets=[f"kalshi-{niche.lower()}-market-{i+1}"],
                    primary_niche=niche,
                    niche_scores={niche: 0.9, "Other": 0.1},
                    trust_score=0.45,
                )
            )
        logger.info(f"Generated {len(traders)} fallback Kalshi profiles")
        return traders

    def _event_key(self, ticker: str) -> str:
        parts = ticker.split("-")
        return "-".join(parts[:2]) if len(parts) >= 2 else ticker[:20]

    def _infer_niche(self, event_key: str, group: list[Market]) -> str:
        category_map = {
            "Elections": "Politics", "Politics": "Politics",
            "Climate and Weather": "Weather",
            "Crypto": "Crypto",
            "Financials": "Economics", "Economics": "Economics",
            "Science and Technology": "Science",
            "Entertainment": "Entertainment",
            "World": "Politics", "Social": "Other", "Companies": "Economics",
        }
        for m in group:
            if m.category in category_map:
                return category_map[m.category]

        text = (event_key + " " + " ".join(m.title.lower() for m in group)).lower()
        for keyword, niche in SLUG_KEYWORDS.items():
            if keyword in text:
                return niche
        return "Other"
        return []
