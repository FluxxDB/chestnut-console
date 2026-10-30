"""The dashboard frame, tabs and the Home tab, against the host sim."""

import json
import re
import time
from datetime import datetime, timezone

import pytest
from playwright.sync_api import expect

from conftest import open_dashboard
from ha_client import HA_URL, SIM_DEVICE, wait_until


LIVE_TARGET = re.compile(r"^(\d+°|\d+–\d+°|OFF)$")


def dash(page):
    d = page.locator("chestnut-dashboard")
    expect(d).to_have_count(1, timeout=20_000)
    return d


def tid(page, name):
    return dash(page).locator(f'[data-testid="{name}"]')


def eid(ha, domain, object_id):
    e = ha.sim_entity(domain, object_id)
    assert e, f"no sim entity {domain}.*_{object_id}"
    return e


def ready(page):
    """Wait until the dashboard has resolved the sim and shows a live target."""
    expect(tid(page, "target")).to_have_text(LIVE_TARGET, timeout=20_000)


def set_schedule_on_no_hold(ha):
    sw = eid(ha, "switch", "schedule_enabled")
    if ha.get_state(sw)["state"] != "on":
        ha.call("switch", "turn_on", {"entity_id": sw})
    ha.call("button", "press", {"entity_id": eid(ha, "button", "resume_schedule")})
    ha.wait_state(eid(ha, "binary_sensor", "schedule_hold"), lambda s: s["state"] == "off")


# The test HA runs metric: HA shows the °F set_target in °C. Convert like the dashboard does.
def to_f(value, unit):
    v = float(value)
    return v * 9 / 5 + 32 if unit == "°C" else v


def from_f(f, unit):
    return (f - 32) * 5 / 9 if unit == "°C" else f


def unit_of(ha, entity_id):
    return ha.get_state(entity_id)["attributes"].get("unit_of_measurement")


def target_f(ha, entity_id):
    st = ha.get_state(entity_id)
    return round(to_f(st["state"], st["attributes"].get("unit_of_measurement")))


def set_target_f(ha, entity_id, f):
    ha.call("number", "set_value", {"entity_id": entity_id, "value": from_f(f, unit_of(ha, entity_id))})


def history(ha, entity_id, since):
    rows = ha.get(f"/api/history/period/{since.isoformat()}?filter_entity_id={entity_id}"
                  "&minimal_response&no_attributes")
    return rows[0] if rows else []


def test_tabs_on_desktop(page):
    for tab in ("HOME", "SCHEDULE", "SIMULATION", "SYSTEM"):
        expect(dash(page).locator(f'[data-tab="{tab}"]')).to_be_visible(timeout=20_000)
    expect(tid(page, "room")).to_be_visible()
    dash(page).locator('[data-tab="SYSTEM"]').click()
    expect(tid(page, "room")).to_be_hidden()
    expect(tid(page, "runtime")).to_be_hidden()
    dash(page).locator('[data-tab="SIMULATION"]').click()
    expect(tid(page, "room")).to_be_visible()
    dash(page).locator('[data-tab="HOME"]').click()
    expect(tid(page, "runtime")).to_be_visible()


