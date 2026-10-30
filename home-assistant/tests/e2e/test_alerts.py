"""Fault alert automations (config/automations.yaml), against the host sim.

Persistent notifications are read over the websocket (`persistent_notification/get`). The
automations run as written: run.sh names the sim "Main Thermostat", like the Tab5, so HA gives
it the entity ids they watch.

Cost: the sim's own recovery from a sensor fault takes 5 min of good readings, so the recovery
and interlock tests drive the binary_sensor state directly (POST /api/states: HA's state machine
only, the device is untouched) and put the real state back afterwards. The sensor-fault test uses
the real sim fault, then restarts the sim (a few seconds). The offline automation waits 10 min, so
its config is checked through HA's config API, and the e2e overlay shortens its 10 minutes to
OFFLINE_TEST_DELAY (30 s) so the HA-start path can be waited for.
"""

import os
import time

import docker
import pytest

from test_home import eid
from test_system import state

SENSOR_TEXT = "Main Thermostat: temperature sensor problem. Heating and cooling paused."
INTERLOCK_TEXT = ("Main Thermostat: the heat and cool relays were found on together, so both were cut. "
                  "Clear it on the System tab once it's checked; it takes effect once both units have been "
                  "off for their minimum off time (5 min by default).")
OFFLINE_TEXT = "Main Thermostat is offline (no contact for 10 minutes). It keeps running on its own."
SENSOR_CLEARED = "Main Thermostat: temperature sensor problem cleared."
INTERLOCK_CLEARED = "Main Thermostat: interlock fault cleared."
OFFLINE_CLEARED = "Main Thermostat: offline cleared."
HA_CONTAINER = os.environ.get("HA_CONTAINER", "chestnut-e2e-ha")
OFFLINE_TEST_DELAY = os.environ.get("OFFLINE_TEST_DELAY", "00:00:30")
# What the alert automations remember between an alert and its "cleared" notice.
ALERTED = [
    "input_boolean.chestnut_sensor_fault_alerted",
    "input_boolean.chestnut_interlock_fault_alerted",
    "input_boolean.chestnut_offline_alerted",
]
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
    for v in ALERTED:
        if ha.get_state(v) is not None:
            ha.call("input_boolean", "turn_off", {"entity_id": v})
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


def test_alert_switches_default_on(ha):
    """A fresh HA (this one): the three switches start on. First in the file, before any test
    touches them."""
    for gate in GATES.values():
        assert state(ha, gate) == "on", gate


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
    wait_for(ha, has_message(ha, SENSOR_CLEARED), 15, "the recovery notification")
    assert SENSOR_TEXT not in notifications(ha).values(), "the alert is dismissed on recovery"


def test_offline_automation_config(ha):
    """The transition path, checked in the loaded config (the overlay's shortened delay)."""
    cfg = ha.get("/api/config/automation/config/chestnut_alert_offline")
    trig = cfg["triggers"][0]
    assert trig["entity_id"] == ha.sim_climate()
    h, m, sec = (int(x) for x in OFFLINE_TEST_DELAY.split(":"))
    assert trig["to"] == "unavailable" and trig["for"] in (OFFLINE_TEST_DELAY, {"hours": h, "minutes": m, "seconds": sec})
    assert any(t.get("trigger") == "homeassistant" and t.get("event") == "start" for t in cfg["triggers"])
    assert GATES["offline"] in str(cfg.get("conditions", [])) + str(cfg["actions"])
    assert OFFLINE_TEXT in str(cfg["actions"])
    assert "persistent_notification.create" in str(cfg["actions"])
    assert ha.get_state("automation.chestnut_alert_offline")["state"] == "on"


# --- faults that pass through unavailable (Tab5 reconnects, HA restarts) ---------------------

def assert_quiet(ha, text, seconds=4):
    time.sleep(seconds)
    assert text not in notifications(ha).values(), f"unexpected: {text}"


def test_fault_via_unavailable_notifies(ha, clean, fake_binary):
    """A fault first seen as the Tab5 comes back (unavailable -> on) is a fault: alert."""
    fake_binary("sensor_fault", "unavailable")
    fake_binary("sensor_fault", "on")
    wait_for(ha, has_message(ha, SENSOR_TEXT), 15, "the sensor fault notification (from unavailable)")


def test_reconnect_with_fault_still_on_is_quiet(ha, clean, fake_binary):
    """on -> unavailable -> on is a reconnect, not a new fault: no second alert."""
    fake_binary("interlock_fault", "on")
    wait_for(ha, has_message(ha, INTERLOCK_TEXT), 15, "the interlock notification")
    dismiss_all(ha)
    fake_binary("interlock_fault", "unavailable")
    fake_binary("interlock_fault", "on")
    assert_quiet(ha, INTERLOCK_TEXT)


def test_fault_cleared_through_unavailable(ha, clean, fake_binary):
    """The interlock latch clears on a Tab5 reboot (on -> unavailable -> off): the alert is
    replaced by the cleared notice, not left up forever."""
    fake_binary("interlock_fault", "on")
    wait_for(ha, has_message(ha, INTERLOCK_TEXT), 15, "the interlock notification")
    fake_binary("interlock_fault", "unavailable")
    fake_binary("interlock_fault", "off")
    wait_for(ha, has_message(ha, INTERLOCK_CLEARED), 15, "the interlock cleared notification")
    assert INTERLOCK_TEXT not in notifications(ha).values(), "the alert is dismissed on recovery"


