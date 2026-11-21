"""Relay fault (milestone 4; thermostat/logic.yaml, the relay hold): when the relay unit stops
answering (relay_fault on), the logic cuts W and Y at once, ignoring minimum run times, and G
too unless the fan mode is On. No heat or cool call goes through until the fault has cleared AND
the larger minimum off time has passed since the fault began. Then the thermostat re-runs its
action by itself. The mode is never touched.

The sim raises relay_fault with Sim Fault "Relay unit unplugged"; the test hook
test_set_relay_fault raises it on its own, so it can be on together with a sensor fault (the
real hardware cuts Port A's power on a lasting relay fault, which drops the sensor too).
Timers are the test build's: furnace minimum run / off 3 s, AC 5 s, so the hold lasts 5 s from
the fault. Times are measured on the device: test_relay_fault_ms is the moment the logic saw
the fault (g_relay_fault_ms), and the relay edges come from the test_*_ms sensors.
"""
from aioesphomeapi import ClimateAction, ClimateMode

from conftest import f_to_c
from test_core import (COOL_OFF_S, HEAT_OFF_S, assert_near, cool_to, fixed_weather, heat_to,
                       is_off, is_on)
from test_interlock import action_of, mode_of

HOLD_S = max(HEAT_OFF_S, COOL_OFF_S)  # the hold lasts this long from the fault's start
RECOVER_S = 5  # the sensor's recovery: 5 "minutes" of good readings


def reason_is(text):
    return lambda v: v == text


async def fault_on(dev):
    """Sim Fault "Relay unit unplugged"; returns when the logic saw it (ms since boot)."""
    before = max(dev.device_times("test_relay_fault_ms"), default=-1)
    await dev.select("sim_fault", "Relay unit unplugged")
    return await dev.wait_device_time("test_relay_fault_ms", before, 1)


async def fault_off(dev):
    await dev.select("sim_fault", "None")
    await dev.wait_for("relay_fault", is_off, 1)


async def heating(dev):
    await fixed_weather(dev, 0)
    await heat_to(dev, 80)
    await dev.wait_for("call_heat", is_on, HEAT_OFF_S + 5)


async def cooling(dev, fan_mode="AUTO"):
    await fixed_weather(dev, 100)
    await dev.climate(mode="COOL", fan_mode=fan_mode)
    await cool_to(dev, 60)
    await dev.wait_for("call_cool", is_on, COOL_OFF_S + 5)
    await dev.wait_for("call_fan", is_on, 1)


async def test_relay_fault_cuts_heat_at_once(device):
    await heating(device)
    fault_ms = await fault_on(device)
    w_off = await device.edge("call_heat", False, fault_ms - 1, 1)
    assert w_off - fault_ms < 300, f"W dropped {w_off - fault_ms} ms after the fault"
    await device.wait_for("call_wait_reason", reason_is("Relay fault"), 1.5)
    assert await mode_of(device) == ClimateMode.HEAT


async def test_relay_fault_cuts_cool_and_fan(device):
    await cooling(device)
    fault_ms = await fault_on(device)
    assert await device.edge("call_cool", False, fault_ms - 1, 1) - fault_ms < 300
    assert await device.edge("call_fan", False, fault_ms - 1, 1) - fault_ms < 300


async def test_relay_fault_keeps_g_with_fan_on(device):
    await cooling(device, fan_mode="ON")
    n = device.updates("call_fan")
    await fault_on(device)
    await device.wait_for("call_cool", is_off, 1)
    await device.sleep(1.5)
    assert await device.state("call_fan") is True  # Fan On is the user's standing choice
    assert False not in device.history("call_fan")[n:]


async def test_no_call_during_fault(device):
    await fault_on(device)  # during the startup delay
    await fixed_weather(device, 0)
    await heat_to(device, 80)
    await device.sleep(HOLD_S + 3)
    assert True not in device.history("call_heat"), "a heat call went through during a relay fault"
    assert await device.state("call_wait_reason") == "Relay fault"


async def test_short_fault_holds_min_off_from_fault(device):
    await heating(device)
    fault_ms = await fault_on(device)
    await device.sleep(1)
    await fault_off(device)
    # The fault is gone but the hold isn't: the minimum off counts from the fault.
    await device.wait_for("call_wait_reason", reason_is("Short-cycle protection"), 1.5)
    w_on = await device.edge("call_heat", True, fault_ms, HOLD_S + 2)
    assert_near(w_on - fault_ms, HOLD_S, "W back after the fault began", late_ms=250)
    await device.wait_for("call_wait_reason", reason_is(""), 1.5)