def test_five_taps_one_write(page, ha):
    climate = ha.sim_climate()
    ha.call("climate", "set_hvac_mode", {"entity_id": climate, "hvac_mode": "heat"})
    set_schedule_on_no_hold(ha)
    st = eid(ha, "number", "set_target")
    unit = unit_of(ha, st)
    start = target_f(ha, st)
    if start > 84:  # keep start + 5 inside 50–90
        set_target_f(ha, st, 80)
        wait_until(lambda: target_f(ha, st) == 80, 10, message="set_target 80")
        start = 80
    ready(page)
    expect(tid(page, "target")).to_have_text(f"{start}°", timeout=15_000)

    since = datetime.now(timezone.utc)
    plus = tid(page, "plus")
    for _ in range(5):
        plus.click()
    # The pending value shows at once.
    expect(tid(page, "target")).to_have_text(f"{start + 5}°", timeout=1_000)
    # Nothing is written during the 1.5 s debounce.
    assert target_f(ha, st) == start
    time.sleep(2)
    assert target_f(ha, st) == start + 5

    # Exactly one state change: the recorder holds the start state and then only start + 5.
    def recorded():
        rows = history(ha, st, since)
        return rows if rows and round(to_f(rows[-1]["state"], unit)) == start + 5 else None
    wait_until(recorded, 15, message="the recorder to hold the write")
    time.sleep(2)
    values = [round(to_f(r["state"], unit)) for r in history(ha, st, since)]
    changes = [b for a, b in zip(values, values[1:]) if a != b]
    assert changes == [start + 5], values
    expect(tid(page, "resume")).to_be_visible(timeout=10_000)  # a temperature hold started


def test_mode_heat_sets_climate(page, ha):
    climate = ha.sim_climate()
    ha.call("climate", "set_hvac_mode", {"entity_id": climate, "hvac_mode": "off"})
    ha.wait_state(climate, lambda s: s["state"] == "off")
    ready(page)
    expect(tid(page, "mode-off")).to_have_attribute("aria-pressed", "true", timeout=10_000)
    tid(page, "mode-heat").click()
    ha.wait_state(climate, lambda s: s["state"] == "heat", timeout=10)
    expect(tid(page, "mode-heat")).to_have_attribute("aria-pressed", "true", timeout=10_000)
    expect(tid(page, "mode-off")).to_have_attribute("aria-pressed", "false")
    tid(page, "fan-on").click()
    ha.wait_state(climate, lambda s: s["attributes"].get("fan_mode") == "on", timeout=10)
    tid(page, "fan-auto").click()
    ha.wait_state(climate, lambda s: s["attributes"].get("fan_mode") == "auto", timeout=10)


def test_resume_only_when_hold(page, ha):
    set_schedule_on_no_hold(ha)
    ready(page)
    expect(tid(page, "resume")).to_be_hidden(timeout=10_000)

    st = eid(ha, "number", "set_target")
    cur = target_f(ha, st)
    set_target_f(ha, st, cur - 2 if cur > 60 else cur + 2)
    hold = eid(ha, "binary_sensor", "schedule_hold")
    ha.wait_state(hold, lambda s: s["state"] == "on")
    expect(tid(page, "resume")).to_be_visible(timeout=10_000)
    expect(tid(page, "resume")).to_have_text("Resume schedule →")

    tid(page, "resume").click()
    ha.wait_state(hold, lambda s: s["state"] == "off", timeout=10)
    expect(tid(page, "resume")).to_be_hidden(timeout=10_000)


def test_phone_hides_sim_tab_and_room(browser, ha, request_log):
    context = browser.new_context(base_url=HA_URL, viewport={"width": 390, "height": 844})
    try:
        page = open_dashboard(context, ha, request_log)
        ready(page)
        expect(dash(page).locator('[data-tab="HOME"]')).to_be_visible()
        expect(dash(page).locator('[data-tab="SYSTEM"]')).to_be_visible()
        expect(dash(page).locator('[data-tab="SIMULATION"]')).to_be_hidden()
        expect(tid(page, "room")).to_be_hidden()
        expect(tid(page, "target")).to_be_visible()
        # Nothing wider than the phone (no horizontal scroll inside the dashboard).
        overflow = dash(page).evaluate("el => el.shadowRoot.querySelector('.page').scrollWidth - el.clientWidth")
        assert overflow <= 0, overflow
    finally:
        context.close()


