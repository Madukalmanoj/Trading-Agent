# Trading Prediction Agent

> A multi-agent AI system that discovers consistent profitable traders on prediction markets, classifies them by niche, enriches a RAG knowledge base with live market research, and lets you chat with the data to make informed follow-trading decisions. Now upgraded to a **modern FastAPI + React-style single-page Web Application** deployable to Railway.

🚀 **Live Demo:** [https://trading-agent-prod.up.railway.app/](https://trading-agent-prod.up.railway.app/)

---

## What It Does

Trading (Trading Agent) runs a pipeline of 5 specialized AI agents:

1. **Polymarket Agent** — Pulls top traders from Manifold Markets leaderboard (public API), filters by win rate and ROI
2. **Kalshi Agent** — Discovers market specialists from Kalshi's event categories (Politics, Crypto, Weather, Economics)
3. **Niche Mapper** — Classifies each trader into a market niche using keyword matching + LLM fallback via OpenRouter
4. **Research Agent** — Scrapes Polymarket and Kalshi market pages via APIFY, chunks and embeds text into ChromaDB for RAG
5. **Chat Agent** — Multi-turn conversational interface backed by RAG + LLM to answer questions like *"Who's the best Politics trader?"*

A **closed learning loop** logs every recommendation to SQLite, tracks outcomes, and updates trader trust scores over time using a Bayesian update formula.

---

## Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                     Trading Prediction Agent                           │
│                                                                        │
│   ┌────────────────────────────────┐       ┌───────────────────────┐   │
│   │Browser (static/index.html)     │ ◄───► │app.py (FastAPI)       │   │
│   │SSE Log Streaming & UI          │       │REST & SSE Endpoints   │   │
│   └────────────────────────────────┘       └─────────┬─────────────┘   │
│                                                      │                 │
│   ┌──────────────────────────────────────────────────▼─────────────┐   │
│   │               web_orchestrator.py + log_capture.py             │   │
│   └────┬──────────┬──────────┬──────────┬──────────┬───────────────┘   │
│        │          │          │          │          │                   │
│   ┌────▼───┐ ┌───▼────┐ ┌───▼────┐ ┌───▼────┐ ┌───▼────────┐           │
│   │Poly-   │ │Kalshi  │ │Niche   │ │Research│ │Chat        │           │
│   │market  │ │Agent   │ │Mapper  │ │Agent   │ │Agent       │           │
│   │Agent   │ │        │ │        │ │        │ │            │           │
│   └────┬───┘ └───┬────┘ └───┬────┘ └───┬────┘ └───┬────────┘           │
│        │          │          │          │          │                   │
│   ┌────▼──────────▼──┐  ┌────▼──┐  ┌───▼────┐ ┌───▼────────┐           │
│   │  tools/           │  │OpenR- │  │ChromaDB│ │Learning    │           │
│   │  polymarket_tools │  │outer  │  │  RAG   │ │Loop        │           │
│   │  kalshi_tools     │  │  LLM  │  │        │ │ (SQLite)   │           │
│   │  apify_tools      │  └───────┘  └────────┘ └────────────┘           │
│   │  rag_tools        │                                                │
│   └───────────────────┘                                                │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
Trading-Prediction-Agent/
├── app.py                    # FastAPI entry point for the web app
├── web_orchestrator.py       # Web-friendly orchestrator wrapping existing agents
├── log_capture.py            # Context manager for SSE log streaming
├── static/                   # Frontend assets
│   └── index.html            # Premium dashboard UI (TailwindCSS + JS)
├── main.py                   # Legacy CLI entry point
├── config.py                 # All settings loaded from .env
├── agents/
│   ├── polymarket_agent.py   # Manifold Markets leaderboard discovery
│   ├── kalshi_agent.py       # Kalshi event-based trader synthesis
│   ├── niche_mapper.py       # Keyword + LLM niche classification
│   ├── research_agent.py     # APIFY scraping → ChromaDB ingestion
│   └── chat_agent.py         # RAG-backed conversational interface
├── tools/
│   ├── polymarket_tools.py   # Manifold Markets API client
│   ├── kalshi_tools.py       # Kalshi demo API client
│   ├── apify_tools.py        # APIFY scraping integration
│   └── rag_tools.py          # ChromaDB embed + query
├── memory/
│   └── learning_loop.py      # SQLite recommendation tracking + trust updates
├── models/
│   ├── trader.py             # Trader dataclass
│   └── market.py             # Market dataclass
├── Dockerfile                # Railway deployment config
├── railway.json              # Railway service definition
├── requirements.txt
└── .env.example
```

---

## Approach

### Agent Design

Each agent is a focused Python class with a single `run()` method. Agents communicate through shared data models (`Trader`, `Market`) rather than message passing, keeping the system simple and debuggable.

**Polymarket Agent** uses the [Manifold Markets](https://manifold.markets) public API as a live data source (Polymarket's own API is geo-restricted in some regions). It fetches the profit leaderboard, enriches the top 15 profiles with win rate and trade history, then filters by configurable thresholds.

**Kalshi Agent** uses Kalshi's demo API events endpoint which exposes real market categories (Politics, Crypto, Weather, Economics, etc.) without authentication. It synthesises one trader profile per event group, using price spread as a proxy for market resolution confidence.

**Niche Mapper** runs in two passes: fast keyword matching against market slugs/titles first, then an LLM call via OpenRouter only when keyword confidence is below 40%. This keeps API costs near zero for most traders.

**Research Agent** uses APIFY's Cheerio Scraper to pull market listing pages and news articles, chunks the text into 400-word overlapping segments, embeds them with `sentence-transformers/all-MiniLM-L6-v2`, and stores them in a local ChromaDB collection.

**Chat Agent** retrieves the 4 most relevant RAG chunks for each user message, injects them alongside the trader data into the LLM context, and maintains full conversation history for multi-turn dialogue.

### Learning Loop

Every `/recommend` command logs the recommendation to SQLite with a timestamp. On subsequent runs, the system estimates outcomes based on the trader's current win rate and updates trust scores using:

```
win  → new_trust = trust + magnitude × (1 - trust)
loss → new_trust = trust - magnitude × trust
```

where `magnitude = min(|pnl| / 100, 0.1)`. Trust scores feed back into the recommendation ranking formula (30% weight alongside ROI and win rate).

### Resilience

All API calls use `tenacity` for retry with exponential backoff. Both agents have fallback profiles that activate when APIs are unreachable, so the full pipeline always completes. The LLM call tries multiple free OpenRouter models in sequence if one is rate-limited.

---

## Setup

```bash
git clone https://github.com/Madukalmanoj/trading-agent.git
cd trading-agent
python -m venv .venv

# Windows
.venv\Scripts\activate
# Mac/Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your keys (see below), then run the web server:

```bash
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

Open your browser and navigate to `http://localhost:8000` to view the Dashboard!

### Deployment (Railway)
The project includes a `Dockerfile` and `railway.json`. You can easily deploy to Railway:
1. Connect your GitHub repository to Railway.
2. Add your Environment Variables.
3. Railway will automatically build and deploy the FastAPI server.

---

## Environment Variables

| Variable | Required | Where to get it |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes | [openrouter.ai](https://openrouter.ai) — free account |
| `APIFY_API_TOKEN` | Yes | [apify.com](https://apify.com) — free tier ($5 credit) |
| `KALSHI_EMAIL` | No | For authenticated Kalshi endpoints |
| `KALSHI_PASSWORD` | No | For authenticated Kalshi endpoints |
| `CHROMA_PERSIST_DIR` | No | Default: `./chroma_db` |
| `LLM_MODEL` | No | Default: `liquid/lfm-2.5-1.2b-instruct:free` |
| `LOG_LEVEL` | No | Default: `INFO` |

---

## Usage

The application now features a rich, responsive dashboard:

1. **Dashboard Tab**: Click buttons to run pipeline actions (e.g., "Full Pipeline", "Polymarket Search"). Logs from agents stream in real-time to the browser terminal.
2. **Chat Tab**: Interact with the AI agent to ask about loaded traders, RAG insights, and recommendations.
3. **Results Tab**: View all discovered traders in a structured table.
4. **Learning Loop Tab**: Review recommendation history and trust score evolutions.

*(You can still run the legacy CLI interface by executing `python main.py`.)*

### Chat Commands

```
/list_traders              — Table of all discovered traders
/trader_detail <id>        — Full stats card for one trader
/niche NBA                 — Filter traders by niche
/recommend                 — Best trader pick right now
/quit                      — Exit chat
```

Or ask in plain English:
```
You> Which traders are best for politics markets?
You> Who has the highest ROI on crypto?
You> Show me weather market specialists
```

---

## Example Output

```
🔍 Polymarket Agent — scanning leaderboard...
✓ Found 9 qualifying Polymarket traders

🔍 Kalshi Agent — scanning markets...
✓ Found 10 Kalshi market specialists

🗂  Niche Mapper — classifying 19 traders...
✓ Niche mapping complete

📚 Research Agent — enriching RAG database...
✓ RAG enrichment complete — 26 chunks stored

┏━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━┓
┃ Platform     ┃ Trader         ┃ Win Rate ┃    ROI ┃ Trades ┃ Niche     ┃
┡━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━┩
│ polymarket   │ SemioticRival… │    99.0% │+2644%  │     45 │ Politics  │
│ polymarket   │ Bayesian       │    99.0% │+1598%  │     38 │ Economics │
│ polymarket   │ chrisjbilling… │    99.0% │  +134% │     63 │ Politics  │
│ kalshi       │ Kalshi:Politic │    68.0% │  +31%  │     45 │ Politics  │
└──────────────┴────────────────┴──────────┴────────┴────────┴───────────┘
```

---

## Tech Stack

| Component | Technology |
|---|---|
| Agent orchestration | Custom Python classes |
| LLM | OpenRouter API (free models) |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` |
| Vector DB | ChromaDB (local persistent) |
| Scraping | APIFY Cheerio Scraper |
| Market data | Manifold Markets API + Kalshi Demo API |
| Terminal UI | Rich |
| Logging | Loguru |
| HTTP | httpx + tenacity (retry) |
| Learning loop | SQLite |

---

## Known Limitations

- Polymarket's `data-api` is geo-restricted in some regions — the agent falls back to Manifold Markets as an equivalent prediction market data source
- Kalshi does not expose per-user trade history on public endpoints — trader profiles are synthesised from market category and price data
- Free OpenRouter models have rate limits — the chat agent automatically tries fallback models
- ChromaDB is local only — for multi-user deployments, swap for a hosted vector DB
- Learning loop uses heuristic outcome estimation; wire to actual market resolution APIs for production use
