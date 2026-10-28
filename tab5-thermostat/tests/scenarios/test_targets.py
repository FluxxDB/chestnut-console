"""Single target, Comfort / Eco, holds, Auto and HA writes (thermostat/logic.yaml, spec "Single
target, Comfort, Eco and holds" and Safety 2's Auto changeover lockout).

The climate's low / high setpoints are always derived (chestnut::derive_setpoints) from the
mode, comfort_target, eco_offset, comfort_level and a hold. Two kinds of hold (rulings R12,
R13), both shown as schedule_hold: switching comfort_level by hand is a level hold (the level
applies normally, Eco widening included); set_target and setpoint writes to the climate (HA, the
API) are a temperature hold (no Eco widening), which any mode change ends. Defaults: comfort 72°F, Eco
offset 4, Comfort, mode Off. The thermostat's deadband and overrun are 0.5 °C (0.9°F), so a
heat target of 68 starts heating at 67.1 and a cool target of 76 starts cooling at 76.9.

Physics: one 1 s step = 10 simulated minutes. With the default 8 h house the room moves about
2% of the gap to outdoor per step; a 1 h house (sim_tau_h) moves it about 15%, which the tests
use to bring the room into a band quickly. Timers: furnace 3 / 3 s, AC 5 / 5 s, min idle 1 s,
changeover lockout 30 "minutes" = 30 s.
"""
from aioesphomeapi import ClimateAction, ClimateMode

from conftest import f_to_c
from test_core import (COOL_OFF_S, COOL_RUN_S, EDGE_SLACK_S, HEAT_OFF_S, HEAT_RUN_S, cool_to,
                       fixed_weather, heat_to, is_off, is_on, now)
from test_schedule import expected_now

LOCKOUT_S = 30  # changeover_lockout default, 30 x timer_unit_s
DEADBAND_F = 0.9  # 0.5 °C
C_TOL = 0.1  # °C, for climate setpoints read back over the API


async def climate(dev):
    return await dev.wait_for("main_thermostat", lambda v: v is not None, 3)


async def ready(dev):
    """Wait for boot's apply_setpoints (effective_target published)."""
    await dev.wait_for("effective_target", lambda v: v is not None, 3)


async def setpoints_f(dev, low, high, timeout_s=2):
    """Wait until the climate's low / high read back as these °F values."""
    def ok(st):
        return (abs(st.target_temperature_low - f_to_c(low)) < C_TOL
                and abs(st.target_temperature_high - f_to_c(high)) < C_TOL)
    return await dev.wait_for("main_thermostat", ok, timeout_s)


async def effective(dev, target, low=None, high=None, timeout_s=2):
    await dev.wait_for("effective_target", lambda v: v == target, timeout_s)
    if low is not None:
        await dev.wait_for("effective_low", lambda v: v == low, timeout_s)
    if high is not None:
        await dev.wait_for("effective_high", lambda v: v == high, timeout_s)


async def room_near(dev, outdoor_f, at_least_f):
    """Bring the room up into a band fast (a leaky 1 h house), then back to the normal 8 h."""
    await dev.set_number("sim_tau_h", 1)
    await fixed_weather(dev, outdoor_f)
    await dev.wait_for("sim_room_f", lambda v: v >= at_least_f, 15)
    await dev.set_number("sim_tau_h", 8)


async def reading_when_on(dev, call):
    """Wait for the call to come on; the checked room temperature (°F) it came on at."""
    await dev.wait_for(call, is_on, 30)
    return await dev.state("checked_temperature")


def actions_before(dev, call, action):
    """Every climate state reporting `action` that arrived before `call` came on, allowing
    0.25 s: the climate publishes in the dispatch that turns the relay on, the call sensor on
    the next loop, so the two can arrive a batch apart in either order. Covers the whole wait."""
    on_at = next(t for t, v in dev.timed_history(call) if v is True)
    return [(round(on_at - t, 2), st.action) for t, st in dev.timed_history("main_thermostat")
            if st is not None and st.action == action and t < on_at - 0.25]


# --- Eco and Auto bands ---

async def test_eco_heat_band(device):
    await ready(device)
    await fixed_weather(device, 68)  # the room starts at 68 and stays there
    await device.climate(mode="HEAT")
    await device.select("comfort_level", "Eco")
    await effective(device, 68)
    await setpoints_f(device, 68, 70)
    assert await device.state("comfort_target") == 72
    # Past the startup delay at 68: Comfort (72) would heat now, Eco (68) doesn't.
    await device.sleep(HEAT_OFF_S + 1)
    assert True not in device.history("call_heat")
    await fixed_weather(device, 60)  # the room drifts down about 0.17°F a step
    at = await reading_when_on(device, "call_heat")
    assert 66.3 < at <= 68 - DEADBAND_F + 0.05, f"heating started at {at:.2f}°F"