def test_empty_history_renders(context, ha, request_log):
    """A fresh HA's recorder has nothing for these entities: the websocket answers history with {}."""
    asked = []

    def route(ws):
        server = ws.connect_to_server()

        def from_page(message):
            try:
                data = json.loads(message)
            except (TypeError, ValueError):
                data = None
            if isinstance(data, dict) and data.get("type") == "history/history_during_period":
                asked.append(data)
                ws.send(json.dumps({"id": data["id"], "type": "result", "success": True, "result": {}}))
            else:
                server.send(message)

        ws.on_message(from_page)

    context.route_web_socket("**/api/websocket", route)
    page = open_dashboard(context, ha, request_log)
    ready(page)
    expect(tid(page, "runtime")).to_contain_text("no data yet", timeout=15_000)
    assert asked, "the dashboard never asked for history"
    # The rest of the page still works.
    expect(tid(page, "status-word")).not_to_have_text("", timeout=10_000)
    expect(tid(page, "today")).to_be_visible()


def test_runtime_shows_history(page):
    """The chart is drawn from the recorder (the sim has run for minutes by now): shown, with a
    room line; not "loading…" or "no data yet" (the 360 bars are in the template either way)."""
    ready(page)
    runtime = tid(page, "runtime")
    expect(runtime).to_contain_text("LAST 12 HOURS", timeout=15_000)
    expect(dash(page).locator("#rt-chart")).to_be_visible(timeout=20_000)
    expect(dash(page).locator("#rt-empty")).to_be_hidden()
    expect(dash(page).locator("#pl-room")).to_have_attribute("points", re.compile(r"\d+(\.\d+)?,\d"), timeout=20_000)
    expect(runtime.locator("[data-bar]")).to_have_count(360)


@pytest.fixture
def mode_restored(ha):
    climate = ha.sim_climate()
    prev = ha.get_state(climate)["state"]
    yield climate
    ha.call("climate", "set_hvac_mode", {"entity_id": climate, "hvac_mode": prev})


def test_minus_plus_do_nothing_in_off(page, ha, mode_restored):
    """As on the wall screen: in Off, − / + are disabled and write nothing (a write would start a
    hold, or set the manual target, that nobody sees until the mode changes)."""
    climate = mode_restored
    st = eid(ha, "number", "set_target")
    ha.call("climate", "set_hvac_mode", {"entity_id": climate, "hvac_mode": "off"})
    ha.wait_state(climate, lambda s: s["state"] == "off")
    ready(page)
    expect(tid(page, "target")).to_have_text("OFF", timeout=10_000)
    expect(tid(page, "plus")).to_be_disabled()
    expect(tid(page, "minus")).to_be_disabled()
    before = ha.get_state(st)["state"]
    dash(page).evaluate("el => { el._step(1); el._step(1); }")  # the handler itself ignores Off too
    time.sleep(2.5)  # past the 1.5 s debounce
    assert ha.get_state(st)["state"] == before
    expect(tid(page, "target")).to_have_text("OFF")
    ha.call("climate", "set_hvac_mode", {"entity_id": climate, "hvac_mode": "heat"})
    expect(tid(page, "plus")).to_be_enabled(timeout=10_000)


def test_write_dropped_when_thermostat_drops_mid_burst(page, ha, mode_restored):
    """The thermostat goes offline during the 1.5 s pause: the burst isn't sent (HA would drop it
    silently), and when it's back the card shows its real target, not the tapped one."""
    climate = mode_restored
    ha.call("climate", "set_hvac_mode", {"entity_id": climate, "hvac_mode": "heat"})
    ha.wait_state(climate, lambda s: s["state"] == "heat")
    st = eid(ha, "number", "set_target")
    ready(page)
    expect(tid(page, "plus")).to_be_enabled(timeout=10_000)
    shown = tid(page, "target").inner_text()
    before = ha.get_state(st)["state"]
    tid(page, "plus").click()
    dash(page).evaluate("el => { el._adapter.online = () => false; }")  # offline, as the page sees it
    time.sleep(2.5)
    assert ha.get_state(st)["state"] == before, "a write went out while the thermostat was offline"
    dash(page).evaluate("el => { delete el._adapter.online; }")         # back online
    expect(tid(page, "target")).to_have_text(shown, timeout=5_000)


