"""The deterministic risk gate.

Every trade proposal — from rules, an LLM, or a human — passes through
`RiskEngine.evaluate()`. The engine either returns an approved decision
with a lot size it computed itself, or a rejection listing every gate
that failed. Nothing outside this module sizes positions or overrides a
rejection.

The engine is deliberately stateful about *session* facts (daily loss
halt, kill-switch latch) and those latches only clear by the rules coded
here (new day) or by an explicit human `manual_reset()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from goldscalper.config import RiskConfig
from goldscalper.models import AccountState, MarketState, SymbolSpec, TradeProposal
from goldscalper.risk.news import NewsFilter
from goldscalper.risk.sizing import size_position


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    lot: float
    risk_amount: float
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @staticmethod
    def rejected(reasons: list[str]) -> "RiskDecision":
        return RiskDecision(approved=False, lot=0.0, risk_amount=0.0, reasons=tuple(reasons))


class RiskEngine:
    def __init__(
        self,
        config: RiskConfig,
        spec: SymbolSpec,
        news_filter: NewsFilter | None = None,
    ) -> None:
        self.config = config
        self.spec = spec
        self.news_filter = news_filter or NewsFilter(
            config.news_blackout_minutes, config.news_currencies
        )
        self._kill_switch_latched = False
        self._kill_switch_reason = ""
        self._halted_for_date: str | None = None

    # ------------------------------------------------------------------ state

    @property
    def kill_switch_latched(self) -> bool:
        return self._kill_switch_latched

    @property
    def kill_switch_reason(self) -> str:
        return self._kill_switch_reason

    def manual_reset(self) -> None:
        """Human-only action: clear the drawdown kill-switch after review."""
        self._kill_switch_latched = False
        self._kill_switch_reason = ""

    def _latch_kill_switch(self, reason: str) -> None:
        self._kill_switch_latched = True
        self._kill_switch_reason = reason

    # -------------------------------------------------------------- evaluation

    def evaluate(
        self,
        proposal: TradeProposal,
        account: AccountState,
        market: MarketState,
        now: datetime,
    ) -> RiskDecision:
        reasons: list[str] = []
        today = now.date().isoformat()

        # -- account-level kill-switch (checked first, latches permanently)
        drawdown = account.drawdown_pct()
        if drawdown >= self.config.max_drawdown_pct:
            self._latch_kill_switch(
                f"drawdown {drawdown:.1%} >= limit {self.config.max_drawdown_pct:.0%}"
            )
        if self._kill_switch_latched:
            reasons.append(f"kill_switch: {self._kill_switch_reason or 'latched'}")

        # -- daily loss halt (clears automatically on a new day)
        if self._halted_for_date is not None and self._halted_for_date != today:
            self._halted_for_date = None
        max_daily_loss = self.config.max_daily_loss_pct * account.balance
        if account.realized_pnl_today <= -max_daily_loss:
            self._halted_for_date = today
        if self._halted_for_date == today:
            reasons.append(
                f"daily_loss_halt: realized {account.realized_pnl_today:.2f} "
                f"<= -{max_daily_loss:.2f}, halted until next day"
            )

        # -- session limits
        if account.trades_today >= self.config.max_trades_per_day:
            reasons.append(
                f"max_trades_per_day: {account.trades_today} >= {self.config.max_trades_per_day}"
            )
        if len(account.open_positions) >= self.config.max_concurrent_positions:
            reasons.append(
                f"max_concurrent_positions: {len(account.open_positions)} "
                f">= {self.config.max_concurrent_positions}"
            )

        # -- market gates
        if market.spread > self.config.max_spread:
            reasons.append(f"spread_gate: {market.spread:.2f} > {self.config.max_spread:.2f}")
        event = self.news_filter.blocking_event(now)
        if event is not None:
            reasons.append(
                f"news_blackout: {event.currency} {event.impact} '{event.title}' at "
                f"{event.time.isoformat()}"
            )

        # -- proposal sanity
        if not proposal.stop_is_protective():
            reasons.append("invalid_stop: stop-loss is not on the losing side of entry")
        if not proposal.target_is_sane():
            reasons.append("invalid_target: take-profit is not on the winning side of entry")

        stop_pips = self.spec.price_to_pips(proposal.stop_distance())
        if stop_pips < self.config.min_stop_pips:
            reasons.append(f"stop_too_tight: {stop_pips:.0f} pips < {self.config.min_stop_pips:.0f}")
        if stop_pips > self.config.max_stop_pips:
            reasons.append(f"stop_too_wide: {stop_pips:.0f} pips > {self.config.max_stop_pips:.0f}")

        # -- risk sizing (requested risk is capped, never trusted)
        risk_pct = proposal.requested_risk_pct or self.config.default_risk_pct
        risk_pct = min(risk_pct, self.config.max_risk_pct)
        if risk_pct <= 0:
            reasons.append("invalid_risk: requested risk percentage is not positive")
        risk_amount = risk_pct * account.balance

        lot = 0.0
        if not reasons:
            lot = size_position(risk_amount, stop_pips, self.spec)
            if lot <= 0:
                reasons.append(
                    f"unsizeable: risk {risk_amount:.2f} over {stop_pips:.0f} pips "
                    f"rounds below min lot {self.spec.min_lot}"
                )

        if reasons:
            return RiskDecision.rejected(reasons)
        return RiskDecision(approved=True, lot=lot, risk_amount=risk_amount)
