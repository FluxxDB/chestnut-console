"""The room view (<chestnut-room-view>) on Home and Simulation, against the host sim."""

import re
import time

import pytest
from playwright.sync_api import expect

from ha_client import wait_until
from test_home import dash, eid, ready, set_target_f, tid, to_f


def room(page):
    return tid(page, "room")


def rtid(page, name):
    return room(page).locator(f'[data-testid="{name}"]')


def frames(page):
    return room(page).evaluate("el => el._frames")


def room_loops(page):
    return room(page).evaluate("el => el._loops")


def test_room_mean_matches_sensor(page, ha):
    ready(page)
    sensor = eid(ha, "sensor", "checked_temperature")
    seen = {}

    def close():
        st = ha.get_state(sensor)
        f = to_f(st["state"], st["attributes"].get("unit_of_measurement"))
        mean = room(page).get_attribute("data-mean")
        seen.update(sensor=f, mean=mean)
        return mean not in (None, "") and abs(float(mean) - f) <= 0.05

    wait_until(close, 20, message=f"the room's field mean to match checked_temperature {seen}")


@pytest.fixture
def heat_forced(ha):
    """Heat mode, a high target and a cold outdoor (sim at 20°F, Fixed); restored afterwards."""
    climate = ha.sim_climate()
    outdoor = eid(ha, "number", "sim_outdoor_f")
    weather = eid(ha, "select", "sim_weather")
    set_target = eid(ha, "number", "set_target")
    prev_outdoor = ha.get_state(outdoor)["state"]
    prev_weather = ha.get_state(weather)["state"]
    ha.call("select", "select_option", {"entity_id": weather, "option": "Fixed"})
    ha.call("number", "set_value", {"entity_id": outdoor, "value": 20})
    ha.call("climate", "set_hvac_mode", {"entity_id": climate, "hvac_mode": "heat"})
    set_target_f(ha, set_target, 85)
    yield
    ha.call("climate", "set_hvac_mode", {"entity_id": climate, "hvac_mode": "off"})
    ha.call("number", "set_value", {"entity_id": outdoor, "value": float(prev_outdoor)})
    ha.call("select", "select_option", {"entity_id": weather, "option": prev_weather})
    ha.call("button", "press", {"entity_id": eid(ha, "button", "resume_schedule")})


def test_furnace_lit_when_call_heat(page, ha, heat_forced):
    ready(page)
    call_heat = eid(ha, "binary_sensor", "call_heat")
    # After a sim boot the furnace waits out its minimum off time (3 min) first.
    ha.wait_state(call_heat, lambda s: s["state"] == "on", timeout=300)
    expect(rtid(page, "furnace")).to_have_attribute("data-on", "1", timeout=10_000)
    expect(rtid(page, "ac")).to_have_attribute("data-on", "0")
    expect(rtid(page, "blower")).to_have_attribute("data-on", "1")
    expect(rtid(page, "furnace")).to_contain_text("firing")
    readouts = rtid(page, "readouts")
    expect(readouts).to_contain_text("airflow on")
    assert "supply" not in readouts.inner_text().lower()


def test_sim_tag_present(page):
    ready(page)
    expect(rtid(page, "room-head")).to_contain_text("SIM", timeout=10_000)
    expect(rtid(page, "outdoor")).to_contain_text("SIM")
    expect(rtid(page, "outdoor-num")).to_have_text(re.compile(r"^-?\d+°F$"), timeout=10_000)


def test_offline_shows_dashes(page, sim):
    ready(page)
    expect(rtid(page, "room-num")).not_to_have_text("—", timeout=10_000)
    sim.stop()
    expect(rtid(page, "room-num")).to_have_text("—", timeout=70_000)
    expect(rtid(page, "readouts")).to_contain_text("room avg —")
    expect(rtid(page, "furnace")).to_have_attribute("data-on", "0")
    # Offline is not "sim gone": the SIMULATION tab stays.
    expect(dash(page).locator('[data-tab="SIMULATION"]')).to_be_visible()
    sim.start(wait=True)
    ready(page)


def test_paused_when_tab_hidden(page):
    ready(page)
    expect(room(page)).to_be_visible()
    wait_until(lambda: room_loops(page) == 1, 10, message="the room loop to run")
    a = frames(page)
    time.sleep(0.5)
    assert frames(page) > a, "the room loop is not running on HOME"

    dash(page).locator('[data-tab="SCHEDULE"]').click()
    expect(room(page)).to_be_hidden()
    time.sleep(0.3)
    a = frames(page)
    time.sleep(1)
    assert frames(page) == a, "requestAnimationFrame kept running with the room hidden"
    assert room_loops(page) == 0

    dash(page).locator('[data-tab="HOME"]').click()
    wait_until(lambda: frames(page) > a, 5, message="the room loop to resume")
    assert room_loops(page) == 1

    # A backgrounded page (visibilitychange → hidden) pauses it too.
    page.evaluate("""() => {
        Object.defineProperty(document, 'hidden', {value: true, configurable: true});
        Object.defineProperty(document, 'visibilityState', {value: 'hidden', configurable: true});
        document.dispatchEvent(new Event('visibilitychange'));
    }""")
    time.sleep(0.3)
    a = frames(page)
    time.sleep(1)
    assert frames(page) == a, "requestAnimationFrame kept running in a hidden page"
    assert room_loops(page) == 0
    page.evaluate("""() => {
        delete document.hidden;
        delete document.visibilityState;
        document.dispatchEvent(new Event('visibilitychange'));
    }""")
    wait_until(lambda: frames(page) > a, 5, message="the room loop to resume when visible")
    assert room_loops(page) == 1
