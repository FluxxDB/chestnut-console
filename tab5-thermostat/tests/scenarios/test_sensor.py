"""Sensor sanity in the loop (thermostat/logic.yaml, spec Safety 4), sensor_fault,
call_wait_reason and action_elapsed.

The thermostat acts on checked_temperature_c, which the SanityChecker feeds from
room_temperature. The test build scales the production thresholds by timer_unit_s = 1:
stale 2 s, frozen 30 s, recovery after 5 s of good readings (2-40 °C, spike 2 °C unchanged).
The sim publishes every 250 ms, so a fault cleared by readings lands about 5.25 s after the
first good one. On a fault the thermostat asks for OFF: no new call starts, a running call
still finishes its minimum run (Dang's Q3), and on recovery the minimum off times still apply.
Timers: furnace minimum run / off 3 s, AC 5 s. Time assertions keep EDGE_SLACK_S for the API's
state batching.
"""
import math

from test_core import (COOL_OFF_S, COOL_RUN_S, EDGE_SLACK_S, HEAT_OFF_S, HEAT_RUN_S, cool_to,
                       fixed_weather, heat_to, is_off, is_on, now)

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
    started = now()
    await device.select("sim_fault", "Out of range")
    await device.wait_for("sensor_fault", is_on, 1)
    await device.wait_for("call_heat", is_off, HEAT_RUN_S + 2)
    ran = now() - started
    assert ran >= HEAT_RUN_S - EDGE_SLACK_S, f"furnace cut after {ran:.2f}s, before its minimum run"
    assert ran <= HEAT_RUN_S + 2, f"furnace ran {ran:.2f}s on a faulted sensor"
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
    """Cooling past its minimum run, then an Out of range fault stops it. Returns the time
    call_cool was seen off (t0), right after which the sensor is healthy again."""
    await fixed_weather(dev, 100)
    await cool_to(dev, 60)
    await dev.wait_for("call_cool", is_on, COOL_OFF_S + 5)
    await dev.sleep(COOL_RUN_S + 0.5)  # past the AC's minimum run: the fault stops it at once
    await dev.select("sim_fault", "Out of range")
    await dev.wait_for("sensor_fault", is_on, 1)
    await dev.wait_for("call_cool", is_off, 1.5)
    t0 = now()
    await dev.select("sim_fault", "None")
    return t0


async def test_recovery_respects_cool_min_off(device):
    t0 = await cooling_stopped_by_fault(device)
    await device.wait_for("call_cool", is_on, 10)
    off_for = now() - t0
    assert off_for >= COOL_OFF_S - EDGE_SLACK_S, f"AC restarted after only {off_for:.2f}s off"
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
    t0 = await cooling_stopped_by_fault(device)
    await device.wait_for("sensor_fault", is_off, RECOVER_S + 2)
    recovered = now() - t0
    assert recovered < 9 - 1, f"recovery at {recovered:.2f}s doesn't separate the two waits"
    assert await device.state("call_cool") is False
    await device.wait_for("call_cool", is_on, t0 + 9 + 3 - now())
    off_for = now() - t0
    assert off_for >= 9 - EDGE_SLACK_S, f"AC restarted after {off_for:.2f}s with a 9 s minimum off"


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
    assert now() - boot >= STARTUP_S - EDGE_SLACK_S
    await device.wait_for("call_wait_reason", lambda v: v == "", 1.5)