async def test_long_fault_resumes_when_it_clears(device):
    await heating(device)
    fault_ms = await fault_on(device)
    await device.sleep(HOLD_S + 2)
    assert await device.state("call_heat") is False
    await fault_off(device)
    w_on = await device.edge("call_heat", True, fault_ms, 1.5)
    assert w_on - fault_ms >= (HOLD_S + 2) * 1000 - 300


async def test_call_resumes_after_fault_clears(device):
    await heating(device)
    await fault_on(device)
    await device.sleep(HOLD_S + 1)
    assert await device.state("call_heat") is False
    # The thermostat never ran its action again: it still believes it is heating.
    assert await action_of(device) == ClimateAction.HEATING, "stale-action path not exercised"
    await fault_off(device)
    await device.wait_for("call_heat", is_on, 2)
    assert await mode_of(device) == ClimateMode.HEAT


async def sensor_faulted_while_heating(dev):
    await heating(dev)
    await dev.select("sim_fault", "Unplugged")
    await dev.wait_for("sensor_fault", is_on, 4)
    await dev.wait_for("call_wait_reason", reason_is("Sensor fault"), 1.5)


async def test_relay_beats_sensor_in_wait_reason(device):
    await sensor_faulted_while_heating(device)
    await device.action("test_set_relay_fault", active=True)
    await device.wait_for("call_wait_reason", reason_is("Relay fault"), 1.5)
    await device.wait_for("call_heat", is_off, 1)


async def test_relay_clears_while_sensor_faulted(device):
    await sensor_faulted_while_heating(device)
    await device.action("test_set_relay_fault", active=True)
    await device.wait_for("call_heat", is_off, 1)
    await device.action("test_set_relay_fault", active=False)
    n = len(device.edges("call_heat", True))
    await device.sleep(HOLD_S + 1)
    # The hold is over but the sensor still isn't: no call, and the sensor is why.
    assert await device.state("call_wait_reason") == "Sensor fault"
    assert len(device.edges("call_heat", True)) == n, "heat came back on a faulted sensor"
    await device.select("sim_fault", "None")
    await device.wait_for("sensor_fault", is_off, RECOVER_S + 3)
    await device.wait_for("call_heat", is_on, 3)


async def test_interlock_beats_relay_in_wait_reason(device):
    await fault_on(device)
    await device.wait_for("call_wait_reason", reason_is("Relay fault"), 1.5)
    await device.action("test_force_relays", heat=True, cool=True)
    await device.wait_for("interlock_fault", is_on, 1)
    await device.wait_for("call_wait_reason", reason_is("Interlock fault"), 1.5)


# --- The relay hold overlapping the interlock latch, and the fan mode during a hold ---

async def test_latch_cleared_during_hold_waits_for_hold(device):
    """Interlock latched, then a relay fault: Clear drops the latch, but heat waits for the hold."""
    await heating(device)
    await device.action("test_force_relays", heat=True, cool=True)  # latch
    await device.wait_for("interlock_fault", is_on, 1)
    fault_ms = await fault_on(device)
    await device.press("clear_interlock_fault")
    await device.wait_for("interlock_fault", is_off, HOLD_S + 2)
    await device.sleep(1)
    assert await device.state("call_heat") is False, "heat came back during the relay hold"
    await fault_off(device)
    w_on = await device.edge("call_heat", True, fault_ms, HOLD_S + 3)
    assert w_on - fault_ms >= HOLD_S * 1000 - 150
    assert await mode_of(device) == ClimateMode.HEAT


async def test_hold_ends_during_latch_waits_for_clear(device):
    """A relay fault, then the interlock latches: the hold's end doesn't resume; Clear does."""
    await heating(device)
    await fault_on(device)
    await device.action("test_force_relays", heat=True, cool=True)  # latch
    await device.wait_for("interlock_fault", is_on, 1)
    await fault_off(device)
    n = len(device.edges("call_heat", True))
    await device.sleep(HOLD_S + 1)  # the hold is over; the latch isn't
    assert len(device.edges("call_heat", True)) == n, "heat came back while latched"
    await device.press("clear_interlock_fault")
    await device.wait_for("interlock_fault", is_off, 2)
    await device.wait_for("call_heat", is_on, 3)


async def test_fan_on_to_auto_during_hold_drops_g(device):
    await cooling(device, fan_mode="ON")
    await fault_on(device)
    await device.wait_for("call_cool", is_off, 1)
    assert await device.state("call_fan") is True
    await device.climate(fan_mode="AUTO")
    await device.wait_for("call_fan", is_off, 1)
