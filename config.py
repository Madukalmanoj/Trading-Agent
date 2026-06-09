import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
LLM_MODEL: str = os.getenv("LLM_MODEL", "liquid/lfm-2.5-1.2b-instruct:free")

APIFY_API_TOKEN: str = os.getenv("APIFY_API_TOKEN", "")

KALSHI_EMAIL: str = os.getenv("KALSHI_EMAIL", "")
KALSHI_PASSWORD: str = os.getenv("KALSHI_PASSWORD", "")
KALSHI_BASE_URL: str = "https://api.elections.kalshi.com/trade-api/v2"
KALSHI_DEMO_URL: str = "https://demo-api.kalshi.co/trade-api/v2"

POLYMARKET_API_KEY: str = os.getenv("POLYMARKET_API_KEY", "")
POLYMARKET_DATA_API: str = "https://data-api.polymarket.com"
POLYMARKET_CLOB_API: str = "https://clob.polymarket.com"
POLYMARKET_GAMMA_API: str = "https://gamma-api.polymarket.com"

CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
CHROMA_COLLECTION_NAME: str = "market_research"
EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR: Path = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

SQLITE_DB_PATH: str = "./trading_learning.db"

MIN_TRADES: int = 1
MIN_WIN_RATE: float = 0.55
TOP_TRADERS_LIMIT: int = 10
ACTIVITY_DAYS: int = 30
HTTP_TIMEOUT: int = 8
HTTP_RETRIES: int = 1
