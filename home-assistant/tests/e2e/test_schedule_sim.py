"""The Schedule and Simulation tabs, and the Home card's level pills with the schedule off,
against the host sim. Every test puts back the sim/schedule state it changes."""

import json
import time
from datetime import datetime, timezone

import pytest
from playwright.sync_api import expect

from conftest import open_dashboard
from ha_client import wait_until
from test_home import dash, eid, from_f, history, ready, tid, to_f, unit_of

PERIODS = ("wake", "leave", "return", "sleep")


def tab(page, name):
    dash(page).locator(f'[data-tab="{name}"]').click()


def state(ha, entity_id):
    return ha.get_state(entity_id)["state"]


def num_f(ha, entity_id):
    st = ha.get_state(entity_id)
    return round(to_f(st["state"], st["attributes"].get("unit_of_measurement")))


def set_num_f(ha, entity_id, f):
    ha.call("number", "set_value", {"entity_id": entity_id, "value": from_f(f, unit_of(ha, entity_id))})


def set_switch(ha, entity_id, on):
    if state(ha, entity_id) != ("on" if on else "off"):
        ha.call("switch", "turn_on" if on else "turn_off", {"entity_id": entity_id})
    ha.wait_state(entity_id, lambda s: s["state"] == ("on" if on else "off"))


def schedule_tab(page):
    ready(page)
    tab(page, "SCHEDULE")
    expect(tid(page, "schedule")).to_be_visible(timeout=10_000)


def day_bar(periods):
    """rules.dayBar in Python: [(level, minutes)] for [(time "HH:MM[:SS]", level)]."""
    ps = sorted(((int(t[:2]) * 60 + int(t[3:5]), lvl) for t, lvl in periods))
    out = []
    if ps[0][0] > 0:
        out.append((ps[-1][1], ps[0][0]))
    for i, (at, lvl) in enumerate(ps):
        end = ps[i + 1][0] if i + 1 < len(ps) else 1440
        if end > at:
            out.append((lvl, end - at))
    return out


def rendered_bar(page, day):
    return tid(page, f"week-{day}").evaluate(
        "el => [...el.querySelectorAll('[data-level]')].map(s => [s.dataset.level, Number(s.style.flexGrow),"
        " getComputedStyle(s).backgroundColor])")


def expected_bar(ha, day):
    return day_bar([(state(ha, eid(ha, "time", f"sched_{day}_{p}_time")),
                     state(ha, eid(ha, "select", f"sched_{day}_{p}_level"))) for p in PERIODS])


COLOURS = {"Comfort": "rgb(238, 238, 238)", "Eco": "rgb(58, 58, 58)"}


# --- Schedule ----------------------------------------------------------------------------------
def test_edit_weekday_leave_time(page, ha):
    entity = eid(ha, "time", "sched_weekday_leave_time")
    prev = state(ha, entity)
    try:
        schedule_tab(page)
        tid(page, "day-weekday").click()
        expect(tid(page, "day-weekday")).to_have_attribute("aria-pressed", "true")
        field = tid(page, "sched-time-leave")
        expect(field).to_have_value(prev[:5], timeout=10_000)
        field.fill("09:15")
        ha.wait_state(entity, lambda s: s["state"] == "09:15:00", timeout=10)
        expect(field).to_have_value("09:15")
    finally:
        ha.call("time", "set_value", {"entity_id": entity, "time": prev})


def test_level_select_sched(page, ha):
    entity = eid(ha, "select", "sched_weekend_sleep_level")
    prev = state(ha, entity)
    other = "Comfort" if prev == "Eco" else "Eco"
    try:
        schedule_tab(page)
        tid(page, "day-weekend").click()
        sel = tid(page, "sched-level-sleep")
        expect(sel).to_have_value(prev, timeout=10_000)
        sel.select_option(other)
        ha.wait_state(entity, lambda s: s["state"] == other, timeout=10)
        expect(sel).to_have_value(other)
    finally:
        ha.call("select", "select_option", {"entity_id": entity, "option": prev})