def test_reconnect_without_alert_is_quiet(ha, clean, fake_binary):
    """off -> unavailable -> off: nothing was alerted, so nothing is cleared."""
    fake_binary("sensor_fault", "unavailable")
    fake_binary("sensor_fault", "off")
    assert_quiet(ha, SENSOR_CLEARED)


def test_fault_dismissed_even_if_switch_turned_off(ha, clean, fake_binary):
    """Switch turned off mid-fault: on recovery the fault notification still goes (no cleared
    notice, the switch is off)."""
    fake_binary("sensor_fault", "on")
    wait_for(ha, has_message(ha, SENSOR_TEXT), 15, "the sensor fault notification")
    ha.call("input_boolean", "turn_off", {"entity_id": GATES["sensor_fault"]})
    fake_binary("sensor_fault", "off")
    wait_for(ha, lambda: SENSOR_TEXT not in notifications(ha).values(), 15, "the fault notification dismissed")
    assert SENSOR_CLEARED not in notifications(ha).values()


def test_new_alert_dismisses_old_cleared_notice(ha, clean, fake_binary):
    """A second fault replaces last time's "cleared" notice: the bell never shows both."""
    fake_binary("sensor_fault", "on")
    wait_for(ha, has_message(ha, SENSOR_TEXT), 15, "the sensor fault notification")
    fake_binary("sensor_fault", "off")
    wait_for(ha, has_message(ha, SENSOR_CLEARED), 15, "the recovery notification")
    fake_binary("sensor_fault", "on")
    wait_for(ha, has_message(ha, SENSOR_TEXT), 15, "the second sensor fault notification")
    assert SENSOR_CLEARED not in notifications(ha).values(), "the old cleared notice is still up"


@pytest.fixture
def fake_climate(ha):
    """set('heat'|'unavailable'|...): fake the sim climate's state; restored afterwards."""
    entity = ha.sim_climate()
    cur = ha.get_state(entity)

    def set_state(value):
        ha.post(f"/api/states/{entity}", {"state": value, "attributes": cur["attributes"]})

    yield set_state
    ha.post(f"/api/states/{entity}", {"state": cur["state"], "attributes": cur["attributes"]})


def test_offline_cleared_through_unknown(ha, clean, fake_climate):
    """Back from offline through unknown (unavailable -> unknown -> heat): the alert is still
    cleared, and the next offline alert isn't muted by a flag left on."""
    offline_alerted = "input_boolean.chestnut_offline_alerted"
    ha.call("input_boolean", "turn_on", {"entity_id": offline_alerted})  # the 10 min alert fired
    fake_climate("unavailable")
    fake_climate("unknown")
    fake_climate("heat")
    wait_for(ha, has_message(ha, OFFLINE_CLEARED), 15, "the offline cleared notification")
    assert state(ha, offline_alerted) == "off"


def test_alert_entity_check_names_a_missing_entity(ha, clean):
    """An entity the alerts watch doesn't exist (here: renamed in HA): the startup check says
    which, and takes the notice down once it exists again."""
    watched = ha.sim_entity("binary_sensor", "sensor_fault")
    assert watched == "binary_sensor.main_thermostat_sensor_fault"  # the id automations.yaml names
    check = "automation.chestnut_alert_entity_check"
    renamed = "binary_sensor.chestnut_renamed_sensor_fault"
    ha.ws({"type": "config/entity_registry/update", "entity_id": watched, "new_entity_id": renamed})
    try:
        ha.call("automation", "trigger", {"entity_id": check})
        wait_for(ha, lambda: any(watched in m for m in notifications(ha).values()), 60,
                 "the missing-entity notice")
    finally:
        ha.ws({"type": "config/entity_registry/update", "entity_id": renamed, "new_entity_id": watched})
    ha.call("automation", "trigger", {"entity_id": check})
    wait_for(ha, lambda: not any(watched in m for m in notifications(ha).values()), 60,
             "the missing-entity notice taken down")


# --- HA starting while the Tab5 is already down ------------------------------------------

def restart_ha(ha):
    docker.from_env().containers.get(HA_CONTAINER).restart(timeout=60)
    wait_until_running = lambda: ha.get("/api/config").get("state") == "RUNNING"  # noqa: E731
    wait_for(ha, wait_until_running, 240, "the test HA to be running again")


def test_offline_alert_after_ha_start(ha, sim, clean):
    """HA (re)starts with the Tab5 already unavailable: no transition ever happens, so the alert
    must come from the start path, OFFLINE_TEST_DELAY (10 min in the real config) after start."""
    # A muted alert stays muted across the restart (the switches are restored, not reset).
    ha.call("input_boolean", "turn_off", {"entity_id": GATES["sensor_fault"]})
    sim.stop()
    ha.wait_state(ha.sim_climate(), lambda s: s["state"] == "unavailable", timeout=60)
    restart_ha(ha)
    assert ha.get_state(GATES["offline"])["state"] == "on"
    assert ha.get_state(GATES["sensor_fault"])["state"] == "off", "the muted alert came back on"
    wait_for(ha, has_message(ha, OFFLINE_TEXT), 150, "the offline notification after HA start")
    sim.start(wait=True, timeout=240)
    wait_for(ha, has_message(ha, OFFLINE_CLEARED), 30, "the offline cleared notification")
    assert OFFLINE_TEXT not in notifications(ha).values(), "the offline alert is dismissed on recovery"