def test_narrowing_on_simulation_goes_home(page):
    """Shrinking to phone width on SIMULATION (rotation, split view) can't leave a page with no
    tab selected: it goes back to HOME."""
    ready(page)
    dash(page).locator('[data-tab="SIMULATION"]').click()
    expect(dash(page).locator('[data-tab="SIMULATION"]')).to_have_attribute("aria-selected", "true")
    page.set_viewport_size({"width": 800, "height": 900})
    expect(dash(page).locator('[data-tab="HOME"]')).to_have_attribute("aria-selected", "true", timeout=5_000)
    expect(tid(page, "target")).to_be_visible()


def test_missing_device_says_not_found(page):
    """A device_name HA doesn't have (a typo, a renamed device) says so, not "offline"."""
    ready(page)
    dash(page).evaluate("el => el.setConfig({ device_name: 'No Such Thermostat' })")
    expect(tid(page, "status-word")).to_have_text("NOT FOUND", timeout=10_000)
    expect(tid(page, "status-sub")).to_contain_text('No device named "No Such Thermostat"')
    dash(page).evaluate("(el, name) => el.setConfig({ device_name: name })", SIM_DEVICE)
    ready(page)
    expect(tid(page, "status-word")).not_to_have_text("NOT FOUND")


def counters(page):
    return dash(page).evaluate("el => ({loops: el._loops, intervals: el._intervals, "
                               "resolves: el._resolves, histories: el._historyLoads})")


def test_reconnect_rebinds_once(context, ha, request_log):
    sockets = []

    def route(ws):  # pass-through; keeps a handle so the test can drop the connection
        ws.connect_to_server()
        sockets.append(ws)

    context.route_web_socket("**/api/websocket", route)
    page = open_dashboard(context, ha, request_log)
    ready(page)
    before = counters(page)
    assert before["loops"] == 1 and before["intervals"] == 1, before

    # Drop HA's websocket from the server side, as a network blip would. The frontend reconnects;
    # HA then rebuilds the view (a new element) and may reload the page. Sample the live timers
    # (all instances in the window) the whole time: never more than one loop / one interval.
    sockets[-1].close()
    samples = []
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            samples.append(counters(page))
        except Exception:  # noqa: BLE001 - the page may be mid-reload
            pass
        time.sleep(0.25)
    assert len(sockets) >= 2, "the frontend never reconnected"
    assert samples and all(s["loops"] <= 1 and s["intervals"] <= 1 for s in samples), samples
    ready(page)
    wait_until(lambda: counters(page)["histories"] >= 1, 20, message="history to load again")
    after = counters(page)
    assert after["loops"] == 1 and after["intervals"] == 1, after
    expect(tid(page, "runtime")).not_to_contain_text("loading", timeout=10_000)

    # Detach and re-attach the element (HA re-rendering the view, or a backgrounded tab):
    # timers stop while detached and come back exactly once, with a fresh entity lookup.
    detached = dash(page).evaluate("""el => {
        const parent = el.parentNode, next = el.nextSibling, resolves = el._resolves;
        parent.removeChild(el);
        const off = {loops: el._loops, intervals: el._intervals};
        parent.insertBefore(el, next);
        return {...off, resolved_again: el._resolves > resolves};
    }""")
    assert detached == {"loops": 0, "intervals": 0, "resolved_again": True}, detached
    time.sleep(1)
    again = counters(page)
    assert again["loops"] == 1 and again["intervals"] == 1, again
    ready(page)


def test_offline_shows_dashes(page, sim):
    ready(page)
    sim.stop()
    expect(tid(page, "status-word")).to_have_text("OFFLINE", timeout=30_000)
    expect(tid(page, "target")).to_have_text("—")
    expect(tid(page, "status-card")).to_contain_text("—")
    expect(tid(page, "mode-heat")).to_be_disabled()
    expect(tid(page, "resume")).to_be_hidden()
    sim.start(wait=True)
    ready(page)


