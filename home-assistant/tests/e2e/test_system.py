"""The System tab (safety and timers, alerts, wall screen, device, event log), against the host
sim. Every test puts back the state it changes."""

import re

import pytest
from playwright.sync_api import expect

from ha_client import SIM_DEVICE, wait_until
from test_home import dash, eid, ready, tid, to_f
from test_room import heat_forced  # noqa: F401 - fixture

ALERTS = ("sensor_fault", "interlock_fault", "offline", "relay_fault")


def system_tab(page):
    ready(page)
    dash(page).locator('[data-tab="SYSTEM"]').click()
    expect(tid(page, "safety")).to_be_visible(timeout=10_000)


def state(ha, entity_id):
    return ha.get_state(entity_id)["state"]


def test_timer_edit_writes_and_clamps(page, ha):
    entity = eid(ha, "number", "heat_min_run")
    st = ha.get_state(entity)
    prev, lo, hi = st["state"], st["attributes"]["min"], st["attributes"]["max"]
    try:
        system_tab(page)
        field = tid(page, "timer-heat_min_run")
        expect(field).to_have_value(str(round(float(prev))), timeout=10_000)
        expect(field).to_have_attribute("min", str(int(lo)))
        expect(field).to_have_attribute("max", str(int(hi)))
        # Above the limit: written as the max, and the field shows the max.
        field.fill("999")
        field.press("Tab")
        ha.wait_state(entity, lambda s: float(s["state"]) == hi, timeout=10)
        expect(field).to_have_value(str(int(hi)), timeout=5_000)
        # Below it: the min.
        field.fill("0")
        field.press("Tab")
        ha.wait_state(entity, lambda s: float(s["state"]) == lo, timeout=10)
        expect(field).to_have_value(str(int(lo)), timeout=5_000)
        # Inside it: as typed.
        mid = int(lo) + 1
        field.fill(str(mid))
        field.press("Tab")
        ha.wait_state(entity, lambda s: float(s["state"]) == mid, timeout=10)
    finally:
        ha.call("number", "set_value", {"entity_id": entity, "value": float(prev)})


def test_clear_interlock_disabled_normally(page, ha):
    assert state(ha, eid(ha, "binary_sensor", "interlock_fault")) == "off"
    system_tab(page)
    expect(tid(page, "safety-interlock-val")).to_have_text("✓ armed", timeout=10_000)
    expect(tid(page, "clear-interlock")).to_be_disabled()


def test_interlock_trip_blanks_timer_rows_and_explains_clear(page, ha):
    """While the interlock is tripped the relays are cut whatever the climate's action says, and
    the trip time isn't published: the four timer rows show "—". Clear says when it takes effect,
    and after a press says it was asked for (a second press would be ignored)."""
    entity = eid(ha, "binary_sensor", "interlock_fault")
    cur = ha.get_state(entity)
    ha.post(f"/api/states/{entity}", {"state": "on", "attributes": cur["attributes"]})  # HA's view only
    try:
        system_tab(page)
        expect(tid(page, "safety-interlock-val")).to_have_text("⚠ tripped", timeout=10_000)
        for row in ("heat-run", "heat-off", "cool-run", "cool-off"):
            expect(tid(page, f"safety-{row}-val")).to_have_text("—")
        clear = tid(page, "clear-interlock")
        expect(clear).to_be_enabled()
        expect(tid(page, "clear-note")).to_contain_text("takes effect once the furnace and ac min off times")
        clear.click()
        expect(tid(page, "clear-note")).to_contain_text("clear requested", timeout=5_000)
        expect(clear).to_be_disabled()
    finally:
        ha.post(f"/api/states/{entity}", {"state": cur["state"], "attributes": cur["attributes"]})
    expect(tid(page, "clear-note")).to_have_text("", timeout=10_000)


def test_alert_toggle_flips_boolean(page, ha):
    entity = "input_boolean.chestnut_alert_sensor_fault"
    st = ha.get_state(entity)
    assert st is not None, "the alert helper is missing from configuration.yaml"
    assert st["attributes"].get("friendly_name") == "Alert: sensor fault"
    for k in ALERTS:
        assert ha.get_state(f"input_boolean.chestnut_alert_{k}") is not None, k
    prev = st["state"]
    try:
        ha.call("input_boolean", "turn_on", {"entity_id": entity})
        ha.wait_state(entity, lambda s: s["state"] == "on")
        system_tab(page)
        for k in ALERTS:
            expect(tid(page, f"alert-{k}")).to_be_visible()
        sw = tid(page, "alert-sensor_fault")
        expect(sw).to_have_attribute("aria-checked", "true", timeout=10_000)
        expect(sw).to_have_text("ON")
        sw.click()
        ha.wait_state(entity, lambda s: s["state"] == "off", timeout=10)
        expect(sw).to_have_attribute("aria-checked", "false", timeout=5_000)
        expect(sw).to_have_text("OFF")
        sw.click()
        ha.wait_state(entity, lambda s: s["state"] == "on", timeout=10)
        expect(sw).to_have_attribute("aria-checked", "true", timeout=5_000)
    finally:
        ha.call("input_boolean", "turn_on" if prev == "on" else "turn_off", {"entity_id": entity})


