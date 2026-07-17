"""Resume/skip logic for the bulk downloader — no network.

Every hour file is pre-seeded in the cache, so download_hour returns the
cached bytes and urlopen is never called (a monkeypatched urlopen would
raise if it were)."""

from datetime import datetime, timedelta, timezone

import pytest

from goldscalper.data import dukascopy
from goldscalper.data.dukascopy import (
    download_range,
    hours_in_range,
    missing_hours,
)
from goldscalper.data.dukascopy import Tick
from goldscalper.data.synthetic import encode_bi5

START = datetime(2025, 6, 3, 12, tzinfo=timezone.utc)


def _seed(cache, hour):
    from goldscalper.data.dukascopy import _cache_path

    path = _cache_path(cache, "XAUUSD", hour)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_bi5([Tick(time=hour, bid=2400.0, ask=2400.3)], hour))


def test_hours_in_range_is_half_open():
    hours = hours_in_range(START, START + timedelta(hours=3))
    assert len(hours) == 3
    assert hours[0] == START
    assert hours[-1] == START + timedelta(hours=2)


def test_missing_hours_reflects_cache(tmp_path):
    end = START + timedelta(hours=4)
    assert len(missing_hours("XAUUSD", START, end, tmp_path)) == 4
    _seed(tmp_path, START)
    _seed(tmp_path, START + timedelta(hours=2))
    missing = missing_hours("XAUUSD", START, end, tmp_path)
    assert missing == [START + timedelta(hours=1), START + timedelta(hours=3)]


def test_download_range_fully_cached_touches_no_network(tmp_path, monkeypatch):
    end = START + timedelta(hours=3)
    for h in hours_in_range(START, end):
        _seed(tmp_path, h)

    def _boom(*a, **k):
        raise AssertionError("network must not be touched when fully cached")

    monkeypatch.setattr(dukascopy.urllib.request, "urlopen", _boom)
    done, failed = download_range("XAUUSD", START, end, tmp_path)
    assert done == 3
    assert failed == []


def test_download_range_resilient_records_failures(tmp_path, monkeypatch):
    end = START + timedelta(hours=3)
    _seed(tmp_path, START)  # first hour cached, other two will "fail"

    def _fail(*a, **k):
        raise TimeoutError("simulated relay timeout")

    monkeypatch.setattr(dukascopy.urllib.request, "urlopen", _fail)
    # retries=1 keeps the test fast; raise_on_fail=False skips and records
    monkeypatch.setattr(dukascopy.time, "sleep", lambda *_: None)
    done, failed = download_range(
        "XAUUSD", START, end, tmp_path, raise_on_fail=False
    )
    assert done == 1  # only the cached hour
    assert len(failed) == 2


def test_download_range_raises_by_default(tmp_path, monkeypatch):
    def _fail(*a, **k):
        raise TimeoutError("simulated relay timeout")

    monkeypatch.setattr(dukascopy.urllib.request, "urlopen", _fail)
    monkeypatch.setattr(dukascopy.time, "sleep", lambda *_: None)
    with pytest.raises(RuntimeError):
        download_range("XAUUSD", START, START + timedelta(hours=1), tmp_path)
