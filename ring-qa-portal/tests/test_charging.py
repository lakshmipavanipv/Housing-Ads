"""Charging is only shown when the battery really climbs; 86 % off the charger is NOT CHARGING, not NEEDS CHARGING."""
from types import SimpleNamespace
from unittest import mock

from ble.manager import RingManager
from stages import charge_state


def feed(readings):
    mgr = RingManager(SimpleNamespace(active={"protocol": "jieli", "rules": {}}))
    mgr.rings["r"] = {"addr": "r"}
    for t, pct, mv in readings:
        with mock.patch("ble.manager.time.time", return_value=t):
            mgr._battery_trend("r", pct, mv)
    return mgr.rings["r"]["charging"]


def test_high_resting_voltage_is_not_charging():
    # real SR16 ring off the charger: 86 % at ~4.29 V, reading jitters 85/86 - used to show CHARGING
    assert not feed([(0, 85, 4289), (15, 86, 4296), (30, 85, 4289), (60, 86, 4296), (90, 86, 4289), (120, 85, 4289)])


def test_real_climb_is_charging():
    assert feed([(0, 60, 4000), (30, 61, 4010), (60, 62, 4020), (90, 63, 4030)])


def test_taken_off_charger_clears():
    assert not feed([(0, 60, 4000), (60, 62, 4020), (90, 63, 4030), (150, 62, 3990), (200, 61, 3980)])


def test_status_labels():
    assert charge_state({"current": 86}, False) == "NOT CHARGING"
    assert charge_state({"current": 12}, False) == "NEEDS CHARGING"
    assert charge_state({"current": 86}, True) == "CHARGING"
    assert charge_state({"current": 100}, False) == "FULLY CHARGED"
