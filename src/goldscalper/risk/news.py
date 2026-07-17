"""News blackout filter.

Blocks new entries inside a +/- window around high-impact events for the
configured currencies. The event feed is pluggable (Forex Factory JSON,
Trading Economics, MT5 calendar) — this module only owns the decision
logic, which must work identically in backtest and live."""

from __future__ import annotations

from datetime import datetime, timedelta

from goldscalper.models import CalendarEvent


class NewsFilter:
    def __init__(
        self,
        blackout_minutes: int,
        currencies: tuple[str, ...] = ("USD",),
        impacts: tuple[str, ...] = ("high",),
    ) -> None:
        self.window = timedelta(minutes=blackout_minutes)
        self.currencies = {c.upper() for c in currencies}
        self.impacts = {i.lower() for i in impacts}
        self._events: list[CalendarEvent] = []

    def load_events(self, events: list[CalendarEvent]) -> None:
        self._events = [
            e
            for e in events
            if e.currency.upper() in self.currencies and e.impact.lower() in self.impacts
        ]

    def blocking_event(self, now: datetime) -> CalendarEvent | None:
        """Return the event whose blackout window contains `now`, if any."""
        for event in self._events:
            if abs(event.time - now) <= self.window:
                return event
        return None

    def is_blocked(self, now: datetime) -> bool:
        return self.blocking_event(now) is not None
