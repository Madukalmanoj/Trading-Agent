import json
from typing import Any

import httpx
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from tenacity import retry, stop_after_attempt, wait_exponential

import config
from memory.learning_loop import LearningLoop
from models.trader import Trader
from tools import rag_tools

console = Console()

HELP_TEXT = """
[bold]Available commands:[/bold]
  /list_traders          — Show all loaded traders
  /trader_detail <id>    — Show full stats for a trader (partial ID ok)
  /niche <topic>         — Filter traders by niche (e.g. /niche NBA)
  /recommend             — Get top copy-trade recommendation
  /quit                  — Exit chat
  [dim]Or just ask a question in plain English.[/dim]
"""

class ChatAgent:

    def __init__(self, traders: list[Trader], learning_loop: LearningLoop | None = None) -> None:
        self.traders = traders
        self.learning_loop = learning_loop
        self.history: list[dict[str, str]] = []
        self._system_prompt = (
            "You are Trading Agent, an expert prediction market analyst. "
            "You help users identify which traders to follow on Polymarket and Kalshi "
            "based on crowd wisdom and statistical performance. "
            "Be concise, data-driven, and always cite specific win rates and ROI figures. "
            "When recommending a trader, explain WHY based on their stats and niche expertise."
        )

    def start(self) -> None:
        console.print(Panel(HELP_TEXT, title="[bold green]Trading Agent Chat[/bold green]", expand=False))
        console.print(f"[dim]Loaded {len(self.traders)} traders | RAG docs: {rag_tools.collection_count()}[/dim]\n")

        while True:
            try:
                user_input = console.input("[bold green]You>[/bold green] ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[yellow]Exiting chat...[/yellow]")
                break

            if not user_input:
                continue

            if user_input.lower() in ("/quit", "/exit", "quit", "exit"):
                console.print("[yellow]Goodbye![/yellow]")
                break
            elif user_input.lower() == "/list_traders":
                self._cmd_list_traders()
            elif user_input.lower().startswith("/trader_detail"):
                parts = user_input.split(maxsplit=1)
                self._cmd_trader_detail(parts[1] if len(parts) > 1 else "")
            elif user_input.lower().startswith("/niche"):
                parts = user_input.split(maxsplit=1)
                self._cmd_niche(parts[1].strip() if len(parts) > 1 else "")
            elif user_input.lower() == "/recommend":
                self._cmd_recommend()
            else:
                self._chat(user_input)

    def _chat(self, user_message: str) -> None:
        rag_results = rag_tools.query(user_message, n_results=4)
        rag_context = "\n\n".join(
            f"[Source: {r['metadata'].get('source', 'unknown')}]\n{r['document']}"
            for r in rag_results
        )

        trader_summary = self._traders_as_json()

        augmented_message = (
            f"{user_message}\n\n"
            f"--- Trader Data ---\n{trader_summary}\n\n"
            f"--- Market Research Context ---\n{rag_context or 'No RAG context available.'}"
        )

        self.history.append({"role": "user", "content": augmented_message})

        try:
            response = self._call_llm(self.history)
            self.history.append({"role": "assistant", "content": response})
            console.print(f"\n[bold blue]Agent>[/bold blue] {response}\n")
        except Exception as exc:
            logger.error(f"LLM call failed: {exc}")
            console.print(f"[red]LLM error: {exc}[/red]")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8), reraise=True)
    def _call_llm(self, messages: list[dict[str, str]]) -> str:
        fallback_models = [
            config.LLM_MODEL,
            "liquid/lfm-2.5-1.2b-instruct:free",
            "liquid/lfm-2.5-1.2b-thinking:free",
        ]
        seen: set[str] = set()
        models_to_try = [m for m in fallback_models if not (m in seen or seen.add(m))]

        last_exc: Exception = RuntimeError("No models available")
        for model in models_to_try:
            try:
                payload = {
                    "model": model,
                    "messages": [{"role": "system", "content": self._system_prompt}] + messages,
                    "temperature": 0.7,
                    "max_tokens": 800,
                }
                with httpx.Client(timeout=30) as client:
                    resp = client.post(
                        f"{config.OPENROUTER_BASE_URL}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
                            "HTTP-Referer": "https://github.com/trading-agent",
                        },
                        json=payload,
                    )
                    if resp.status_code == 429:
                        logger.warning(f"Model {model} rate-limited, trying next...")
                        continue
                    resp.raise_for_status()
                    return resp.json()["choices"][0]["message"]["content"].strip()
            except Exception as exc:
                last_exc = exc
                logger.warning(f"Model {model} failed: {exc}, trying next...")
                continue

        raise last_exc

    def _build_system_prompt(self) -> str:
        return (
            "You are Trading Agent, an expert prediction market analyst. "
            "You help users identify which traders to follow on Polymarket and Kalshi "
            "based on crowd wisdom and statistical performance. "
            "Be concise, data-driven, and always cite specific win rates and ROI figures. "
            "When recommending a trader, explain WHY based on their stats and niche expertise."
        )

    def _traders_as_json(self) -> str:
        top = sorted(self.traders, key=lambda t: t.roi, reverse=True)[:10]
        return json.dumps([t.to_dict() for t in top], indent=2)

    def _cmd_list_traders(self) -> None:
        if not self.traders:
            console.print("[yellow]No traders loaded.[/yellow]")
            return

        table = Table(title="Discovered Traders", show_lines=True)
        table.add_column("Platform", style="cyan", width=12)
        table.add_column("ID", style="dim", width=14)
        table.add_column("Win Rate", justify="right")
        table.add_column("ROI", justify="right")
        table.add_column("Trades", justify="right")
        table.add_column("Niche", style="magenta")
        table.add_column("Trust", justify="right")

        for t in sorted(self.traders, key=lambda x: x.roi, reverse=True):
            wr_color = "green" if t.win_rate >= 0.6 else "yellow"
            table.add_row(
                t.platform,
                t.identifier[:12] + "…",
                f"[{wr_color}]{t.win_rate:.1%}[/{wr_color}]",
                f"{t.roi:+.1%}",
                str(t.total_trades),
                t.primary_niche or "—",
                f"{t.trust_score:.2f}",
            )

        console.print(table)

    def _cmd_trader_detail(self, partial_id: str) -> None:
        if not partial_id:
            console.print("[yellow]Usage: /trader_detail <partial_id>[/yellow]")
            return

        matches = [t for t in self.traders if partial_id.lower() in t.identifier.lower()]
        if not matches:
            console.print(f"[red]No trader found matching '{partial_id}'[/red]")
            return

        trader = matches[0]
        d = trader.to_dict()

        table = Table(title=f"Trader Detail — {trader.platform.upper()}", show_header=False, show_lines=True)
        table.add_column("Field", style="bold cyan", width=20)
        table.add_column("Value")

        for key, val in d.items():
            if key == "niche_scores":
                val = ", ".join(f"{k}: {v:.0%}" for k, v in sorted(val.items(), key=lambda x: -x[1]) if v > 0.05)
            table.add_row(key.replace("_", " ").title(), str(val))

        console.print(table)

    def _cmd_niche(self, niche: str) -> None:
        if not niche:
            console.print("[yellow]Usage: /niche <topic>  e.g. /niche NBA[/yellow]")
            return

        matches = [
            t for t in self.traders
            if t.primary_niche and niche.lower() in t.primary_niche.lower()
        ]

        if not matches:
            console.print(f"[yellow]No traders found for niche '{niche}'[/yellow]")
            return

        console.print(f"[bold]Traders specialising in '{niche}':[/bold]")
        for t in sorted(matches, key=lambda x: x.roi, reverse=True):
            score = t.niche_scores.get(t.primary_niche, 0)
            console.print(
                f"  • [cyan]{t.identifier[:14]}[/cyan] ({t.platform}) "
                f"wr={t.win_rate:.1%} roi={t.roi:+.1%} "
                f"niche_conf={score:.0%}"
            )

    def _cmd_recommend(self) -> None:
        if not self.traders:
            console.print("[yellow]No traders loaded.[/yellow]")
            return

        best = max(
            self.traders,
            key=lambda t: (t.trust_score * 0.3 + t.roi * 0.4 + t.win_rate * 0.3),
        )

        panel_text = Text()
        panel_text.append("🏆 Top Recommendation\n\n", style="bold yellow")
        panel_text.append(f"Platform:  {best.platform.upper()}\n")
        panel_text.append(f"Trader:    {best.identifier}\n")
        panel_text.append(f"Win Rate:  {best.win_rate:.1%}\n")
        panel_text.append(f"ROI:       {best.roi:+.1%}\n")
        panel_text.append(f"Trades:    {best.total_trades}\n")
        panel_text.append(f"Niche:     {best.primary_niche or 'Unknown'}\n")
        panel_text.append(f"Trust:     {best.trust_score:.2f}\n")

        console.print(Panel(panel_text, border_style="yellow"))

        if self.learning_loop:
            self.learning_loop.log_recommendation(best)
            logger.info(f"Recommendation logged for trader {best.identifier[:12]}")
