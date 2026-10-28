"""Persistence across a restart (thermostat/logic.yaml, spec "Entities that HA or the web page can
change are restored after a reboot"; "A hold doesn't survive a reboot").

The program is stopped with SIGTERM (which flushes its preferences) and started again on the same
preferences directory (the device_keep_prefs fixture).
"""
import datetime

from aioesphomeapi import ClimateFanMode, ClimateMode

from test_core import fixed_weather, is_on, now


async def test_settings_survive_restart(device_keep_prefs):
    dev = device_keep_prefs
    await dev.wait_for("effective_target", lambda v: v is not None, 3)
    await dev.climate(mode="COOL", fan_mode="ON")
    assert await dev.set_number("comfort_target", 70) == 70
    assert await dev.set_number("eco_offset", 6) == 6
    assert await dev.set_number("cool_min_off", 8) == 8
    assert (await dev.set_time("sched_weekday_sleep_time", 23, 15)).hour == 23
    assert await dev.select("sched_weekday_sleep_level", "Eco") == "Eco"
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
    assert await dev.wait_for("sched_weekday_sleep_level", lambda v: v is not None, 3) == "Eco"
    assert await dev.wait_for("schedule_enabled", lambda v: v is not None, 3) is False

    # A hold doesn't survive a reboot (and the schedule is off anyway).
    assert await dev.wait_for("schedule_hold", lambda v: v is not None, 3) is False
    await dev.sleep(0.5)
    assert True not in dev.history("schedule_hold")

    # No equipment call before the startup delay (the restored 8 s cool minimum off). Ask for
    # cooling at once, in a hot outdoor: the call may come only once the delay is over.
    await fixed_weather(dev, 100)
    await dev.set_number("set_target", 55)
    await dev.sleep(max(0, boot + 7.5 - now()))
    assert True not in dev.history("call_cool"), "cool call started inside the startup delay"
    assert True not in dev.history("call_heat")
    await dev.wait_for("call_cool", is_on, max(0.5, boot + 8 + 3 - now()))
