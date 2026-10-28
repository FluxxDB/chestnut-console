"""Interlock watchdog (thermostat/logic.yaml, spec Safety 3): if W and Y are ever both on, the
watchdog cuts both at once (ignoring minimum run times), latches `interlock_fault`, and while
latched no heat or cool call goes through. The Clear button never touches the climate mode: it
waits out the larger minimum off time since the trip, drops the latch, and makes the thermostat
re-run its action.

The test hook `test_force_relays` switches the relays directly, which is the only way to reach
the both-on state: the logic's own actions always turn the opposite relay off first.
Timers are the test build's: furnace minimum run / off 3 s, AC 5 s, so Clear waits 5 s from the
trip. Time assertions keep EDGE_SLACK_S for the API's state batching.
"""
from aioesphomeapi import ClimateAction, ClimateMode

from conftest import f_to_c

from test_core import (COOL_OFF_S, EDGE_SLACK_S, HEAT_OFF_S, cool_to, fixed_weather,
                       heat_to, is_off, is_on, now)

CLEAR_WAIT_S = max(HEAT_OFF_S, COOL_OFF_S)  # Clear holds the latch this long after the trip


async def trip(dev):
    """Both relays on, then wait for the watchdog to latch the fault. Returns the time just
    before the relays were forced (the real trip is never earlier)."""
    t0 = now()
    await dev.action("test_force_relays", heat=True, cool=True)
    await dev.wait_for("interlock_fault", is_on, 1)
    await dev.wait_for("call_heat", is_off, 1)
    await dev.wait_for("call_cool", is_off, 1)
    return t0


async def mode_of(dev):
    return (await dev.state("main_thermostat")).mode


async def action_of(dev):
    return (await dev.state("main_thermostat")).action


async def test_both_relays_trip_watchdog(device):
    assert await device.wait_for("interlock_fault", lambda v: v is not None, 3) is False
    await device.action("test_force_relays", heat=True, cool=True)
    await device.wait_for("interlock_fault", is_on, 1)
    assert await device.wait_for("call_heat", is_off, 1) is False
    assert await device.wait_for("call_cool", is_off, 1) is False
    await device.sleep(1)
    assert await device.state("interlock_fault") is True
    assert await device.state("call_heat") is False
    assert await device.state("call_cool") is False
    assert "interlock" in device.log_tail(200).lower()


async def test_latched_blocks_calls(device):
    await trip(device)
    await fixed_weather(device, 0)
    n = device.updates("call_heat")
    nc = device.updates("call_cool")
    await heat_to(device, 73)  # room starts at 68°F: 5°F below target
    # Past the startup delay: the thermostat itself now wants (and believes it runs) heat.
    await device.sleep(8)
    assert await action_of(device) == ClimateAction.HEATING, "stale-action path not exercised"
    assert True not in device.history("call_heat")[n:], "heat call went through while latched"
    assert True not in device.history("call_cool")[nc:]
    assert await device.state("interlock_fault") is True


async def test_forced_relay_while_latched_is_cut_again(device):
    await trip(device)
    # Something switches W on again while latched (no action involved): cut on the next tick.
    await device.action("test_force_relays", heat=True, cool=False)
    await device.wait_for("call_heat", is_off, 1)
    await device.sleep(0.5)
    assert await device.state("call_heat") is False
    assert await device.state("interlock_fault") is True


async def test_clear_restores(device):
    await trip(device)
    await fixed_weather(device, 0)
    nc = device.updates("call_cool")
    await heat_to(device, 73)
    # Let the thermostat reach HEATING (relays stay off), so its own state has to be reset.
    await device.sleep(CLEAR_WAIT_S + 2)
    assert await device.state("call_heat") is False
    assert await action_of(device) == ClimateAction.HEATING, "stale-action path not exercised"
    await device.press("clear_interlock_fault")
    await device.wait_for("interlock_fault", is_off, 2)
    await device.wait_for("call_heat", is_on, 8)
    assert await mode_of(device) == ClimateMode.HEAT  # the mode was never touched
    assert True not in device.history("call_cool")[nc:]
    assert await device.state("interlock_fault") is False


async def test_clear_waits_out_min_off_since_trip(device):
    t0 = await trip(device)
    await fixed_weather(device, 0)
    await heat_to(device, 73)
    await device.press("clear_interlock_fault")  # right after the trip
    await device.sleep(1.5)
    assert now() - t0 < CLEAR_WAIT_S - 1, "test setup too slow"
    # Nothing changes until the larger minimum off time (cool, 5 s) has passed since the trip.
    assert await device.state("interlock_fault") is True
    assert await device.state("call_heat") is False
    await device.wait_for("interlock_fault", is_off, CLEAR_WAIT_S + 2 - (now() - t0))
    held = now() - t0
    assert held >= CLEAR_WAIT_S - EDGE_SLACK_S, f"latch cleared {held:.2f}s after the trip"
    await device.wait_for("call_heat", is_on, 8)
    assert await mode_of(device) == ClimateMode.HEAT


async def test_clear_during_wait_is_harmless_when_pressed_twice(device):
    t0 = await trip(device)
    await device.press("clear_interlock_fault")
    await device.press("clear_interlock_fault")
    await device.wait_for("interlock_fault", is_off, CLEAR_WAIT_S + 2)
    assert now() - t0 >= CLEAR_WAIT_S - EDGE_SLACK_S