def test_event_log_shows_heat_on(page, ha, heat_forced):  # noqa: F811 - fixture
    call_heat = eid(ha, "binary_sensor", "call_heat")
    # After a sim boot the furnace waits out its minimum off time (3 min) first.
    ha.wait_state(call_heat, lambda s: s["state"] == "on", timeout=300)
    system_tab(page)
    log = tid(page, "event-log")
    expect(log.locator("[data-event]").first).to_be_visible(timeout=20_000)
    expect(log).to_contain_text("furnace on", timeout=20_000)
    rows = log.locator("[data-event]")
    assert rows.count() <= 40
    # Newest first (each row carries its time in ms).
    times = [float(t) for t in rows.evaluate_all("els => els.map(e => e.dataset.t)")]
    assert times == sorted(times, reverse=True), times
    # The running furnace's minimum run counts down from action_elapsed (default 3 min).
    expect(tid(page, "safety-heat-run-val")).to_have_text(re.compile(r"^(\d+ min left|✓ ok)$"), timeout=10_000)
    # The bar grows from action_elapsed, interpolated between the device's 30 s publishes.
    bar = tid(page, "safety-heat-run-bar")
    w0 = bar.evaluate("el => parseFloat(el.style.width)")
    page.wait_for_timeout(3000)
    w1 = bar.evaluate("el => parseFloat(el.style.width)")
    assert w1 > 0 and (w1 > w0 or w1 == 100), (w0, w1)
    # The idle AC's minimum off can't be known while the furnace runs.
    expect(tid(page, "safety-cool-off-val")).to_have_text("—")


def test_device_dash_on_sim(page, ha):
    system_tab(page)
    # The host sim has no Wi-Fi, uptime, clock or IP sensors, and no wall screen.
    for k in ("ip", "uptime", "wifi", "clock"):
        expect(tid(page, f"dev-{k}")).to_have_text("—", timeout=10_000)
    expect(tid(page, "dev-name")).to_have_text(SIM_DEVICE)
    sim_dev = next(d for d in ha.ws({"type": "config/device_registry/list"})
                   if (d.get("name_by_user") or d.get("name")) == SIM_DEVICE)
    expect(tid(page, "dev-firmware")).to_have_text(sim_dev.get("sw_version") or "—")
    for k in ("scr-bright", "scr-dim"):
        expect(tid(page, k)).to_be_disabled()
        expect(tid(page, f"{k}-val")).to_have_text("—")
    expect(tid(page, "dark-theme")).to_be_disabled()
    expect(tid(page, "dark-theme")).to_have_text("—")


def test_relay_unit_row_follows_fault(page, ha):
    """Milestone 4: the relay unit stopped answering. Faked through the states API (the sim only
    republishes relay_fault when Sim Fault changes), and put back afterwards."""
    entity = eid(ha, "binary_sensor", "relay_fault")
    cur = ha.get_state(entity)
    assert cur["state"] == "off"
    try:
        system_tab(page)
        expect(tid(page, "safety-relay-val")).to_have_text("✓ ok", timeout=10_000)
        ha.post(f"/api/states/{entity}", {"state": "on", "attributes": cur["attributes"]})
        expect(tid(page, "safety-relay-val")).to_have_text("⚠ fault", timeout=10_000)
        expect(tid(page, "status-word")).to_have_text("PAUSED", timeout=10_000)
    finally:
        ha.post(f"/api/states/{entity}", {"state": cur["state"], "attributes": cur["attributes"]})
    expect(tid(page, "safety-relay-val")).to_have_text("✓ ok", timeout=10_000)


def test_offset_control_writes_fahrenheit(page, ha):
    """The offset is °F with no device_class, so the metric test HA keeps it in °F, and the sensor's
    reading moves by the same °F against the sim's true room (sim_room_f, no offset)."""
    entity = eid(ha, "number", "temperature_offset")
    st = ha.get_state(entity)
    assert st["attributes"].get("unit_of_measurement") == "°F"
    prev = float(st["state"])
    room, true_room = eid(ha, "sensor", "room_temperature"), eid(ha, "sensor", "sim_room_f")

    def gap_f():  # the sensor's reading minus the true room, in °F (noise is ±0.09 °F)
        r, t = ha.get_state(room), ha.get_state(true_room)
        return (to_f(r["state"], r["attributes"].get("unit_of_measurement"))
                - to_f(t["state"], t["attributes"].get("unit_of_measurement")))

    try:
        if prev != 0:
            ha.call("number", "set_value", {"entity_id": entity, "value": 0})
            ha.wait_state(entity, lambda s: float(s["state"]) == 0, timeout=10)
        system_tab(page)
        field = tid(page, "offset")
        expect(field).to_be_enabled(timeout=10_000)
        expect(field).to_have_value("0")
        expect(field).to_have_attribute("step", "0.1")
        expect(field).to_have_attribute("min", "-5")
        expect(field).to_have_attribute("max", "5")
        wait_until(lambda: abs(gap_f()) < 0.3, 25, message="the reading to match the true room at offset 0")
        field.fill("1.5")
        field.press("Tab")
        ha.wait_state(entity, lambda s: float(s["state"]) == 1.5, timeout=10)
        assert ha.get_state(entity)["attributes"].get("unit_of_measurement") == "°F"
        expect(field).to_have_value("1.5", timeout=5_000)
        wait_until(lambda: abs(gap_f() - 1.5) < 0.3, 25, message="the reading to move by +1.5 °F")
    finally:
        ha.call("number", "set_value", {"entity_id": entity, "value": prev})