@pytest.fixture
def sim_fault(ha, sim):
    entity = eid(ha, "select", "sim_fault")
    yield entity
    ha.call("select", "select_option", {"entity_id": entity, "option": "None"})
    # The sanity checker needs 5 min of good readings to clear; a fresh sim program starts clean.
    sim.stop()
    sim.start(wait=True)


def test_status_paused_on_sensor_fault(page, ha, sim_fault):
    ready(page)
    expect(tid(page, "status-word")).not_to_have_text("PAUSED", timeout=10_000)
    # "Out of range" (a 60 °C reading) faults at once. "Unplugged" only faults once the reading is
    # stale (2 min on the sim), which would test the sim's clock, not the dashboard.
    ha.call("select", "select_option", {"entity_id": sim_fault, "option": "Out of range"})
    expect(tid(page, "status-word")).to_have_text("PAUSED", timeout=10_000)
    expect(tid(page, "status-card")).to_contain_text("⚠", timeout=10_000)


def heat_hold_start(ha, hi=84):
    """Heat mode, schedule on with no hold; returns (set_target entity, its °F, rounded), kept <= hi."""
    climate = ha.sim_climate()
    ha.call("climate", "set_hvac_mode", {"entity_id": climate, "hvac_mode": "heat"})
    set_schedule_on_no_hold(ha)
    st = eid(ha, "number", "set_target")
    start = target_f(ha, st)
    if start > hi:
        set_target_f(ha, st, 80)
        wait_until(lambda: target_f(ha, st) == 80, 10, message="set_target 80")
        start = 80
    return st, start


def test_second_burst_before_confirm_is_written(context, ha, request_log):
    """+2 is written; -2 tapped before the device's effective_target confirms the 2 must be
    written too (back to the start), not compared against the stale device value and dropped.
    The page never hears effective_target change (filtered from HA's websocket), which holds
    the window open as long as the test needs."""
    st, start = heat_hold_start(ha)
    eff_id = eid(ha, "sensor", "effective_target")

    def strip(node):
        if isinstance(node, list):
            for n in node:
                strip(n)
        elif isinstance(node, dict):
            ev = node.get("event")
            if isinstance(ev, dict) and isinstance(ev.get("c"), dict):
                ev["c"].pop(eff_id, None)

    def route(ws):
        server = ws.connect_to_server()

        def from_server(message):
            try:
                data = json.loads(message)
            except (TypeError, ValueError):
                ws.send(message)
                return
            strip(data)
            ws.send(json.dumps(data))

        server.on_message(from_server)

    context.route_web_socket("**/api/websocket", route)
    page = open_dashboard(context, ha, request_log)
    ready(page)
    expect(tid(page, "target")).to_have_text(f"{start}°", timeout=15_000)
    # The filter runs in this (sync Playwright) thread: wait with page.wait_for_timeout, which
    # keeps forwarding HA's messages, never with time.sleep.
    def wait_target(f, message):
        deadline = time.monotonic() + 6
        while target_f(ha, st) != f:
            assert time.monotonic() < deadline, f"timed out waiting for {message}"
            page.wait_for_timeout(250)

    plus, minus = tid(page, "plus"), tid(page, "minus")
    plus.click()
    plus.click()
    wait_target(start + 2, f"set_target {start + 2}")
    minus.click()
    minus.click()
    expect(tid(page, "target")).to_have_text(f"{start}°", timeout=1_000)
    wait_target(start, f"set_target back to {start}")


def test_detach_mid_burst_still_writes(page, ha):
    """A tap still in its 1.5 s debounce when the element detaches (HA rebuilding the view on a
    reconnect) is sent, not silently dropped."""
    st, start = heat_hold_start(ha)
    ready(page)
    expect(tid(page, "target")).to_have_text(f"{start}°", timeout=15_000)
    tid(page, "plus").click()
    dash(page).evaluate("el => el.remove()")
    wait_until(lambda: target_f(ha, st) == start + 1, 6, message=f"set_target {start + 1} after detach")