async def test_retrip_during_wait_restarts_wait(device):
    t0 = await trip(device)
    await device.press("clear_interlock_fault")
    await device.sleep(2)
    t1 = now()
    await device.action("test_force_relays", heat=True, cool=True)  # trips again, still waiting
    await device.wait_for("call_heat", is_off, 1)
    await device.wait_for("interlock_fault", is_off, CLEAR_WAIT_S + 3)
    assert now() - t1 >= CLEAR_WAIT_S - EDGE_SLACK_S, "wait was not restarted by the second trip"


async def test_mode_change_during_wait_off_is_honoured(device):
    await trip(device)
    await fixed_weather(device, 0)
    nh = device.updates("call_heat")
    await heat_to(device, 73)
    await device.press("clear_interlock_fault")
    await device.climate(mode="OFF")  # the user changes their mind while Clear is waiting
    await device.wait_for("interlock_fault", is_off, CLEAR_WAIT_S + 2)
    await device.sleep(HEAT_OFF_S + 2)
    assert await mode_of(device) == ClimateMode.OFF  # never forced back to Heat
    assert True not in device.history("call_heat")[nh:]


async def test_mode_change_during_wait_heat_again_is_not_stuck(device):
    await trip(device)
    await fixed_weather(device, 0)
    await heat_to(device, 73)
    await device.press("clear_interlock_fault")
    await device.climate(mode="OFF")
    await device.sleep(0.5)
    await device.climate(mode="HEAT")  # Heat again while the stale action is still around
    await device.wait_for("interlock_fault", is_off, CLEAR_WAIT_S + 2)
    await device.wait_for("call_heat", is_on, 8)
    assert await mode_of(device) == ClimateMode.HEAT


async def test_trip_during_cooling_cuts_g_and_clear_resumes(device):
    await fixed_weather(device, 100)
    await cool_to(device, 60)
    await device.wait_for("call_cool", is_on, COOL_OFF_S + 5)
    await device.wait_for("call_fan", is_on, 1)
    await device.action("test_force_relays", heat=True, cool=True)
    await device.wait_for("interlock_fault", is_on, 1)
    await device.wait_for("call_heat", is_off, 1)
    await device.wait_for("call_cool", is_off, 1)
    await device.wait_for("call_fan", is_off, 1)  # fan Auto: no blower left running
    await device.sleep(CLEAR_WAIT_S + 1)
    assert await device.state("call_cool") is False and await device.state("call_fan") is False
    assert await action_of(device) == ClimateAction.COOLING, "stale-action path not exercised"
    await device.press("clear_interlock_fault")
    await device.wait_for("interlock_fault", is_off, 2)
    await device.wait_for("call_cool", is_on, 8)
    await device.wait_for("call_fan", is_on, 2)
    assert await mode_of(device) == ClimateMode.COOL


async def test_trip_with_fan_on_keeps_g(device):
    await fixed_weather(device, 100)
    await device.climate(mode="COOL", fan_mode="ON", target_temperature_low=f_to_c(58),
                         target_temperature_high=f_to_c(60))
    await device.wait_for("call_cool", is_on, COOL_OFF_S + 5)
    await device.action("test_force_relays", heat=True, cool=True)
    await device.wait_for("interlock_fault", is_on, 1)
    await device.wait_for("call_cool", is_off, 1)
    n = device.updates("call_fan")
    await device.sleep(1.5)
    assert await device.state("call_fan") is True  # Fan On is the user's choice
    assert False not in device.history("call_fan")[n:]


async def test_reboot_after_clear_keeps_mode(device_keep_prefs):
    dev = device_keep_prefs
    await fixed_weather(dev, 0)
    await heat_to(dev, 73)
    await trip(dev)
    await dev.press("clear_interlock_fault")  # still waiting when the device restarts
    await dev.sleep(1)
    await dev.restart()
    st = await dev.wait_for("main_thermostat", lambda v: v is not None, 3)
    assert st.mode == ClimateMode.HEAT, "the user's mode must survive a restart during Clear"
    assert await dev.wait_for("interlock_fault", lambda v: v is not None, 3) is False


async def test_normal_heat_to_cool_handover_is_not_a_false_trip(device):
    await fixed_weather(device, 0)
    await heat_to(device, 80)
    await device.wait_for("call_heat", is_on, HEAT_OFF_S + 5)
    # Change of mind: now cooling is wanted. The furnace stops, then the AC starts.
    await cool_to(device, 60)
    await device.wait_for("call_cool", is_on, 15)
    assert await device.state("call_heat") is False
    assert await device.state("interlock_fault") is False
    assert True not in device.history("interlock_fault")


async def test_clear_when_healthy_is_harmless(device):
    await fixed_weather(device, 100)
    await cool_to(device, 60)
    await device.wait_for("call_cool", is_on, COOL_OFF_S + 5)
    await device.press("clear_interlock_fault")
    await device.sleep(1)
    assert await device.state("call_cool") is True
    assert await device.state("interlock_fault") is False
    assert await mode_of(device) == ClimateMode.COOL
