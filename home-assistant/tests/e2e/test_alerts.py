"""Fault alert automations (config/automations.yaml), against the host sim.

Persistent notifications are read over the websocket (`persistent_notification/get`). The e2e
overlay rewrites the automations' real-install entity ids to the sim's.

Cost: the sim's own recovery from a sensor fault takes 5 min of good readings, so the recovery
and interlock tests drive the binary_sensor state directly (POST /api/states: HA's state machine
only, the device is untouched) and put the real state back afterwards. The sensor-fault test uses
the real sim fault, then restarts the sim (a few seconds). The offline automation waits 10 min, so
its config is checked through HA's config API instead of waiting.
"""

import pytest

from test_home import eid
from test_system import state

SENSOR_TEXT = "Main Thermostat: temperature sensor problem. Heating and cooling paused."
INTERLOCK_TEXT = ("Main Thermostat: the heat and cool relays were found on together, so both were cut. "
                  "Clear it once it's checked.")
OFFLINE_TEXT = "Main Thermostat is offline (no contact for 10 minutes). It keeps running on its own."
GATES = {
    "sensor_fault": "input_boolean.chestnut_alert_sensor_fault",
    "interlock_fault": "input_boolean.chestnut_alert_interlock_fault",
    "offline": "input_boolean.chestnut_alert_offline",
}


def notifications(ha):
    """{notification_id: message} of the persistent notifications HA holds."""
    got = ha.ws({"type": "persistent_notification/get"})
    items = got.values() if isinstance(got, dict) else got
    return {n["notification_id"]: n["message"] for n in items}


def dismiss_all(ha):
    for nid in notifications(ha):
        ha.call("persistent_notification", "dismiss", {"notification_id": nid})


def has_message(ha, text):
    return lambda: text in notifications(ha).values()


def wait_for(ha, predicate, timeout, message):
    from ha_client import wait_until
    return wait_until(predicate, timeout, interval=0.5, message=message)


@pytest.fixture
def clean(ha):
    dismiss_all(ha)
    prev = {k: state(ha, v) for k, v in GATES.items()}
    for v in GATES.values():
        ha.call("input_boolean", "turn_on", {"entity_id": v})
    yield
    for k, v in GATES.items():
        ha.call("input_boolean", "turn_on" if prev[k] == "on" else "turn_off", {"entity_id": v})
    dismiss_all(ha)


@pytest.fixture
def fake_binary(ha):
    """set(object_id, 'on'|'off'): fake a sim binary_sensor's state; restored afterwards."""
    saved = {}

    def set_state(object_id, value):
        entity = eid(ha, "binary_sensor", object_id)
        cur = ha.get_state(entity)
        saved.setdefault(entity, cur)
        ha.post(f"/api/states/{entity}", {"state": value, "attributes": cur["attributes"]})

    yield set_state
    for entity, cur in saved.items():
        ha.post(f"/api/states/{entity}", {"state": cur["state"], "attributes": cur["attributes"]})


def test_sensor_fault_notifies(ha, sim, clean):
    fault = eid(ha, "select", "sim_fault")
    try:
        ha.call("select", "select_option", {"entity_id": fault, "option": "Out of range"})
        wait_for(ha, has_message(ha, SENSOR_TEXT), 15, "the sensor fault notification")
    finally:
        ha.call("select", "select_option", {"entity_id": fault, "option": "None"})
        # The sanity checker needs 5 min of good readings to clear; a fresh sim starts clean.
        sim.stop()
        sim.start(wait=True)


def test_interlock_fault_notifies(ha, clean, fake_binary):
    fake_binary("interlock_fault", "on")
    wait_for(ha, has_message(ha, INTERLOCK_TEXT), 15, "the interlock notification")


def test_alert_off_silences(ha, clean, fake_binary):
    ha.call("input_boolean", "turn_off", {"entity_id": GATES["interlock_fault"]})
    fake_binary("interlock_fault", "on")
    # A positive control on a still-gated alert proves the automations are running.
    fake_binary("sensor_fault", "on")
    wait_for(ha, has_message(ha, SENSOR_TEXT), 15, "the (enabled) sensor fault notification")
    assert INTERLOCK_TEXT not in notifications(ha).values()


def test_recovery_notifies(ha, clean, fake_binary):
    fake_binary("sensor_fault", "on")
    wait_for(ha, has_message(ha, SENSOR_TEXT), 15, "the sensor fault notification")
    fake_binary("sensor_fault", "off")
    cleared = "Main Thermostat: temperature sensor problem cleared."
    wait_for(ha, has_message(ha, cleared), 15, "the recovery notification")
    assert SENSOR_TEXT not in notifications(ha).values(), "the alert is dismissed on recovery"


def test_offline_automation_config(ha):
    """Waiting 10 minutes is too slow: check the trigger, gate and copy in the loaded config."""
    cfg = ha.get("/api/config/automation/config/chestnut_alert_offline")
    trig = cfg["triggers"][0]
    assert trig["entity_id"] == ha.sim_climate()
    assert trig["to"] == "unavailable" and trig["for"] in ("00:10:00", {"hours": 0, "minutes": 10, "seconds": 0})
    assert GATES["offline"] in str(cfg["conditions"])
    assert OFFLINE_TEXT in str(cfg["actions"])
    assert "persistent_notification.create" in str(cfg["actions"])
    assert ha.get_state("automation.chestnut_alert_offline")["state"] == "on"