async def test_eco_cool_band(device):
    await ready(device)
    await fixed_weather(device, 100)
    await device.climate(mode="COOL")
    await device.select("comfort_level", "Eco")
    await effective(device, 76)
    await setpoints_f(device, 74, 76)
    at = await reading_when_on(device, "call_cool")
    assert 76 + DEADBAND_F - 0.05 <= at < 78, f"cooling started at {at:.2f}°F"
    assert True not in device.history("call_heat")


async def test_auto_single_target(device):
    await ready(device)
    await room_near(device, 74, 71.5)  # inside the 71-73 band
    await fixed_weather(device, 60)
    await device.climate(mode="HEAT_COOL")
    await effective(device, 72, 71, 73)
    await setpoints_f(device, 71, 73)
    assert (await climate(device)).mode == ClimateMode.HEAT_COOL
    assert await device.state("schedule_hold") is False
    at = await reading_when_on(device, "call_heat")
    assert 69.5 < at <= 71 - DEADBAND_F + 0.05, f"heating started at {at:.2f}°F"
    assert True not in device.history("call_cool")


async def test_auto_cools_above(device):
    await ready(device)
    await room_near(device, 74, 71.5)
    await fixed_weather(device, 85)
    await device.climate(mode="HEAT_COOL")
    await effective(device, 72, 71, 73)
    at = await reading_when_on(device, "call_cool")
    assert 73 + DEADBAND_F - 0.05 <= at < 75, f"cooling started at {at:.2f}°F"
    assert True not in device.history("call_heat")


async def test_auto_eco_band(device):
    # Eco pressed in Auto: a level hold, and Eco widens the band by the offset on both sides.
    await ready(device)
    await device.climate(mode="HEAT_COOL")
    await device.select("comfort_level", "Eco")
    await device.wait_for("schedule_hold", is_on, 2)
    await effective(device, 72, 67, 77)
    await setpoints_f(device, 67, 77)
    assert (await climate(device)).mode == ClimateMode.HEAT_COOL


async def test_holds_do_not_survive_restart(device_keep_prefs):
    dev = device_keep_prefs
    await ready(dev)
    await dev.climate(mode="HEAT_COOL")
    await dev.select("comfort_level", "Eco")
    assert await dev.set_number("set_target", 70) == 70
    await effective(dev, 70, 69, 71)
    before = expected_now()
    await dev.restart()
    await ready(dev)
    period = await dev.wait_for("schedule_period", lambda v: v, 3)
    after = expected_now()
    assert period in (before[0], after[0]), f"real clock gives {before} / {after}"
    eco = before[1] if period == before[0] else after[1]
    # No hold: the schedule re-applies the real clock's period at boot.
    assert await dev.wait_for("schedule_hold", lambda v: v is not None, 3) is False
    assert await dev.wait_for("comfort_level", lambda v: v is not None, 3) == ("Eco" if eco else "Comfort")
    low, high = (67, 77) if eco else (71, 73)
    await effective(dev, 72, low, high)
    await setpoints_f(dev, low, high)


async def test_eco_offset_and_comfort_target_apply_without_hold(device):
    await ready(device)
    await device.climate(mode="HEAT")
    await effective(device, 72)
    assert await device.set_number("comfort_target", 70) == 70
    await effective(device, 70)
    await setpoints_f(device, 70, 72)
    await device.climate(mode="COOL")
    assert await device.set_number("eco_offset", 6) == 6
    await effective(device, 70)  # Comfort: the offset doesn't matter
    await setpoints_f(device, 68, 70)
    assert True not in device.history("schedule_hold")


# --- Holds ---

async def test_set_target_starts_hold_comfort_untouched(device):
    # The spec's example: in Eco at 68°, + gives a hold at 69°.
    await ready(device)
    await device.climate(mode="HEAT")
    await device.select("comfort_level", "Eco")
    await effective(device, 68)
    assert await device.set_number("set_target", 69) == 69
    await device.wait_for("schedule_hold", is_on, 2)
    await effective(device, 69)
    await setpoints_f(device, 69, 71)
    assert await device.state("comfort_target") == 72
    assert await device.state("eco_offset") == 4
    assert await device.state("comfort_level") == "Eco"