def test_week_bar_updates(page, ha):
    level = eid(ha, "select", "sched_weekday_return_level")
    sleep = eid(ha, "time", "sched_weekday_sleep_time")
    prev_level, prev_sleep = state(ha, level), state(ha, sleep)
    try:
        schedule_tab(page)
        for day in ("weekday", "weekend"):
            want = expected_bar(ha, day)
            wait_until(lambda: [r[:2] for r in rendered_bar(page, day)] == [list(w) for w in want], 10,
                       message=f"the {day} bar to match {want}")
            for lvl, _, colour in rendered_bar(page, day):
                assert colour == COLOURS[lvl], (lvl, colour)
        # Change the schedule from HA: the bar follows without a reload.
        ha.call("select", "select_option", {"entity_id": level, "option": "Eco" if prev_level == "Comfort" else "Comfort"})
        ha.call("time", "set_value", {"entity_id": sleep, "time": "21:00:00"})
        ha.wait_state(sleep, lambda s: s["state"] == "21:00:00")
        want = expected_bar(ha, "weekday")
        wait_until(lambda: [r[:2] for r in rendered_bar(page, "weekday")] == [list(w) for w in want], 10,
                   message=f"the weekday bar to follow the change {want}")
    finally:
        ha.call("select", "select_option", {"entity_id": level, "option": prev_level})
        ha.call("time", "set_value", {"entity_id": sleep, "time": prev_sleep})


def row_opacity(page, period):
    return float(tid(page, f"sched-row-{period}").evaluate("el => getComputedStyle(el).opacity"))


def test_schedule_off_dims_rows(page, ha):
    sw = eid(ha, "switch", "schedule_enabled")
    set_switch(ha, sw, True)
    try:
        schedule_tab(page)
        toggle = tid(page, "sched-switch")
        expect(toggle).to_have_attribute("aria-checked", "true", timeout=10_000)
        assert all(row_opacity(page, p) == 1 for p in PERIODS)
        toggle.click()
        ha.wait_state(sw, lambda s: s["state"] == "off", timeout=10)
        expect(toggle).to_have_attribute("aria-checked", "false", timeout=10_000)
        wait_until(lambda: all(row_opacity(page, p) < 0.5 for p in PERIODS), 5, message="rows to dim")
        toggle.click()
        ha.wait_state(sw, lambda s: s["state"] == "on", timeout=10)
        wait_until(lambda: all(row_opacity(page, p) == 1 for p in PERIODS), 5, message="rows to undim")
    finally:
        set_switch(ha, sw, True)


def test_comfort_stepper_writes(page, ha):
    entity = eid(ha, "number", "comfort_target")
    prev = num_f(ha, entity)
    up = prev < 90
    want = prev + 1 if up else prev - 1
    try:
        schedule_tab(page)
        expect(tid(page, "comfort-val")).to_have_text(f"{prev}°", timeout=10_000)
        tid(page, "comfort-plus" if up else "comfort-minus").click()
        expect(tid(page, "comfort-val")).to_have_text(f"{want}°", timeout=1_000)
        wait_until(lambda: num_f(ha, entity) == want, 10, message=f"comfort_target {want}")
    finally:
        set_num_f(ha, entity, prev)


# --- Simulation --------------------------------------------------------------------------------
def sim_tab(page):
    ready(page)
    tab(page, "SIMULATION")
    expect(tid(page, "sim-panel")).to_be_visible(timeout=10_000)
    expect(tid(page, "sim-panel")).to_contain_text("BENCH ONLY")


def drag(locator, value):
    """Move a range input like a user would: input events while dragging, one change at the end."""
    locator.evaluate("""(el, v) => {
        el.value = String(v - 1); el.dispatchEvent(new Event('input', {bubbles: true}));
        el.value = String(v); el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
    }""", value)


