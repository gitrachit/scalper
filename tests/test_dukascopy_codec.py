"""bi5 codec round-trips on synthetic payloads only — no network."""

from datetime import datetime, timezone

from goldscalper.data.dukascopy import decode_bi5, hour_url
from goldscalper.data.synthetic import encode_bi5
from goldscalper.data.dukascopy import Tick

HOUR = datetime(2025, 6, 2, 13, 0, tzinfo=timezone.utc)


def test_encode_decode_round_trip():
    ticks = [
        Tick(time=HOUR, bid=2400.00, ask=2400.30),
        Tick(time=HOUR.replace(minute=0, second=1), bid=2400.05, ask=2400.34),
        Tick(time=HOUR.replace(minute=30), bid=2399.80, ask=2400.10),
    ]
    raw = encode_bi5(ticks, HOUR)
    decoded = decode_bi5(raw, HOUR)
    assert len(decoded) == 3
    for original, got in zip(ticks, decoded):
        assert abs(got.bid - original.bid) < 1e-6
        assert abs(got.ask - original.ask) < 1e-6
        assert got.time == original.time


def test_empty_file_decodes_to_no_ticks():
    assert decode_bi5(b"", HOUR) == []


def test_hour_url_uses_zero_indexed_month():
    url = hour_url("XAUUSD", datetime(2025, 1, 5, 9, tzinfo=timezone.utc))
    # January -> month index 00
    assert url.endswith("/XAUUSD/2025/00/05/09h_ticks.bi5")


def test_download_hour_uses_cache(tmp_path, monkeypatch):
    from goldscalper.data import dukascopy

    ticks = [Tick(time=HOUR, bid=2400.0, ask=2400.3)]
    (tmp_path / "XAUUSD" / "2025" / "06" / "02").mkdir(parents=True)
    cache_file = tmp_path / "XAUUSD" / "2025" / "06" / "02" / "13h_ticks.bi5"
    cache_file.write_bytes(encode_bi5(ticks, HOUR))

    def _boom(*a, **k):
        raise AssertionError("network must not be touched when cache exists")

    monkeypatch.setattr(dukascopy.urllib.request, "urlopen", _boom)
    raw = dukascopy.download_hour("XAUUSD", HOUR, tmp_path)
    assert decode_bi5(raw, HOUR)[0].bid == 2400.0
