import sys
from datetime import datetime

from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

import config
from agents.chat_agent import ChatAgent
from agents.kalshi_agent import KalshiAgent
from agents.niche_mapper import NicheMapperAgent
from agents.polymarket_agent import PolymarketAgent
from agents.research_agent import ResearchAgent
from memory.learning_loop import LearningLoop
from models.trader import Trader

log_file = config.LOG_DIR / f"trading_agent_{datetime.now().strftime('%Y%m%d')}.log"
logger.remove()
logger.add(sys.stderr, level=config.LOG_LEVEL, colorize=True, format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}")
logger.add(str(log_file), level="DEBUG", rotation="10 MB", retention="7 days")

console = Console()

BANNER = """
[bold cyan]
  ██████╗██╗    ██╗████████╗
 ██╔════╝██║    ██║╚══██╔══╝
 ██║     ██║ █╗ ██║   ██║   
 ██║     ██║███╗██║   ██║   
 ╚██████╗╚███╔███╔╝   ██║   
  ╚═════╝ ╚══╝╚══╝    ╚═╝   
[/bold cyan]
[bold white]Trading Agent Prediction Agent[/bold white]
[dim]Polymarket · Kalshi · Multi-Agent Research System[/dim]
"""

MENU = """
[bold]Select an option:[/bold]

  [cyan][1][/cyan] Run full pipeline (all agents sequentially)
  [cyan][2][/cyan] Search Polymarket traders only
  [cyan][3][/cyan] Search Kalshi traders only
  [cyan][4][/cyan] Map niches for discovered traders
  [cyan][5][/cyan] Research & enrich RAG for top markets
  [cyan][6][/cyan] Chat with data (interactive)
  [cyan][7][/cyan] View learning loop feedback
  [cyan][0][/cyan] Exit
"""

class Orchestrator:

    def __init__(self) -> None:
        self.traders: list[Trader] = []
        self.learning_loop = LearningLoop()
        self.poly_agent = PolymarketAgent()
        self.kalshi_agent = KalshiAgent()
        self.niche_agent = NicheMapperAgent()
        self.research_agent = ResearchAgent()

    def run_full_pipeline(self) -> None:
        console.print(Panel("[bold]Running full pipeline...[/bold]", style="cyan"))

        poly_traders = self.poly_agent.run()
        kalshi_traders = self.kalshi_agent.run()
        self.traders = poly_traders + kalshi_traders
        logger.info(f"Total traders discovered: {len(self.traders)}")

        if not self.traders:
            console.print("[yellow]No traders discovered — check API connectivity.[/yellow]")
            return

        self.traders = self.niche_agent.run(self.traders)

        self.research_agent.run(markets=[])

        self.learning_loop.update_all_pending(self.traders)

        self._start_chat()

    def run_polymarket_only(self) -> None:
        poly_traders = self.poly_agent.run()
        self.traders = [t for t in self.traders if t.platform != "polymarket"] + poly_traders
        console.print(f"[green]Polymarket: {len(poly_traders)} traders loaded[/green]")

    def run_kalshi_only(self) -> None:
        kalshi_traders = self.kalshi_agent.run()
        self.traders = [t for t in self.traders if t.platform != "kalshi"] + kalshi_traders
        console.print(f"[green]Kalshi: {len(kalshi_traders)} traders loaded[/green]")

    def run_niche_mapping(self) -> None:
        if not self.traders:
            console.print("[yellow]No traders loaded. Run option 1, 2, or 3 first.[/yellow]")
            return
        self.traders = self.niche_agent.run(self.traders)

    def run_research(self) -> None:
        self.research_agent.run(markets=[])

    def _start_chat(self) -> None:
        if not self.traders:
            console.print("[yellow]No traders loaded. Run discovery first.[/yellow]")
        chat = ChatAgent(traders=self.traders, learning_loop=self.learning_loop)
        chat.start()

    def view_learning_loop(self) -> None:
        if not self.traders:
            console.print("[dim]Loading traders for learning loop context...[/dim]")
            from agents.polymarket_agent import PolymarketAgent
            from agents.kalshi_agent import KalshiAgent
            self.traders = PolymarketAgent().run() + KalshiAgent().run()

        history = self.learning_loop.get_history(limit=1)
        if not history and self.traders:
            console.print("[dim]No history yet — seeding with top 5 traders...[/dim]")
            for trader in sorted(self.traders, key=lambda t: t.roi, reverse=True)[:5]:
                self.learning_loop.log_recommendation(trader)
            self.learning_loop.update_all_pending(self.traders)

        self.learning_loop.display_history()

def main() -> None:
    console.print(BANNER)

    orch = Orchestrator()

    while True:
        console.print(Panel(MENU, title="[bold green]Trading Agent Menu[/bold green]", expand=False))
        choice = Prompt.ask("[bold]Enter choice[/bold]", choices=["0", "1", "2", "3", "4", "5", "6", "7"], default="0")

        if choice == "0":
            console.print("[yellow]Goodbye![/yellow]")
            break
        elif choice == "1":
            orch.run_full_pipeline()
        elif choice == "2":
            orch.run_polymarket_only()
        elif choice == "3":
            orch.run_kalshi_only()
        elif choice == "4":
            orch.run_niche_mapping()
        elif choice == "5":
            orch.run_research()
        elif choice == "6":
            orch._start_chat()
        elif choice == "7":
            orch.view_learning_loop()

if __name__ == "__main__":
    main()