def test_sim_outdoor_slider_writes(page, ha):
    outdoor = eid(ha, "number", "sim_outdoor_f")
    weather = eid(ha, "select", "sim_weather")
    prev_outdoor, prev_weather = state(ha, outdoor), state(ha, weather)
    attrs = ha.get_state(outdoor)["attributes"]
    want = round(float(prev_outdoor)) + (7 if float(prev_outdoor) + 7 <= attrs["max"] else -7)
    try:
        ha.call("select", "select_option", {"entity_id": weather, "option": "Fixed"})
        sim_tab(page)
        slider = tid(page, "sim-outdoor")
        expect(slider).to_have_attribute("min", str(int(attrs["min"])))
        expect(slider).to_have_attribute("max", str(int(attrs["max"])))
        expect(slider).to_have_value(str(round(float(prev_outdoor))), timeout=10_000)
        since = datetime.now(timezone.utc)
        drag(slider, want)
        ha.wait_state(outdoor, lambda s: float(s["state"]) == want, timeout=10)
        expect(tid(page, "sim-outdoor-val")).to_have_text(f"{want}°F", timeout=5_000)
        # Only the final value was written (no write for the intermediate input event).
        time.sleep(1)
        values = [float(r["state"]) for r in history(ha, outdoor, since) if r["state"] not in ("unknown", "unavailable")]
        assert want - 1 not in values[1:], values
    finally:
        ha.call("number", "set_value", {"entity_id": outdoor, "value": float(prev_outdoor)})
        ha.call("select", "select_option", {"entity_id": weather, "option": prev_weather})


def test_sim_outdoor_now_shown(page, ha):
    """The panel and the room view show the outdoor the physics uses now (sim_outdoor_now_f):
    the Fixed setting, or the day curve, which the panel says the slider switches off."""
    outdoor = eid(ha, "number", "sim_outdoor_f")
    weather = eid(ha, "select", "sim_weather")
    now_f = eid(ha, "sensor", "sim_outdoor_now_f")
    prev_outdoor, prev_weather = state(ha, outdoor), state(ha, weather)

    def outdoor_now_f():  # the test HA runs metric: it shows this °F sensor in °C
        st = ha.get_state(now_f)
        if st["state"] in ("unknown", "unavailable"):
            return None
        return to_f(st["state"], st["attributes"].get("unit_of_measurement"))

    def shown_f():
        text = tid(page, "sim-outdoor-now").inner_text()
        return float(text[:-2]) if text.endswith("°F") else None

    try:
        ha.call("select", "select_option", {"entity_id": weather, "option": "Fixed"})
        ha.call("number", "set_value", {"entity_id": outdoor, "value": 50})
        wait_until(lambda: (v := outdoor_now_f()) is not None and abs(v - 50) < 0.06, 10, message="sim_outdoor_now_f 50")
        sim_tab(page)
        expect(tid(page, "sim-outdoor-now")).to_have_text("50.0°F", timeout=10_000)
        expect(tid(page, "sim-outdoor-note")).to_have_text("")
        expect(dash(page).locator('[data-testid="outdoor-num"]')).to_have_text("50°F", timeout=10_000)
        ha.call("select", "select_option", {"entity_id": weather, "option": "Winter day"})
        wait_until(lambda: (v := outdoor_now_f()) is not None and abs(v - 50) >= 0.06, 10, message="sim_outdoor_now_f off the Fixed value")
        want = outdoor_now_f()
        wait_until(lambda: (v := shown_f()) is not None and abs(v - want) <= 0.11, 10, message=f"outdoor now ≈ {want:.1f}°F")
        expect(tid(page, "sim-outdoor-note")).to_have_text("moving it switches the weather from winter day to fixed")
        expect(dash(page).locator('[data-testid="outdoor-num"]')).to_have_text(f"{round(want)}°F", timeout=10_000)
    finally:
        ha.call("number", "set_value", {"entity_id": outdoor, "value": float(prev_outdoor)})
        ha.call("select", "select_option", {"entity_id": weather, "option": prev_weather})


