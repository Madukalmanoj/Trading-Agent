import os
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

import config
from models.trader import Trader
from models.market import Market

def _client(token: Optional[str] = None) -> httpx.Client:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    return httpx.Client(
        timeout=httpx.Timeout(connect=5.0, read=config.HTTP_TIMEOUT, write=5.0, pool=5.0),
        headers=headers,
        proxy=proxy if proxy else None,
    )

def _retry():
    return retry(
        stop=stop_after_attempt(config.HTTP_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )

def login_kalshi() -> Optional[str]:
    if not config.KALSHI_EMAIL or not config.KALSHI_PASSWORD:
        logger.info("Kalshi credentials not set — using public demo endpoints")
        return None

    url = f"{config.KALSHI_BASE_URL}/login"
    payload = {"email": config.KALSHI_EMAIL, "password": config.KALSHI_PASSWORD}

    try:
        with _client() as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json().get("token")
    except Exception as exc:
        logger.warning(f"Kalshi login failed (will use public endpoints): {exc}")
        return None

@_retry()
def fetch_markets(limit: int = 100, cursor: str = "") -> list[Market]:
    url = f"{config.KALSHI_DEMO_URL}/events"
    params: dict[str, Any] = {"limit": min(limit, 100)}
    if cursor:
        params["cursor"] = cursor

    markets: list[Market] = []

    with _client() as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    for event in data.get("events", []):
        try:
            category = event.get("category", "Other")
            event_ticker = event.get("event_ticker", "")
            title = event.get("title", event_ticker)

            closes_raw = event.get("expected_expiration_time") or event.get("expiration_time")
            closes_at = (
                datetime.fromisoformat(closes_raw.replace("Z", "+00:00"))
                if closes_raw
                else None
            )

            markets.append(
                Market(
                    platform="kalshi",
                    market_id=event_ticker,
                    title=title,
                    description=event.get("sub_title", ""),
                    category=category,
                    yes_price=0.5,
                    no_price=0.5,
                    volume_usd=0.0,
                    liquidity_usd=0.0,
                    closes_at=closes_at,
                )
            )
        except Exception as exc:
            logger.warning(f"Skipping malformed Kalshi event: {exc}")

    logger.info(f"Fetched {len(markets)} Kalshi events as markets")
    return markets

@_retry()
def fetch_market_history(ticker: str, limit: int = 100) -> list[dict[str, Any]]:
    url = f"{config.KALSHI_BASE_URL}/markets/{ticker}/trades"
    params = {"limit": limit}

    with _client() as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp.json().get("trades", [])

def aggregate_traders_from_trades(trades: list[dict[str, Any]]) -> dict[str, dict]:
    stats: dict[str, dict] = {}

    for trade in trades:
        member = trade.get("member_id") or trade.get("taker_member_id", "")
        if not member:
            continue

        if member not in stats:
            stats[member] = {"wins": 0, "losses": 0, "volume": 0.0, "pnl": 0.0, "markets": set()}

        count = int(trade.get("count", 1))
        price = float(trade.get("yes_price", 50)) / 100
        side = trade.get("taker_side", "yes")
        market_id = trade.get("market_id")
        if market_id:
            stats[member]["markets"].add(market_id)

        stats[member]["volume"] += count * price
        if side == "yes" and price < 0.5:
            stats[member]["wins"] += 1
        elif side == "no" and price > 0.5:
            stats[member]["wins"] += 1
        else:
            stats[member]["losses"] += 1

    return stats

def build_trader_from_stats(member_id: str, stats: dict[str, Any]) -> Trader:
    wins = stats.get("wins", 0)
    losses = stats.get("losses", 0)
    total = wins + losses
    win_rate = wins / total if total > 0 else 0.0
    volume = stats.get("volume", 0.0)
    pnl = stats.get("pnl", 0.0)
    roi = pnl / volume if volume > 0 else 0.0

    return Trader(
        platform="kalshi",
        identifier=member_id[:12],
        display_name=f"Kalshi:{member_id[:12]}",
        win_rate=win_rate,
        roi=roi,
        total_trades=total,
        total_volume_usd=volume,
        profit_loss_usd=pnl,
        last_active=datetime.now(timezone.utc),
        active_markets=list(stats.get("markets", [])),
    )

def fetch_trending_traders(limit: int = 15, timeframe: str = "daily") -> list[Trader]:
    # 1. Fetch recent active markets
    markets_limit = 50 if timeframe == "weekly" else 20
    trades_limit = 500 if timeframe == "weekly" else 200
    markets = fetch_markets(limit=markets_limit)
    all_trades = []
    
    # 2. Fetch history for each market to gather recent trades
    for m in markets[:(30 if timeframe=="weekly" else 10)]:
        try:
            trades = fetch_market_history(m.market_id, limit=trades_limit)
            for t in trades:
                t["market_id"] = m.market_id  # Inject market ID for linking
            all_trades.extend(trades)
        except Exception:
            pass

    # 3. Aggregate user performance across all recent trades
    stats = aggregate_traders_from_trades(all_trades)
    
    traders = []
    for member_id, user_stats in stats.items():
        if user_stats["volume"] < 10: # Filter out dust
            continue
        traders.append(build_trader_from_stats(member_id, user_stats))
        
    # 4. Sort by volume to find the daily trending traders
    traders.sort(key=lambda t: t.total_volume_usd, reverse=True)
    
    logger.info(f"Synthesised {len(traders)} REAL trending Kalshi traders from recent history")
    return traders[:limit]
