"""Sensor sanity in the loop (thermostat/logic.yaml, spec Safety 4), sensor_fault,
call_wait_reason and action_elapsed.

The thermostat acts on checked_temperature_c, which the SanityChecker feeds from
room_temperature. The test build scales the production thresholds by timer_unit_s = 1:
stale 2 s without an accepted reading, frozen 30 s, recovery after 5 s of good readings
(-10..50 °C, i.e. 14-122°F, and the 2 °C spike limit unchanged).
The sim publishes every 250 ms, so a fault cleared by readings lands about 5.25 s after the
first good one. On a fault the thermostat asks for OFF: no new call starts, a running call
still finishes its minimum run (Dang's Q3), and on recovery the minimum off times still apply.
Timers: furnace minimum run / off 3 s, AC 5 s. Durations are measured on the device (relay
edge timestamps, conftest's Dev.edge).
"""
import math

from test_core import (COOL_OFF_S, COOL_RUN_S, HEAT_OFF_S, HEAT_RUN_S, TOL_MS, assert_near,
                       cool_to, fixed_weather, heat_to, is_off, is_on, now, run_ms)

RECOVER_S = 5  # 5 "minutes" of good readings
FROZEN_S = 30  # 30 "minutes" of an identical value
STARTUP_S = max(HEAT_OFF_S, COOL_OFF_S)  # "Starting up" lasts the larger minimum off time


def is_nan(v):
    return v is None or (isinstance(v, float) and math.isnan(v))


async def healthy(dev):
    """Wait until the checked temperature is a number and there is no sensor fault."""
    await dev.wait_for("checked_temperature", lambda v: not is_nan(v), 3)
    assert await dev.wait_for("sensor_fault", lambda v: v is not None, 3) is False


async def test_unplugged_faults_and_stops_new_calls(device):
    await fixed_weather(device, 68)  # the room starts at 68°F and stays there
    await heat_to(device, 68)
    await healthy(device)
    await device.sleep(HEAT_OFF_S + 1)  # past the startup delay, idle at target
    assert True not in device.history("call_heat")
    await device.select("sim_fault", "Unplugged")
    await fixed_weather(device, 0)  # the room cools fast: heat would be wanted
    await device.wait_for("sensor_fault", is_on, 3)
    assert is_nan(await device.state("checked_temperature"))
    await device.sleep(6)
    assert await device.state("sim_room_f") < 66, "room didn't cool: heat was never wanted"
    assert True not in device.history("call_heat"), "a heat call started during a sensor fault"
    assert await device.state("sensor_fault") is True


async def test_fault_mid_run_finishes_min_run(device):
    await fixed_weather(device, 0)
    await heat_to(device, 80)
    await device.wait_for("call_heat", is_on, HEAT_OFF_S + 5)
    await device.select("sim_fault", "Out of range")
    await device.wait_for("sensor_fault", is_on, 1)
    # Neither cut early nor kept running on the faulted sensor: off when the minimum run ends.
    on, off = await run_ms(device, "call_heat", HEAT_RUN_S + 2)
    assert_near(off - on, HEAT_RUN_S, "furnace run under a sensor fault")
    n = device.updates("call_heat")
    await device.sleep(HEAT_OFF_S + 1)  # past its minimum off: still no call while faulted
    assert True not in device.history("call_heat")[n:]


async def test_frozen_faults(device):
    await fixed_weather(device, 68)
    await healthy(device)
    t0 = now()
    await device.select("sim_fault", "Frozen")
    await device.wait_for("sensor_fault", is_on, FROZEN_S + 2)
    held = now() - t0
    # The identical value started at most one reading (250 ms) before the select.
    assert held >= FROZEN_S - 1, f"frozen fault after only {held:.2f}s"
    assert is_nan(await device.state("checked_temperature"))


async def test_spike_does_not_fault(device):
    await fixed_weather(device, 68)
    await healthy(device)
    n = device.updates("checked_temperature")
    await device.select("sim_fault", "Spike")  # one reading 10 °C (18°F) high
    await device.wait_for("sim_fault", lambda v: v == "None", 2)
    await device.sleep(3)
    assert True not in device.history("sensor_fault")
    room_f = await device.state("sim_room_f")
    seen = device.history("checked_temperature")[n:]
    assert seen, "no checked readings after the spike"
    assert not [v for v in seen if is_nan(v)], seen
    assert max(abs(v - room_f) for v in seen) < 2, f"spike got through: {seen} vs room {room_f:.1f}"


