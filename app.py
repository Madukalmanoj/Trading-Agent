"""
Trading Agent — FastAPI Web Application.

Entry point:  uvicorn app:app --host 0.0.0.0 --port $PORT
"""

import asyncio
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from web_orchestrator import WebOrchestrator
from log_capture import LogCapture

# ── App setup ──

app = FastAPI(
    title="Trading Agent",
    description="Multi-agent prediction market analysis platform",
    version="1.0.0",
)

# Serve static files (the frontend)
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Singleton orchestrator
orchestrator = WebOrchestrator()

# Thread pool for running blocking agent code
executor = ThreadPoolExecutor(max_workers=3)

# ANSI escape code stripper
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\[/?[a-z ]+\]", re.IGNORECASE)


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes and rich markup tags."""
    return ANSI_RE.sub("", text)


# ── Health check ──

@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Serve frontend ──

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = STATIC_DIR / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"), status_code=200)


# ── Pipeline actions via SSE ──

ACTION_MAP = {
    "1": "run_full_pipeline",
    "8": "run_trending_pipeline",
    "9": "run_weekly_pipeline",
}

ACTION_LABELS = {
    "1": "Top Traders (All-Time)",
    "8": "Trending Traders (Daily)",
    "9": "Consistent Traders (Weekly)",
}


@app.get("/api/run/{action}")
async def run_action(action: str):
    """
    SSE endpoint that runs a pipeline action in a background thread
    and streams captured log output in real-time.
    """
    if action not in ACTION_MAP:
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid action '{action}'. Valid: {list(ACTION_MAP.keys())}"},
        )

    method_name = ACTION_MAP[action]
    label = ACTION_LABELS[action]

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        result = {}

        def _run():
            nonlocal result
            capture = LogCapture(queue, loop)
            with capture:
                method = getattr(orchestrator, method_name)
                result = method() or {}

        yield {"event": "status", "data": f"Starting: {label}..."}

        # Run in thread pool to avoid blocking
        future = loop.run_in_executor(executor, _run)

        # Stream logs from queue until None sentinel
        while True:
            try:
                line = await asyncio.wait_for(queue.get(), timeout=120)
            except asyncio.TimeoutError:
                yield {"event": "log", "data": "[timeout] Operation timed out after 120s"}
                break

            if line is None:
                break

            yield {"event": "log", "data": strip_ansi(str(line))}

        # Wait for the thread to finish
        await future

        # Send final result
        import json
        yield {"event": "result", "data": json.dumps(result)}
        yield {"event": "done", "data": label}

    return EventSourceResponse(event_generator())


# ── Chat endpoint ──

@app.post("/api/chat")
async def chat(request: Request):
    """Chat with the AI agent. Returns the LLM response."""
    body = await request.json()
    message = body.get("message", "").strip()

    if not message:
        return JSONResponse(status_code=400, content={"error": "Message is required"})

    loop = asyncio.get_event_loop()

    # Run chat in thread pool (it makes HTTP calls to LLM)
    reply = await loop.run_in_executor(executor, orchestrator.chat, message)

    return {"reply": reply}


# ── Data endpoints ──

@app.get("/api/traders")
async def get_traders():
    """Return all discovered traders as JSON."""
    return orchestrator.get_traders_json()


@app.get("/api/learning-loop")
async def get_learning_loop():
    """Return learning loop recommendation history."""
    return orchestrator.get_learning_loop_json()
