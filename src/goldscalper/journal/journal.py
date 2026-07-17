"""Structured trade journal (SQLite).

Two tables:
- `decisions`: every proposal the risk engine saw, approved or not, with
  the full gate reasons. This is the audit trail proving the gate works.
- `trades`: every executed trade with the features the EOD analysis needs
  (setup, session, spread at entry, ATR, MFE/MAE, outcome, rationale).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from goldscalper.models import TradeProposal
from goldscalper.risk.engine import RiskDecision

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    source TEXT NOT NULL,
    setup_type TEXT,
    direction TEXT NOT NULL,
    entry REAL NOT NULL,
    stop_loss REAL NOT NULL,
    take_profit REAL NOT NULL,
    requested_risk_pct REAL,
    confidence REAL,
    rationale TEXT,
    approved INTEGER NOT NULL,
    lot REAL NOT NULL,
    risk_amount REAL NOT NULL,
    reject_reasons TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket INTEGER,
    setup_type TEXT,
    session TEXT,
    direction TEXT NOT NULL,
    lot REAL NOT NULL,
    entry_time TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_time TEXT,
    exit_price REAL,
    stop_loss REAL,
    take_profit REAL,
    spread_at_entry REAL,
    atr_at_entry REAL,
    mfe REAL,
    mae REAL,
    pnl REAL,
    outcome TEXT,
    rationale TEXT
);
"""


class Journal:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------- decisions

    def log_decision(
        self, ts: datetime, proposal: TradeProposal, decision: RiskDecision
    ) -> int:
        cur = self._conn.execute(
            """INSERT INTO decisions
               (ts, source, setup_type, direction, entry, stop_loss, take_profit,
                requested_risk_pct, confidence, rationale, approved, lot,
                risk_amount, reject_reasons)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ts.isoformat(),
                proposal.source.value,
                proposal.setup_type,
                proposal.direction.value,
                proposal.entry,
                proposal.stop_loss,
                proposal.take_profit,
                proposal.requested_risk_pct,
                proposal.confidence,
                proposal.rationale,
                int(decision.approved),
                decision.lot,
                decision.risk_amount,
                json.dumps(list(decision.reasons)),
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    # ---------------------------------------------------------------- trades

    def open_trade(
        self,
        ticket: int,
        direction: str,
        lot: float,
        entry_time: datetime,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        setup_type: str = "",
        session: str = "",
        spread_at_entry: float | None = None,
        atr_at_entry: float | None = None,
        rationale: str = "",
    ) -> int:
        cur = self._conn.execute(
            """INSERT INTO trades
               (ticket, setup_type, session, direction, lot, entry_time,
                entry_price, stop_loss, take_profit, spread_at_entry,
                atr_at_entry, rationale)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ticket,
                setup_type,
                session,
                direction,
                lot,
                entry_time.isoformat(),
                entry_price,
                stop_loss,
                take_profit,
                spread_at_entry,
                atr_at_entry,
                rationale,
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def close_trade(
        self,
        ticket: int,
        exit_time: datetime,
        exit_price: float,
        pnl: float,
        outcome: str,
        mfe: float | None = None,
        mae: float | None = None,
    ) -> None:
        self._conn.execute(
            """UPDATE trades
               SET exit_time = ?, exit_price = ?, pnl = ?, outcome = ?,
                   mfe = ?, mae = ?
               WHERE ticket = ? AND exit_time IS NULL""",
            (exit_time.isoformat(), exit_price, pnl, outcome, mfe, mae, ticket),
        )
        self._conn.commit()

    # ----------------------------------------------------------------- reads

    def decisions(self) -> list[sqlite3.Row]:
        return list(self._conn.execute("SELECT * FROM decisions ORDER BY id"))

    def trades(self) -> list[sqlite3.Row]:
        return list(self._conn.execute("SELECT * FROM trades ORDER BY id"))

    def daily_stats(self, date_iso: str) -> dict:
        row = self._conn.execute(
            """SELECT COUNT(*) AS n,
                      COALESCE(SUM(pnl), 0.0) AS pnl,
                      SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins
               FROM trades
               WHERE exit_time IS NOT NULL AND substr(exit_time, 1, 10) = ?""",
            (date_iso,),
        ).fetchone()
        return {"trades": row["n"], "pnl": row["pnl"], "wins": row["wins"] or 0}