def test_sim_fault_select_writes(page, ha, sim):
    entity = eid(ha, "select", "sim_fault")
    try:
        sim_tab(page)
        sel = tid(page, "sim-fault")
        expect(sel).to_have_value("None", timeout=10_000)
        sel.select_option("Frozen")
        ha.wait_state(entity, lambda s: s["state"] == "Frozen", timeout=10)
        expect(sel).to_have_value("Frozen")
    finally:
        ha.call("select", "select_option", {"entity_id": entity, "option": "None"})
        if state(ha, eid(ha, "binary_sensor", "sensor_fault")) == "on":
            sim.stop()  # the fault needs 5 min of good readings to clear; a fresh sim starts clean
            sim.start(wait=True)


# --- Home level pills with the schedule off (Task 5 code, regression) --------------------------
def pump_until(page, predicate, timeout, message):
    """wait_until that keeps Playwright's event loop running: the sync API runs the websocket
    route handler (which forwards the page's messages to HA) only inside Playwright calls, so a
    plain time.sleep would hold every message the page sends."""
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, f"timed out after {timeout}s waiting for {message}"
        page.wait_for_timeout(250)


def ha_is(ha, entity_id, value):
    return lambda: state(ha, entity_id) == value


@pytest.fixture
def calls(context):
    """Every call_service the page sends over the websocket: [(domain, service, data)].
    While it is in use, wait with pump_until / page.wait_for_timeout, never time.sleep."""
    seen = []

    def route(ws):
        server = ws.connect_to_server()

        def from_page(message):
            try:
                data = json.loads(message)
            except (TypeError, ValueError):
                data = None
            if isinstance(data, dict) and data.get("type") == "call_service":
                seen.append((data.get("domain"), data.get("service"), data.get("service_data") or {}))
            server.send(message)

        ws.on_message(from_page)

    context.route_web_socket("**/api/websocket", route)
    return seen


@pytest.fixture
def schedule_off_heat(ha):
    """Heat mode, schedule turned on (clears a manual target) and then off; restored afterwards."""
    climate = ha.sim_climate()
    sw = eid(ha, "switch", "schedule_enabled")
    prev_mode = state(ha, climate)
    ha.call("climate", "set_hvac_mode", {"entity_id": climate, "hvac_mode": "heat"})
    set_switch(ha, sw, True)
    set_switch(ha, sw, False)
    ha.wait_state(eid(ha, "binary_sensor", "manual_target"), lambda s: s["state"] == "off")
    yield
    set_switch(ha, sw, True)
    ha.call("climate", "set_hvac_mode", {"entity_id": climate, "hvac_mode": prev_mode})


def test_lit_level_sends_when_manual(context, ha, request_log, calls, schedule_off_heat):
    manual = eid(ha, "binary_sensor", "manual_target")
    page = open_dashboard(context, ha, request_log)
    ready(page)
    tid(page, "minus").click()
    pump_until(page, ha_is(ha, manual, "on"), 10, "manual_target on")
    level = state(ha, eid(ha, "select", "comfort_level"))
    pill = tid(page, f"level-{level.lower()}")
    expect(pill).to_have_attribute("aria-pressed", "false", timeout=10_000)  # not lit while manual
    calls.clear()
    pill.click()
    pump_until(page, ha_is(ha, manual, "off"), 10, "manual_target off")
    assert ("select", "select_option") in [(d, s) for d, s, _ in calls], calls
    expect(pill).to_have_attribute("aria-pressed", "true", timeout=10_000)


def test_lit_level_noop_otherwise(context, ha, request_log, calls, schedule_off_heat):
    level_entity = eid(ha, "select", "comfort_level")
    before = ha.get_state(level_entity)
    page = open_dashboard(context, ha, request_log)
    ready(page)
    pill = tid(page, f"level-{before['state'].lower()}")
    expect(pill).to_have_attribute("aria-pressed", "true", timeout=10_000)
    calls.clear()
    pill.click()
    page.wait_for_timeout(2_500)
    assert not [c for c in calls if c[:2] == ("select", "select_option")], calls
    after = ha.get_state(level_entity)
    assert after["state"] == before["state"] and after["last_updated"] == before["last_updated"]
    assert state(ha, eid(ha, "binary_sensor", "manual_target")) == "off"
