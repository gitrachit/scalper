from datetime import timedelta

from goldscalper.models import CalendarEvent
from goldscalper.risk.news import NewsFilter
from tests.conftest import NOW


def make_filter(**events_kwargs) -> NewsFilter:
    f = NewsFilter(blackout_minutes=30, currencies=("USD",))
    defaults = dict(time=NOW, currency="USD", impact="high", title="NFP")
    defaults.update(events_kwargs)
    f.load_events([CalendarEvent(**defaults)])
    return f


def test_blocks_inside_window_before_and_after():
    f = make_filter(time=NOW + timedelta(minutes=29))
    assert f.is_blocked(NOW)
    f = make_filter(time=NOW - timedelta(minutes=29))
    assert f.is_blocked(NOW)


def test_window_boundary_inclusive():
    f = make_filter(time=NOW + timedelta(minutes=30))
    assert f.is_blocked(NOW)


def test_clear_outside_window():
    f = make_filter(time=NOW + timedelta(minutes=31))
    assert not f.is_blocked(NOW)


def test_ignores_low_impact_and_other_currencies():
    assert not make_filter(impact="low").is_blocked(NOW)
    assert not make_filter(currency="EUR").is_blocked(NOW)


def test_case_insensitive_matching():
    assert make_filter(currency="usd", impact="HIGH").is_blocked(NOW)


def test_no_events_never_blocks():
    f = NewsFilter(blackout_minutes=30)
    assert not f.is_blocked(NOW)
