from goldscalper.models import SymbolSpec
from goldscalper.risk.sizing import risk_at_lot, size_position


def test_blueprint_example(spec):
    # $1,000 account, 1% risk = $10, $3.00 stop = 300 pips -> 0.03 lots
    assert size_position(10.0, 300.0, spec) == 0.03


def test_rounds_down_not_up(spec):
    # 10 / (280 * 1) = 0.0357 -> 0.03, never 0.04
    assert size_position(10.0, 280.0, spec) == 0.03


def test_below_min_lot_is_no_trade(spec):
    # $5 risk over 600 pips = 0.0083 -> below 0.01 min -> refuse
    assert size_position(5.0, 600.0, spec) == 0.0


def test_never_exceeds_risk_budget(spec):
    for risk in (5.0, 7.5, 10.0, 20.0):
        for stop in (50.0, 137.0, 300.0, 999.0):
            lot = size_position(risk, stop, spec)
            assert risk_at_lot(lot, stop, spec) <= risk + 1e-9


def test_capped_at_max_lot():
    spec = SymbolSpec(max_lot=0.05)
    assert size_position(100.0, 100.0, spec) == 0.05


def test_zero_and_negative_inputs(spec):
    assert size_position(0.0, 300.0, spec) == 0.0
    assert size_position(10.0, 0.0, spec) == 0.0
    assert size_position(-10.0, 300.0, spec) == 0.0
    assert size_position(10.0, -5.0, spec) == 0.0


def test_float_step_boundary(spec):
    # exactly representable multiple: 9 / (300*1) = 0.03 even with float noise
    assert size_position(9.0, 300.0, spec) == 0.03
