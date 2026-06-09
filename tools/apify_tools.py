from typing import Any, Optional

from apify_client import ApifyClient
from loguru import logger

import config

def _client() -> ApifyClient:
    return ApifyClient(config.APIFY_API_TOKEN)

def scrape_urls(urls: list[str], max_pages: int = 10) -> list[dict[str, Any]]:
    if not config.APIFY_API_TOKEN:
        logger.warning("APIFY_API_TOKEN not set — skipping scrape")
        return []

    client = _client()
    run_input = {
        "startUrls": [{"url": u} for u in urls],
        "maxPagesPerCrawl": max_pages,
        "pageFunction": """
            async function pageFunction(context) {
                const { $, request } = context;
                return {
                    url: request.url,
                    title: $('title').text().trim(),
                    text: $('body').text().replace(/\\s+/g, ' ').trim().slice(0, 5000),
                };
            }
        """,
    }

    try:
        logger.info(f"Starting APIFY cheerio-scraper for {len(urls)} URL(s)")
        run = client.actor("apify/cheerio-scraper").call(run_input=run_input)
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        logger.info(f"APIFY returned {len(items)} scraped pages")
        return items
    except Exception as exc:
        logger.error(f"APIFY scrape failed: {exc}")
        return []

def scrape_polymarket_markets() -> list[dict[str, Any]]:
    urls = [
        "https://polymarket.com/markets",
        "https://polymarket.com/markets?category=politics",
        "https://polymarket.com/markets?category=sports",
        "https://polymarket.com/markets?category=crypto",
    ]
    return scrape_urls(urls, max_pages=3)

def scrape_kalshi_markets() -> list[dict[str, Any]]:
    urls = [
        "https://kalshi.com/markets",
        "https://kalshi.com/markets#politics",
        "https://kalshi.com/markets#sports",
    ]
    return scrape_urls(urls, max_pages=3)

def scrape_news_for_market(market_title: str, max_results: int = 5) -> list[dict[str, Any]]:
    if not config.APIFY_API_TOKEN:
        logger.warning("APIFY_API_TOKEN not set — skipping news scrape")
        return []

    client = _client()
    run_input = {
        "queries": [market_title],
        "maxPagesPerQuery": 1,
        "resultsPerPage": max_results,
        "mobileResults": False,
        "languageCode": "en",
        "countryCode": "us",
        "saveHtml": False,
        "saveHtmlToKeyValueStore": False,
    }

    try:
        logger.info(f"Searching news for: '{market_title[:60]}'")
        run = client.actor("apify/google-search-scraper").call(run_input=run_input)
        raw = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        articles: list[dict] = []
        for page in raw:
            for result in page.get("organicResults", []):
                articles.append({
                    "url": result.get("url", ""),
                    "title": result.get("title", ""),
                    "text": result.get("description", ""),
                })
        return articles[:max_results]
    except Exception as exc:
        logger.error(f"APIFY news search failed: {exc}")
        return []

def fallback_scrape(url: str) -> Optional[str]:
    import requests
    from bs4 import BeautifulSoup

    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; TradingBot/1.0)"}
        resp = requests.get(url, headers=headers, timeout=config.HTTP_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        return soup.get_text(separator=" ", strip=True)[:5000]
    except Exception as exc:
        logger.warning(f"Fallback scrape failed for {url}: {exc}")
        return None
