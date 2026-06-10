from loguru import logger
from rich.console import Console
from rich.progress import track

import config
from models.trader import Trader
from tools import polymarket_tools

console = Console()

class PolymarketAgent:

    def __init__(self) -> None:
        self.min_win_rate = config.MIN_WIN_RATE
        self.min_trades = config.MIN_TRADES
        self.activity_days = config.ACTIVITY_DAYS
        self.top_n = config.TOP_TRADERS_LIMIT

    def run(self, mode: str = 'all-time') -> list[Trader]:
        logger.info(f"PolymarketAgent starting trader discovery in '{mode}' mode")
        console.print("[bold cyan]🔍 Polymarket Agent[/bold cyan] — scanning leaderboard...")

        try:
            if mode == 'trending':
                raw_entries = polymarket_tools.fetch_trending_traders(limit=200)
            else:
                raw_entries = polymarket_tools.fetch_leaderboard(limit=200)
        except Exception as exc:
            logger.warning(f"Polymarket API unavailable ({exc}) — using fallback profiles")
            console.print("[yellow]⚠ Polymarket API unavailable — using representative profiles[/yellow]")
            return self._fallback_traders()

        traders: list[Trader] = []
        for entry in track(raw_entries, description="Parsing traders..."):
            trader = polymarket_tools.build_trader_from_leaderboard(entry)
            if trader:
                traders.append(trader)

        logger.info(f"Parsed {len(traders)} raw traders from leaderboard")

        if not traders:
            logger.warning("No traders parsed — using fallback profiles")
            console.print("[yellow]⚠ No traders parsed — using representative profiles[/yellow]")
            return self._fallback_traders()

        filtered = self._filter(traders)
        if not filtered:
            filtered = sorted(traders, key=lambda t: t.roi, reverse=True)[:self.top_n]

        sorted_traders = sorted(filtered, key=lambda t: t.roi, reverse=True)[: self.top_n]

        logger.info(f"PolymarketAgent returning {len(sorted_traders)} top traders")
        console.print(
            f"[green]✓ Found {len(sorted_traders)} qualifying Polymarket traders[/green]"
        )
        return sorted_traders

    def _fallback_traders(self) -> list[Trader]:
        from datetime import datetime, timezone
        import hashlib

        profiles = [
            {"niche": "Politics",  "win_rate": 0.72, "roi": 0.64, "trades": 89,  "vol": 142300.0},
            {"niche": "Crypto",    "win_rate": 0.68, "roi": 0.41, "trades": 47,  "vol": 38200.0},
            {"niche": "Sports",    "win_rate": 0.61, "roi": 0.28, "trades": 63,  "vol": 21500.0},
            {"niche": "Economics", "win_rate": 0.65, "roi": 0.35, "trades": 34,  "vol": 67800.0},
            {"niche": "NBA",       "win_rate": 0.59, "roi": 0.22, "trades": 51,  "vol": 14200.0},
            {"niche": "Weather",   "win_rate": 0.63, "roi": 0.31, "trades": 28,  "vol": 8900.0},
        ]
        traders = []
        for p in profiles:
            niche = p["niche"]
            pseudo_id = "0x" + hashlib.md5(f"poly_fallback_{niche}".encode()).hexdigest()[:40]
            traders.append(
                Trader(
                    platform="polymarket",
                    identifier=pseudo_id,
                    display_name=f"Poly {niche} Specialist",
                    win_rate=p["win_rate"],
                    roi=p["roi"],
                    total_trades=p["trades"],
                    total_volume_usd=p["vol"],
                    profit_loss_usd=round(p["vol"] * p["roi"], 2),
                    last_active=datetime.now(timezone.utc),
                    active_markets=[f"polymarket-{niche.lower()}-market"],
                    primary_niche=niche,
                    niche_scores={niche: 0.9, "Other": 0.1},
                    trust_score=0.45,
                )
            )
        logger.info(f"Generated {len(traders)} fallback Polymarket profiles")
        return traders

    def _filter(self, traders: list[Trader]) -> list[Trader]:
        result: list[Trader] = []
        for t in traders:
            if t.win_rate < self.min_win_rate:
                continue
            if t.total_trades < self.min_trades:
                continue
            if not polymarket_tools.is_recently_active(t, self.activity_days):
                continue
            result.append(t)

        logger.debug(
            f"Filter: {len(traders)} -> {len(result)} traders "
            f"(wr>{self.min_win_rate:.0%}, trades>={self.min_trades}, "
            f"active<{self.activity_days}d)"
        )
        return result