async def test_temperature_hold_in_auto_eco_has_no_widening(device):
    await ready(device)
    await device.climate(mode="HEAT_COOL")
    await device.select("comfort_level", "Eco")
    await effective(device, 72, 67, 77)
    assert await device.set_number("set_target", 73) == 73  # first tap from the Comfort target
    await effective(device, 73, 72, 74)
    await setpoints_f(device, 72, 74)


async def test_set_target_in_comfort_is_a_hold_too(device):
    await ready(device)
    await device.climate(mode="COOL")
    await effective(device, 72)
    assert await device.set_number("set_target", 74) == 74
    await device.wait_for("schedule_hold", is_on, 2)
    await effective(device, 74)
    await setpoints_f(device, 72, 74)
    assert await device.state("comfort_target") == 72


async def test_same_value_no_hold(device):
    await ready(device)
    await device.climate(mode="HEAT")
    await effective(device, 72)
    assert await device.wait_for("comfort_level", lambda v: v is not None, 3) == "Comfort"
    assert await device.set_number("set_target", 72) == 72  # the current effective target
    await device.select("comfort_level", "Comfort")  # re-tapping the lit pill
    await device.sleep(1)
    assert True not in device.history("schedule_hold")
    assert await device.state("effective_target") == 72


async def test_level_switch_starts_hold(device):
    await ready(device)
    await device.climate(mode="HEAT")
    await device.select("comfort_level", "Eco")
    await device.wait_for("schedule_hold", is_on, 2)
    await effective(device, 68)
    assert await device.state("set_target") == 68  # set_target follows the effective target


async def test_eco_level_hold_follows_mode(device):
    # A level hold holds Eco, not 68: switching Heat -> Cool cools to comfort + offset.
    await ready(device)
    await device.climate(mode="HEAT")
    await device.select("comfort_level", "Eco")
    await effective(device, 68)
    await device.climate(mode="COOL")
    await effective(device, 76)
    await setpoints_f(device, 74, 76)
    assert await device.state("schedule_hold") is True  # the level hold stays


async def test_level_switch_ends_temperature_hold(device):
    await ready(device)
    await device.climate(mode="HEAT")
    assert await device.set_number("set_target", 75) == 75
    await effective(device, 75)
    await device.select("comfort_level", "Eco")
    await effective(device, 68)  # Eco's own target, not the held 75
    assert await device.state("schedule_hold") is True


async def test_mode_change_ends_temperature_hold(device):
    await ready(device)
    await device.climate(mode="HEAT")
    assert await device.set_number("set_target", 75) == 75
    await device.wait_for("schedule_hold", is_on, 2)
    await device.climate(mode="COOL")
    await device.wait_for("schedule_hold", is_off, 2)
    await effective(device, 72)  # back to Comfort
    await setpoints_f(device, 70, 72)


async def test_mode_change_keeps_level_hold_under_temperature_hold(device):
    await ready(device)
    await device.climate(mode="HEAT")
    await device.select("comfort_level", "Eco")
    assert await device.set_number("set_target", 70) == 70
    await effective(device, 70)
    await device.climate(mode="COOL")
    await effective(device, 76)  # the temperature hold ended; Eco (held) applies
    assert await device.state("schedule_hold") is True


async def test_mode_change_is_not_a_hold_and_rederives(device):
    await ready(device)
    await device.climate(mode="HEAT")
    await setpoints_f(device, 72, 74)
    await device.climate(mode="COOL")
    await setpoints_f(device, 70, 72)
    await device.climate(mode="HEAT_COOL")
    await setpoints_f(device, 71, 73)
    await effective(device, 72, 71, 73)
    assert True not in device.history("schedule_hold")


# --- HA / API writes to the climate ---

async def test_ha_setpoint_write_becomes_hold(device):
    await ready(device)
    await device.climate(mode="HEAT")
    await device.climate(target_temperature_low=f_to_c(70))
    await device.wait_for("set_target", lambda v: v == 70, 2)
    await device.wait_for("schedule_hold", is_on, 2)
    await effective(device, 70)
    st = await setpoints_f(device, 70, 72)
    assert abs(st.target_temperature_low - f_to_c(70)) < C_TOL
    assert await device.state("comfort_target") == 72


