import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ble import parsers  # noqa: E402
from stages import battery_update, live_eval  # noqa: E402

RULES = {"spec_full_charge_min": 60, "battery_variance_pct": 20, "battery_stall_min": 10,
         "hr": [40, 180], "live_no_data_s": 30}


def test_parsers_roundtrip():
    for p, v in [("uint8", 87), ("int16_le", -240), ("uint32_le", 123456), ("unix_time_le", 1763250000)]:
        assert parsers.decode(p, parsers.encode(p, v)) == v
    assert parsers.decode("hr_measurement", bytes([0x01, 0x48, 0x00])) == 72
    assert parsers.encode("raw_hex", "0a01") == b"\x0a\x01"


def test_battery_pass_within_estimate():
    row = {}
    battery_update(row, 50, 0, RULES)                  # 50% -> estimate 30 min
    assert row["est_total_min"] == 30 and row["status"] == "PENDING"
    battery_update(row, 75, 15 * 60, RULES)
    assert row["eta_min"] == 15.0                      # measured 25%/15min -> 15 min left
    battery_update(row, 100, 32 * 60, RULES)
    assert row["status"] == "PASS" and row["actual_min"] == 32 and row["variance_min"] == 2


def test_battery_fail_slow_and_stall():
    row = {}
    battery_update(row, 50, 0, RULES)
    battery_update(row, 100, 45 * 60, RULES)           # 45 vs 30 min = +50%
    assert row["status"].startswith("FAIL")
    row = {}
    battery_update(row, 40, 0, RULES)
    battery_update(row, 40, 11 * 60, RULES)
    assert row["status"].startswith("FAIL: no charge rise")


def test_live_eval_rules():
    row = {"start_t": 0, "last_data_t": 30, "samples": [[10, 70], [20, 72], [30, 75]]}
    assert live_eval("hr", row, RULES, 31) == "PASS"
    row["samples"] = [[10, 0], [20, 0], [30, 0]]
    assert live_eval("hr", row, RULES, 31).startswith("FAIL")
    assert live_eval("steps", {"start_t": 0, "last_data_t": 5, "samples": [[1, 10], [5, 10]]}, RULES, 6, final=True).startswith("FAIL")
    assert live_eval("hr", {"start_t": 0, "samples": []}, RULES, 40) == "FAIL: no data"
