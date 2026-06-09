import json
from typing import Any

import httpx
from loguru import logger
from rich.console import Console
from rich.progress import track
from tenacity import retry, stop_after_attempt, wait_exponential

import config
from models.trader import Trader

console = Console()

NICHES = ["NBA", "NFL", "Politics", "Crypto", "Weather", "Economics", "Entertainment", "Science", "Other"]

KEYWORD_MAP: dict[str, list[str]] = {
    "NBA": ["nba", "basketball", "lakers", "celtics", "warriors", "lebron", "curry"],
    "NFL": ["nfl", "football", "super bowl", "touchdown", "quarterback", "chiefs", "eagles"],
    "Politics": ["election", "president", "senate", "congress", "vote", "democrat", "republican", "biden", "trump"],
    "Crypto": ["bitcoin", "ethereum", "btc", "eth", "crypto", "defi", "solana", "token", "blockchain"],
    "Weather": ["hurricane", "temperature", "storm", "rainfall", "climate", "tornado", "flood"],
    "Economics": ["fed", "inflation", "gdp", "rate", "unemployment", "cpi", "recession", "interest rate"],
    "Entertainment": ["oscar", "grammy", "box office", "movie", "award", "celebrity", "netflix"],
    "Science": ["nasa", "space", "climate", "vaccine", "discovery", "research", "ai", "artificial intelligence"],
}

class NicheMapperAgent:

    def __init__(self) -> None:
        self.llm_model = config.LLM_MODEL
        self.api_key = config.OPENROUTER_API_KEY

    def run(self, traders: list[Trader]) -> list[Trader]:
        logger.info(f"NicheMapperAgent classifying {len(traders)} traders")
        console.print(f"[bold cyan]🗂  Niche Mapper[/bold cyan] — classifying {len(traders)} traders...")

        for trader in track(traders, description="Mapping niches..."):
            scores = self._keyword_classify(trader)

            top_score = max(scores.values()) if scores else 0.0
            if top_score < 0.4 and self.api_key:
                try:
                    llm_scores = self._llm_classify(trader)
                    for niche in NICHES:
                        scores[niche] = 0.4 * scores.get(niche, 0.0) + 0.6 * llm_scores.get(niche, 0.0)
                except Exception as exc:
                    logger.warning(f"LLM classification failed for {trader.identifier[:10]}: {exc}")

            total = sum(scores.values()) or 1.0
            trader.niche_scores = {k: round(v / total, 4) for k, v in scores.items()}
            trader.primary_niche = max(trader.niche_scores, key=trader.niche_scores.get)

        logger.info("NicheMapperAgent classification complete")
        console.print("[green]✓ Niche mapping complete[/green]")
        return traders

    def _keyword_classify(self, trader: Trader) -> dict[str, float]:
        scores: dict[str, float] = {n: 0.0 for n in NICHES}
        text = " ".join(trader.active_markets).lower()

        if not text:
            scores["Other"] = 1.0
            return scores

        for niche, keywords in KEYWORD_MAP.items():
            for kw in keywords:
                if kw in text:
                    scores[niche] += 1.0

        if all(v == 0.0 for v in scores.values()):
            scores["Other"] = 1.0

        return scores

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8), reraise=True)
    def _llm_classify(self, trader: Trader) -> dict[str, float]:
        markets_sample = trader.active_markets[:20]
        prompt = (
            f"You are a prediction market analyst. Given these market titles a trader has participated in:\n"
            f"{json.dumps(markets_sample)}\n\n"
            f"Classify this trader's activity into the following niches with a probability score (0.0-1.0) for each. "
            f"Scores must sum to 1.0. Return ONLY valid JSON like: "
            f'{{"NBA": 0.1, "NFL": 0.0, "Politics": 0.7, "Crypto": 0.1, "Weather": 0.0, '
            f'"Economics": 0.05, "Entertainment": 0.05, "Science": 0.0, "Other": 0.0}}'
        )

        fallback_models = [
            self.llm_model,
            "liquid/lfm-2.5-1.2b-instruct:free",
            "liquid/lfm-2.5-1.2b-thinking:free",
        ]
        seen: set[str] = set()
        models_to_try = [m for m in fallback_models if not (m in seen or seen.add(m))]

        with httpx.Client(timeout=30) as client:
            for model in models_to_try:
                resp = client.post(
                    f"{config.OPENROUTER_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "HTTP-Referer": "https://github.com/trading-agent",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1,
                        "max_tokens": 200,
                    },
                )
                if resp.status_code == 429:
                    logger.warning(f"Niche mapper: {model} rate-limited, trying next...")
                    continue
                resp.raise_for_status()
                break

        content = resp.json()["choices"][0]["message"]["content"].strip()
        start = content.find("{")
        end = content.rfind("}") + 1
        parsed: dict[str, Any] = json.loads(content[start:end])

        return {niche: float(parsed.get(niche, 0.0)) for niche in NICHES}
