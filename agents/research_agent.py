from typing import Any

from loguru import logger
from rich.console import Console
from rich.progress import track

from models.market import Market
from tools import apify_tools, rag_tools

console = Console()

class ResearchAgent:

    def run(self, markets: list[Market] | None = None) -> int:
        logger.info("ResearchAgent starting RAG enrichment")
        console.print("[bold cyan]📚 Research Agent[/bold cyan] — enriching RAG database...")

        total_docs = 0

        total_docs += self._scrape_market_pages()

        if markets:
            top_markets = sorted(markets, key=lambda m: m.volume_usd, reverse=True)[:10]
            for market in track(top_markets, description="Researching markets..."):
                total_docs += self._enrich_market(market)

        logger.info(f"ResearchAgent stored {total_docs} total document chunks")
        console.print(
            f"[green]✓ RAG enrichment complete — {total_docs} chunks stored "
            f"(total in DB: {rag_tools.collection_count()})[/green]"
        )
        return total_docs

    def _scrape_market_pages(self) -> int:
        stored = 0

        poly_pages = apify_tools.scrape_polymarket_markets()
        for page in poly_pages:
            ids = rag_tools.ingest_scraped_page(
                page,
                extra_metadata={"platform": "polymarket", "content_type": "market_listing"},
            )
            stored += len(ids)

        kalshi_pages = apify_tools.scrape_kalshi_markets()
        for page in kalshi_pages:
            ids = rag_tools.ingest_scraped_page(
                page,
                extra_metadata={"platform": "kalshi", "content_type": "market_listing"},
            )
            stored += len(ids)

        logger.info(f"Market page scrape stored {stored} chunks")
        return stored

    def _enrich_market(self, market: Market) -> int:
        stored = 0
        articles = apify_tools.scrape_news_for_market(market.title, max_results=5)

        for article in articles:
            text = article.get("text", "")
            if not text or len(text) < 30:
                continue

            ids = rag_tools.ingest_scraped_page(
                article,
                extra_metadata={
                    "platform": market.platform,
                    "market_id": market.market_id,
                    "category": market.category,
                    "content_type": "news_article",
                },
            )
            stored += len(ids)
            market.rag_doc_ids.extend(ids)

        if stored:
            logger.debug(f"Market '{market.title[:40]}' enriched with {stored} chunks")

        return stored

    def ingest_text(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
        source_url: str = "manual",
    ) -> list[str]:
        page = {"text": text, "url": source_url, "title": metadata.get("title", "") if metadata else ""}
        return rag_tools.ingest_scraped_page(page, extra_metadata=metadata)
