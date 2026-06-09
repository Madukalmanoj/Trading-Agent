import sqlite3
from datetime import datetime, timezone
from typing import Optional

from loguru import logger
from rich.console import Console
from rich.table import Table

import config
from models.trader import Trader

console = Console()

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS recommendations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trader_id   TEXT    NOT NULL,
    platform    TEXT    NOT NULL,
    recommended_at TEXT NOT NULL,
    outcome     TEXT,           -- 'win' | 'loss' | 'pending'
    profit_loss REAL DEFAULT 0.0,
    old_trust   REAL DEFAULT 0.5,
    new_trust   REAL DEFAULT 0.5,
    updated_at  TEXT
)
"""

class LearningLoop:

    def __init__(self, db_path: str = config.SQLITE_DB_PATH) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(CREATE_TABLE_SQL)
            conn.commit()
        logger.debug(f"LearningLoop DB ready at {self.db_path}")

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def log_recommendation(self, trader: Trader) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO recommendations
                    (trader_id, platform, recommended_at, outcome, old_trust, new_trust)
                VALUES (?, ?, ?, 'pending', ?, ?)
                """,
                (trader.identifier, trader.platform, now, trader.trust_score, trader.trust_score),
            )
            conn.commit()
            row_id = cursor.lastrowid

        logger.info(f"Recommendation logged: trader={trader.identifier[:12]} id={row_id}")
        return row_id

    def record_outcome(
        self,
        recommendation_id: int,
        outcome: str,
        profit_loss: float,
        trader: Optional[Trader] = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()

        with self._conn() as conn:
            row = conn.execute(
                "SELECT old_trust FROM recommendations WHERE id = ?",
                (recommendation_id,),
            ).fetchone()

            if not row:
                logger.warning(f"Recommendation ID {recommendation_id} not found")
                return

            old_trust = row["old_trust"]
            new_trust = self._update_trust(old_trust, outcome, profit_loss)

            conn.execute(
                """
                UPDATE recommendations
                SET outcome = ?, profit_loss = ?, new_trust = ?, updated_at = ?
                WHERE id = ?
                """,
                (outcome, profit_loss, new_trust, now, recommendation_id),
            )
            conn.commit()

        logger.info(
            f"Trader score updated: id={recommendation_id} "
            f"outcome={outcome} pnl={profit_loss:+.2f} "
            f"trust: {old_trust:.3f} -> {new_trust:.3f}"
        )

        if trader:
            trader.trust_score = new_trust

    def update_all_pending(self, traders: list[Trader]) -> None:
        trader_map = {t.identifier: t for t in traders}

        with self._conn() as conn:
            pending = conn.execute(
                "SELECT id, trader_id FROM recommendations WHERE outcome = 'pending'"
            ).fetchall()

        for row in pending:
            trader = trader_map.get(row["trader_id"])
            if not trader:
                continue

            outcome = "win" if trader.win_rate >= config.MIN_WIN_RATE else "loss"
            estimated_pnl = trader.profit_loss_usd * 0.01

            self.record_outcome(row["id"], outcome, estimated_pnl, trader)

    def get_history(self, limit: int = 20) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM recommendations ORDER BY recommended_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def display_history(self) -> None:
        history = self.get_history(limit=20)

        if not history:
            console.print("[yellow]No recommendation history yet.[/yellow]")
            return

        table = Table(title="Learning Loop — Recommendation History", show_lines=True)
        table.add_column("ID", width=4)
        table.add_column("Trader", width=14)
        table.add_column("Platform", width=10)
        table.add_column("Recommended At", width=20)
        table.add_column("Outcome", width=8)
        table.add_column("P&L", justify="right", width=10)
        table.add_column("Trust Δ", justify="right", width=10)

        for rec in history:
            outcome_color = {"win": "green", "loss": "red", "pending": "yellow"}.get(
                rec["outcome"], "white"
            )
            trust_delta = rec["new_trust"] - rec["old_trust"]
            delta_str = f"{trust_delta:+.3f}"
            delta_color = "green" if trust_delta >= 0 else "red"

            table.add_row(
                str(rec["id"]),
                rec["trader_id"][:12] + "…",
                rec["platform"],
                rec["recommended_at"][:19],
                f"[{outcome_color}]{rec['outcome']}[/{outcome_color}]",
                f"${rec['profit_loss']:+.2f}",
                f"[{delta_color}]{delta_str}[/{delta_color}]",
            )

        console.print(table)

    @staticmethod
    def _update_trust(current: float, outcome: str, profit_loss: float) -> float:
        magnitude = min(abs(profit_loss) / 100.0, 0.1)

        if outcome == "win":
            new_trust = current + magnitude * (1.0 - current)
        else:
            new_trust = current - magnitude * current

        return round(max(0.1, min(0.99, new_trust)), 4)