async def test_ha_single_target_write_in_cool(device):
    await ready(device)
    await device.climate(mode="COOL")
    await device.climate(target_temperature=f_to_c(75))
    await device.wait_for("set_target", lambda v: v == 75, 2)
    await device.wait_for("schedule_hold", is_on, 2)
    await setpoints_f(device, 73, 75)


async def test_ha_auto_range_write_uses_midpoint(device):
    await ready(device)
    await device.climate(mode="HEAT_COOL")
    await setpoints_f(device, 71, 73)
    # HA's range slider: the high end dragged from 73 to 77 -> centre 74, band 73-75.
    await device.climate(target_temperature_low=f_to_c(71), target_temperature_high=f_to_c(77))
    await device.wait_for("set_target", lambda v: v == 74, 2)
    await effective(device, 74, 73, 75)
    await setpoints_f(device, 73, 75)


async def test_ha_mode_and_target_in_one_call(device):
    # The mode change ends the old temperature hold first; the call's own target starts a new one.
    await ready(device)
    await device.climate(mode="HEAT")
    assert await device.set_number("set_target", 70) == 70
    await device.climate(mode="COOL", target_temperature_high=f_to_c(76))
    await device.wait_for("schedule_hold", is_on, 2)
    await effective(device, 76)
    st = await setpoints_f(device, 74, 76)
    assert st.mode == ClimateMode.COOL


async def test_ha_write_out_of_range_is_clamped(device):
    await ready(device)
    await device.climate(mode="HEAT")
    await device.climate(target_temperature_low=f_to_c(45))
    await device.wait_for("set_target", lambda v: v == 50, 2)
    await setpoints_f(device, 50, 52)


async def test_preset_call_does_not_switch_off(device):
    # Ruling R8: the stock thermostat's "Default" preset (mode Off) stays configured but is
    # stripped from outside calls; Comfort / Eco replace named presets.
    await ready(device)
    await device.climate(mode="HEAT")
    await device.wait_for("main_thermostat", lambda v: v.mode == ClimateMode.HEAT, 2)
    await device.climate(custom_preset="Default")
    await device.sleep(1)
    st = await climate(device)
    assert st.mode == ClimateMode.HEAT
    assert ClimateMode.OFF not in [s.mode for s in device.history("main_thermostat")[-5:]]
    await setpoints_f(device, 72, 74)


# --- Auto changeover lockout, mode changes mid-run ---

async def auto_heat_then_cool_wanted(dev):
    """Auto with a warm day: heats the 68°F room after the startup delay, then the furnace's
    minimum run carries the room past the band's top, so cooling is wanted the moment heat ends.
    Returns when call_heat goes off."""
    await ready(dev)
    await fixed_weather(dev, 90)  # about +0.45°F a step: still below 70.1 when heat may start
    await dev.climate(mode="HEAT_COOL")
    await dev.wait_for("call_heat", is_on, HEAT_OFF_S + 3)
    await dev.wait_for("call_heat", is_off, HEAT_RUN_S + 3)
    # The room keeps rising toward 90: cooling is wanted now or within a step or two.
    await dev.wait_for("checked_temperature", lambda v: v > 73 + DEADBAND_F + 0.1, 3)


async def test_auto_changeover_lockout(device):
    await auto_heat_then_cool_wanted(device)
    heat_off = now()
    await device.wait_for("call_wait_reason", lambda v: v == "Changeover wait", 3)
    await device.wait_for("call_cool", is_on, LOCKOUT_S + 5)
    waited = now() - heat_off
    assert waited >= LOCKOUT_S - EDGE_SLACK_S, f"AC started {waited:.2f}s after heat ended"
    assert waited <= LOCKOUT_S + 3, f"AC started {waited:.2f}s after heat ended: late"
    # The reported action matches the relays: never COOLING while Y was off, over the whole wait.
    assert actions_before(device, "call_cool", ClimateAction.COOLING) == []
    st = await device.wait_for("main_thermostat", lambda v: v.action == ClimateAction.COOLING, 1)
    assert st.mode == ClimateMode.HEAT_COOL
    await device.wait_for("call_wait_reason", lambda v: v == "", 1.5)
    assert await device.state("call_heat") is False