async def test_recovery_after_5_units(device):
    await fixed_weather(device, 68)
    await healthy(device)
    await device.select("sim_fault", "Out of range")
    await device.wait_for("sensor_fault", is_on, 1)
    await device.sleep(1)
    await device.select("sim_fault", "None")
    t = now()
    await device.sleep(RECOVER_S - 1)
    assert await device.state("sensor_fault") is True, "cleared before 5 s of good readings"
    assert is_nan(await device.state("checked_temperature"))
    await device.wait_for("sensor_fault", is_off, t + RECOVER_S + 2 - now())
    room_f = await device.state("sim_room_f")
    checked = await device.wait_for("checked_temperature", lambda v: not is_nan(v), 1)
    assert abs(checked - room_f) < 1, (checked, room_f)


async def cooling_stopped_by_fault(dev):
    """Cooling past its minimum run, then an Out of range fault stops it. Returns the device time
    (ms since boot) Y went off; right after it is seen off, the sensor is healthy again."""
    await fixed_weather(dev, 100)
    await cool_to(dev, 60)
    await dev.wait_for("call_cool", is_on, COOL_OFF_S + 5)
    await dev.sleep(COOL_RUN_S + 0.5)  # past the AC's minimum run: the fault stops it at once
    await dev.select("sim_fault", "Out of range")
    await dev.wait_for("sensor_fault", is_on, 1)
    await dev.wait_for("call_cool", is_off, 1.5)
    await dev.select("sim_fault", "None")
    return (await run_ms(dev, "call_cool", 2))[1]


async def test_recovery_respects_cool_min_off(device):
    off = await cooling_stopped_by_fault(device)
    on = await device.edge("call_cool", True, off, 10)
    # The recovery (5 s of good readings) and the AC's 5 s minimum off end close together: at
    # least the minimum off, whichever is later.
    assert on - off >= COOL_OFF_S * 1000 - TOL_MS, f"AC restarted after only {(on - off) / 1000:.2f}s off"
    assert await device.state("sensor_fault") is False


async def test_wait_reason_values(device):
    boot = device.started_at
    await heat_to(device, 80)  # the room (68°F) is off target, held by the startup delay
    await fixed_weather(device, 0)
    await device.wait_for("call_wait_reason", lambda v: v == "Starting up", 2)
    assert now() - boot < HEAT_OFF_S - 0.3, "too late to see the startup delay"
    await device.wait_for("call_heat", is_on, boot + HEAT_OFF_S + 3 - now())
    await device.wait_for("call_wait_reason", lambda v: v == "", 1.5)
    await device.select("sim_fault", "Out of range")
    await device.wait_for("call_wait_reason", lambda v: v == "Sensor fault", 1.5)


async def test_action_elapsed_resets(device):
    # Outdoor 68: once idle, the room settles back to 68, far above the 50 that ends the call,
    # so the action stays IDLE until the periodic publish.
    await fixed_weather(device, 68)
    await heat_to(device, 80)
    await device.wait_for("call_heat", is_on, HEAT_OFF_S + 5)
    await device.sleep(0.5)
    # Published at once when heating began.
    assert await device.state("action_elapsed") < 1.5
    await device.sleep(HEAT_RUN_S)
    n = device.updates("action_elapsed")
    await heat_to(device, 50)  # no longer wanted: IDLE now, the minimum run has passed
    await device.wait_for("call_heat", is_off, 2)
    idle_at = now()
    await device.wait_for("action_elapsed",
                          lambda v: device.updates("action_elapsed") > n and v < 1.5, 1.5)
    # Then the periodic publish (every 30 s): seconds since IDLE began, not a timestamp.
    v = await device.wait_for("action_elapsed", lambda v: v >= 5, 31)
    assert abs(v - (now() - idle_at)) < 2, (v, now() - idle_at)


# Beyond the brief's eight: a bad reading that would itself start a call, a longer AC minimum
# off that outlasts the recovery, and the two remaining wait reasons.

