"""The System tab (safety and timers, alerts, wall screen, device, event log), against the host
sim. Every test puts back the state it changes."""

import re

import pytest
from playwright.sync_api import expect

from test_home import dash, eid, ready, tid
from test_room import heat_forced  # noqa: F401 - fixture

ALERTS = ("sensor_fault", "interlock_fault", "offline")


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
    expect(tid(page, "dev-name")).to_have_text("Main Thermostat (Sim)")
    sim_dev = next(d for d in ha.ws({"type": "config/device_registry/list"})
                   if (d.get("name_by_user") or d.get("name")) == "Main Thermostat (Sim)")
    expect(tid(page, "dev-firmware")).to_have_text(sim_dev.get("sw_version") or "—")
    for k in ("scr-bright", "scr-dim"):
        expect(tid(page, k)).to_be_disabled()
        expect(tid(page, f"{k}-val")).to_have_text("—")
    expect(tid(page, "dark-theme")).to_be_disabled()
    expect(tid(page, "dark-theme")).to_have_text("—")