async def test_auto_changeover_lockout_after_cooling(device):
    await ready(device)
    await fixed_weather(device, 50)
    await device.climate(mode="HEAT_COOL")
    assert await device.set_number("set_target", 60) == 60  # band 59-61: the 68°F room is hot
    await device.wait_for("call_cool", is_on, COOL_OFF_S + 3)
    assert await device.set_number("set_target", 75) == 75  # band 74-76: now it's cold
    await device.wait_for("call_cool", is_off, 5 + 3)
    cool_off = now()
    await device.wait_for("call_wait_reason", lambda v: v == "Changeover wait", 3)
    await device.wait_for("call_heat", is_on, LOCKOUT_S + 5)
    waited = now() - cool_off
    assert LOCKOUT_S - EDGE_SLACK_S <= waited <= LOCKOUT_S + 3, f"heat after {waited:.2f}s"
    assert actions_before(device, "call_heat", ClimateAction.HEATING) == []


async def test_leaving_auto_ends_the_changeover_wait(device):
    await auto_heat_then_cool_wanted(device)
    await device.wait_for("call_wait_reason", lambda v: v == "Changeover wait", 3)
    await device.sleep(2)
    switched = now()
    await device.climate(mode="COOL")  # manual: no lockout, only the AC's own timers
    await device.wait_for("call_cool", is_on, COOL_OFF_S + 3)
    assert now() - switched < COOL_OFF_S + 2


async def test_manual_heat_to_cool_no_lockout(device):
    await auto_heat_then_cool_wanted(device)
    heat_off = now()
    await device.climate(mode="COOL")  # the room is above the 72 target
    await device.wait_for("call_cool", is_on, COOL_OFF_S + 3)
    waited = now() - heat_off
    assert waited < COOL_OFF_S + 2, f"AC waited {waited:.2f}s after a manual switch"
    await device.wait_for("call_wait_reason", lambda v: v == "", 1.5)  # a 1 s tick


async def test_mode_change_mid_run_finishes(device):
    await ready(device)
    await fixed_weather(device, 0)
    assert await device.set_number("comfort_target", 80) == 80  # Cool to 80 later: nothing to do
    await device.climate(mode="HEAT")
    await device.wait_for("call_heat", is_on, HEAT_OFF_S + 3)
    started = now()
    await device.climate(mode="COOL")
    st = await device.wait_for("main_thermostat", lambda v: v.mode == ClimateMode.COOL, 0.5)
    assert now() - started < HEAT_RUN_S - 1, "switched too late to see the run finish"
    assert st.action == ClimateAction.HEATING
    assert await device.state("call_heat") is True
    await device.wait_for("call_heat", is_off, HEAT_RUN_S + 2)
    ran = now() - started
    assert ran >= HEAT_RUN_S - EDGE_SLACK_S, f"furnace cut after {ran:.2f}s"
    st = await device.wait_for("main_thermostat", lambda v: v.action == ClimateAction.IDLE, 1)
    assert st.mode == ClimateMode.COOL
    assert True not in device.history("call_cool")  # cool to 80 in a cold room: nothing to do


# --- Minimum runs under dispatch latency ---
# The call starts from a reading (the sim's interval dispatch) that the test hook holds back
# 3 ms first, so the thermostat starts its minimum-run timer well after the dispatch began. The
# minimum run must still hold when the call is no longer wanted right after it starts.

async def test_heat_min_run_holds_with_dispatch_latency(device):
    await device.action("test_set_latency", ms=3)
    await fixed_weather(device, 68)
    await heat_to(device, 68)  # the 68°F room is on target: idle
    await device.sleep(HEAT_OFF_S + 1)  # past the startup delay
    assert True not in device.history("call_heat")
    await fixed_weather(device, 0)  # the next readings fall below 67.1: heat starts on one
    await device.wait_for("call_heat", is_on, 10)
    started = now()
    await heat_to(device, 50)
    await device.wait_for("call_heat", is_off, HEAT_RUN_S + 3)
    ran = now() - started
    assert ran >= HEAT_RUN_S - EDGE_SLACK_S, f"furnace ran only {ran:.2f}s"


async def test_cool_min_run_holds_with_dispatch_latency(device):
    await device.action("test_set_latency", ms=3)
    await fixed_weather(device, 68)
    await cool_to(device, 68)  # idle: cooling starts at 68.9
    await device.sleep(COOL_OFF_S + 1)
    assert True not in device.history("call_cool")
    await fixed_weather(device, 100)
    await device.wait_for("call_cool", is_on, 10)
    started = now()
    await cool_to(device, 85)
    await device.wait_for("call_cool", is_off, COOL_RUN_S + 3)
    ran = now() - started
    assert ran >= COOL_RUN_S - EDGE_SLACK_S, f"AC ran only {ran:.2f}s"
