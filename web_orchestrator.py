"""
Web-friendly orchestrator wrapping the existing agents.

Holds the same state as the CLI Orchestrator but exposes methods
suitable for calling from async FastAPI endpoints. Does not handle
I/O directly — logging is intercepted by log_capture.LogCapture.
"""

from loguru import logger

from agents.polymarket_agent import PolymarketAgent
from agents.kalshi_agent import KalshiAgent
from agents.niche_mapper import NicheMapperAgent
from agents.research_agent import ResearchAgent
from agents.chat_agent import ChatAgent
from memory.learning_loop import LearningLoop
from models.trader import Trader


class WebOrchestrator:
    """Singleton orchestrator for the web application."""

    def __init__(self) -> None:
        self.traders: list[Trader] = []
        self.learning_loop = LearningLoop()
        self.poly_agent = PolymarketAgent()
        self.kalshi_agent = KalshiAgent()
        self.niche_agent = NicheMapperAgent()
        self.research_agent = ResearchAgent()
        self._chat_agent: ChatAgent | None = None

    # ── Pipeline actions (matching CLI menu options 1-7) ──

    def run_full_pipeline(self) -> dict:
        """Option 1: Run full pipeline (all agents sequentially)."""
        logger.info("Starting full pipeline")

        poly_traders = self.poly_agent.run()
        kalshi_traders = self.kalshi_agent.run()
        self.traders = poly_traders + kalshi_traders
        logger.info(f"Total traders discovered: {len(self.traders)}")

        if not self.traders:
            return {"status": "warning", "message": "No traders discovered — check API connectivity.", "traders": 0}

        self.traders = self.niche_agent.run(self.traders)
        self.research_agent.run(markets=[])
        self.learning_loop.update_all_pending(self.traders)

        return {
            "status": "success",
            "message": f"Full pipeline complete. {len(self.traders)} traders discovered.",
            "traders": len(self.traders),
        }

    def run_polymarket_only(self) -> dict:
        """Option 2: Search Polymarket traders only."""
        poly_traders = self.poly_agent.run()
        self.traders = [t for t in self.traders if t.platform != "polymarket"] + poly_traders
        return {
            "status": "success",
            "message": f"Polymarket: {len(poly_traders)} traders loaded",
            "traders": len(poly_traders),
        }

    def run_kalshi_only(self) -> dict:
        """Option 3: Search Kalshi traders only."""
        kalshi_traders = self.kalshi_agent.run()
        self.traders = [t for t in self.traders if t.platform != "kalshi"] + kalshi_traders
        return {
            "status": "success",
            "message": f"Kalshi: {len(kalshi_traders)} traders loaded",
            "traders": len(kalshi_traders),
        }

    def run_niche_mapping(self) -> dict:
        """Option 4: Map niches for discovered traders."""
        if not self.traders:
            return {"status": "warning", "message": "No traders loaded. Run option 1, 2, or 3 first."}
        self.traders = self.niche_agent.run(self.traders)
        return {
            "status": "success",
            "message": f"Niche mapping complete for {len(self.traders)} traders.",
        }

    def run_research(self) -> dict:
        """Option 5: Research & enrich RAG for top markets."""
        total_docs = self.research_agent.run(markets=[])
        return {
            "status": "success",
            "message": f"RAG enrichment complete — {total_docs} chunks stored.",
        }

    def view_learning_loop(self) -> dict:
        """Option 7: View learning loop feedback."""
        if not self.traders:
            logger.info("Loading traders for learning loop context...")
            self.traders = self.poly_agent.run() + self.kalshi_agent.run()

        history = self.learning_loop.get_history(limit=1)
        if not history and self.traders:
            logger.info("No history yet — seeding with top 5 traders...")
            for trader in sorted(self.traders, key=lambda t: t.roi, reverse=True)[:5]:
                self.learning_loop.log_recommendation(trader)
            self.learning_loop.update_all_pending(self.traders)

        self.learning_loop.display_history()
        return {
            "status": "success",
            "message": "Learning loop displayed.",
        }

    # ── Chat ──

    def chat(self, user_message: str) -> str:
        """Option 6: Chat with data. Returns the LLM response text."""
        if self._chat_agent is None:
            self._chat_agent = ChatAgent(traders=self.traders, learning_loop=self.learning_loop)

        # Use the internal _chat logic but capture the response
        from tools import rag_tools
        import json

        rag_results = rag_tools.query(user_message, n_results=4)
        rag_context = "\n\n".join(
            f"[Source: {r['metadata'].get('source', 'unknown')}]\n{r['document']}"
            for r in rag_results
        )

        trader_summary = json.dumps(
            [t.to_dict() for t in sorted(self.traders, key=lambda t: t.roi, reverse=True)[:10]],
            indent=2,
        )

        augmented_message = (
            f"{user_message}\n\n"
            f"--- Trader Data ---\n{trader_summary}\n\n"
            f"--- Market Research Context ---\n{rag_context or 'No RAG context available.'}"
        )

        self._chat_agent.history.append({"role": "user", "content": augmented_message})

        try:
            response = self._chat_agent._call_llm(self._chat_agent.history)
            self._chat_agent.history.append({"role": "assistant", "content": response})
            return response
        except Exception as exc:
            logger.error(f"LLM call failed: {exc}")
            return f"Error: {exc}"

    # ── Data access ──

    def get_traders_json(self) -> list[dict]:
        """Return all traders as JSON-serializable dicts."""
        return [t.to_dict() for t in sorted(self.traders, key=lambda t: t.roi, reverse=True)]

    def get_learning_loop_json(self) -> list[dict]:
        """Return learning loop history as JSON-serializable dicts."""
        return self.learning_loop.get_history(limit=50)
