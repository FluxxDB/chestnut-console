"""Persistence across a restart (thermostat/logic.yaml, spec "Entities that HA or the web page can
change are restored after a reboot"; "A hold doesn't survive a reboot").

The program is stopped with SIGTERM (which flushes its preferences) and started again on the same
preferences directory (the device_keep_prefs fixture).
"""
import datetime
from zoneinfo import ZoneInfo

from aioesphomeapi import ClimateFanMode, ClimateMode

from test_core import assert_near, fixed_weather, is_on, now
from test_schedule import clock, effective, expected_at, heat_at_68, level, set_target


async def test_settings_survive_restart(device_keep_prefs):
    dev = device_keep_prefs
    await dev.wait_for("effective_target", lambda v: v is not None, 3)
    await dev.climate(mode="COOL", fan_mode="ON")
    assert await dev.set_number("comfort_target", 70) == 70
    assert await dev.set_number("eco_offset", 6) == 6
    assert await dev.set_number("cool_min_off", 8) == 8
    assert (await dev.set_time("sched_weekday_sleep_time", 23, 15)).hour == 23
    assert await dev.select("sched_weekday_sleep_level", "Comfort") == "Comfort"
    assert await dev.switch("schedule_enabled", False) is False
    await dev.sleep(2)  # the preference flush

    await dev.restart()
    boot = dev.started_at

    st = await dev.wait_for("main_thermostat", lambda v: v is not None, 3)
    assert st.mode == ClimateMode.COOL
    assert st.fan_mode == ClimateFanMode.ON
    assert await dev.wait_for("comfort_target", lambda v: v is not None, 3) == 70
    assert await dev.wait_for("eco_offset", lambda v: v is not None, 3) == 6
    assert await dev.wait_for("cool_min_off", lambda v: v is not None, 3) == 8
    t = await dev.wait_for("sched_weekday_sleep_time", lambda v: v is not None, 3)
    assert (t.hour, t.minute) == (23, 15)
    assert await dev.wait_for("sched_weekday_sleep_level", lambda v: v is not None, 3) == "Comfort"
    assert await dev.wait_for("schedule_enabled", lambda v: v is not None, 3) is False

    # No equipment call before the startup delay (the restored 8 s cool minimum off). Ask for
    # cooling at once, in a hot outdoor: the call may come only once the delay is over.
    await fixed_weather(dev, 100)
    await dev.set_number("set_target", 55)
    await dev.wait_for("call_cool", is_on, max(0.5, boot + 8 + 3 - now()))
    assert_near(await dev.edge("call_cool", True), 8, "call_cool after boot with an 8 s minimum off")
    assert True not in dev.history("call_heat")


async def test_hold_does_not_survive_restart(device_keep_prefs):
    """A level hold and a temperature hold are running when the device restarts; after it, neither
    is left: the period's own level and target are back.

    The clock is pinned to the REAL time of day (New York), before and after: at boot the schedule
    evaluates from the real clock, which would end a hold from a different period by itself, so
    only a hold in the same period can show that it is not restored."""
    dev = device_keep_prefs
    now_ny = datetime.datetime.now(ZoneInfo("America/New_York"))
    dow, minute = now_ny.weekday(), now_ny.hour * 60 + now_ny.minute
    await heat_at_68(dev)  # Heat, the schedule on
    await clock(dev, dow, minute)
    # The period's level and Heat target (Comfort 72, Eco 68), once the evaluation has arrived
    # (reading them at once could still see the pinned clock's Comfort).
    eco = expected_at(dow, minute)[1]
    period_level = await level(dev, "Eco" if eco else "Comfort")
    period_target = await effective(dev, 68 if eco else 72)
    other = "Eco" if period_level == "Comfort" else "Comfort"
    await dev.select("comfort_level", other)  # a level hold ...
    await dev.wait_for("schedule_hold", is_on, 2)
    held = await dev.wait_for("effective_target", lambda v: v != period_target, 2)
    await set_target(dev, held + 2)  # ... and a temperature hold on top of it
    await effective(dev, held + 2)
    assert await dev.state("schedule_hold") is True
    await dev.sleep(2)  # the preference flush

    await dev.restart()
    await dev.wait_for("effective_target", lambda v: v is not None, 3)
    await clock(dev, dow, minute)
    st = await dev.wait_for("main_thermostat", lambda v: v is not None, 3)
    assert st.mode.name == "HEAT"
    await level(dev, period_level)  # a surviving level hold would keep `other`
    await effective(dev, period_target)  # a surviving temperature hold would keep held + 2
    await dev.wait_for("schedule_hold", lambda v: v is False, 2)
    await dev.sleep(0.5)
    assert await dev.state("schedule_hold") is False
    assert await dev.state("comfort_level") == period_level
    assert await dev.state("effective_target") == period_target