async def test_out_of_range_reading_never_starts_cooling(device):
    # Without the checker, the thermostat would read 60 °C and start cooling.
    await fixed_weather(device, 68)
    await cool_to(device, 72)
    await healthy(device)
    await device.sleep(COOL_OFF_S + 1)  # past the startup delay, idle below target
    await device.select("sim_fault", "Out of range")
    await device.wait_for("sensor_fault", is_on, 1)
    await device.sleep(3)
    assert True not in device.history("call_cool")
    assert True not in device.history("call_fan")


async def test_recovery_waits_out_longer_cool_min_off(device):
    assert await device.set_number("cool_min_off", 9) == 9
    off = await cooling_stopped_by_fault(device)
    t0 = now()
    await device.wait_for("sensor_fault", is_off, RECOVER_S + 2)
    recovered = now() - t0
    assert recovered < 9 - 1, f"recovery at {recovered:.2f}s doesn't separate the two waits"
    assert await device.state("call_cool") is False
    on = await device.edge("call_cool", True, off, 9 + 3)
    assert_near(on - off, 9, "AC off time with a 9 s minimum off")


async def test_wait_reason_short_cycle_and_interlock(device):
    await fixed_weather(device, 0)
    await heat_to(device, 80)
    await device.wait_for("call_heat", is_on, HEAT_OFF_S + 5)
    await heat_to(device, 50)
    await device.wait_for("call_heat", is_off, HEAT_RUN_S + 2)
    await heat_to(device, 80)  # wanted again at once: the furnace's minimum off holds it
    await device.wait_for("call_wait_reason", lambda v: v == "Short-cycle protection", 1.5)
    await device.wait_for("call_heat", is_on, HEAT_OFF_S + 2)
    await device.wait_for("call_wait_reason", lambda v: v == "", 1.5)
    await device.action("test_force_relays", heat=True, cool=True)
    await device.wait_for("interlock_fault", is_on, 1)
    await device.wait_for("call_wait_reason", lambda v: v == "Interlock fault", 1.5)


async def test_wait_reason_starting_up_lasts_the_longer_min_off(device):
    boot = device.started_at
    await cool_to(device, 60)  # the room (68°F) is off target; the AC waits 5 s after boot
    await fixed_weather(device, 100)
    await device.wait_for("call_wait_reason", lambda v: v == "Starting up", 2)
    await device.sleep(boot + HEAT_OFF_S + 1 - now())  # past the furnace's 3 s
    assert await device.state("call_wait_reason") == "Starting up"
    await device.wait_for("call_cool", is_on, boot + STARTUP_S + 3 - now())
    assert_near(await device.edge("call_cool", True), STARTUP_S, "call_cool after boot")
    await device.wait_for("call_wait_reason", lambda v: v == "", 1.5)


async def test_freezing_house_is_still_heated(device):
    # Ruling R19: a house left cold (below the old 2 °C / 35.6°F limit) reads as a real
    # temperature, so heating starts and brings it back. A leaky 1 h house at 20°F outdoor gets
    # there in a few seconds.
    await device.set_number("sim_tau_h", 1)
    await fixed_weather(device, 20)
    await device.wait_for("sim_room_f", lambda v: v < 32, 20)
    await device.sleep(1)  # a few readings at freezing
    assert True not in device.history("sensor_fault"), "a freezing room counted as a bad reading"
    checked = await device.state("checked_temperature")
    assert not is_nan(checked) and checked < 34, checked
    await heat_to(device, 68)
    await device.wait_for("call_heat", is_on, HEAT_OFF_S + 3)
    assert await device.state("sensor_fault") is False


async def test_unplugged_makes_humidity_unknown(device):
    # Spec, Safety 4: humidity faults only make humidity unknown (the screen shows "—"). With no
    # humidity reading for 2 "minutes" (2 s here), room_humidity and the climate's humidity
    # become unknown; heating and cooling never depend on it.
    await device.wait_for("room_humidity", lambda v: not is_nan(v), 3)
    await device.select("sim_fault", "Unplugged")
    t0 = now()
    await device.wait_for("room_humidity", is_nan, 4)
    assert now() - t0 >= 1.5, f"humidity unknown after only {now() - t0:.2f}s"
    st = await device.wait_for("main_thermostat", lambda v: math.isnan(v.current_humidity), 2)
    assert math.isnan(st.current_humidity)
    await device.select("sim_fault", "None")
    h = await device.wait_for("room_humidity", lambda v: not is_nan(v), 2)
    assert 40 < h < 50, h  # sim_humidity 45 ± noise
