"""Thermostat core (thermostat/logic.yaml): equipment calls, startup delay, minimum run and off
times, and the timer settings.

The test entry runs the timers with one "minute" = 1 s (timer_unit_s), so the defaults are:
furnace minimum run / off 3 s, AC minimum run / off 5 s, min_idle_time 1 s. Physics runs at
600x (furnace about +1.7°F per real second with no losses), with Fixed weather in every test.
Targets go straight to the climate's low/high (°C) for now; Task 9 moves them to set_target.
"""
import asyncio

from aioesphomeapi import ClimateFanMode, ClimateMode

from conftest import f_to_c

HEAT_RUN_S = 3
HEAT_OFF_S = 3
COOL_RUN_S = 5
COOL_OFF_S = 5
# How much shorter than the device's own timer a measured gap may look. Both edges are seen
# over the API, which batches states (batch_delay 100 ms, counted from the first item queued
# in a batch; the sim's 250 ms publishes often leave a batch already open), so each edge
# arrives 0 to ~120 ms late. A late start edge plus an early end edge can shave up to that
# much off a gap. Without the timer the gap would be ~0-1 s against 3-5 s thresholds, so
# 0.3 s still catches a broken timer.
EDGE_SLACK_S = 0.3


def now():
    return asyncio.get_running_loop().time()


async def fixed_weather(dev, outdoor_f):
    await dev.select("sim_weather", "Fixed")
    await dev.set_number("sim_outdoor_f", outdoor_f)


async def heat_to(dev, target_f):
    await dev.climate(mode="HEAT", target_temperature_low=f_to_c(target_f),
                      target_temperature_high=f_to_c(target_f + 2))


async def cool_to(dev, target_f):
    await dev.climate(mode="COOL", target_temperature_low=f_to_c(target_f - 2),
                      target_temperature_high=f_to_c(target_f))


def is_on(v):
    return v is True


def is_off(v):
    return v is False


def never_on(dev, object_id):
    return True not in dev.history(object_id)


# The room starts at 68°F. Outdoor 0°F keeps it well below 80°F even with the furnace on (the
# furnace's equilibrium is 80°F), so a Heat call to 80 stays wanted for the whole test.
# Outdoor 100°F keeps it well above 60°F with the AC on.


async def test_boot_no_calls_during_startup_delay(device):
    boot = device.started_at
    await heat_to(device, 80)
    sent = now() - boot
    assert sent < HEAT_OFF_S - 0.5, f"Heat sent {sent:.2f}s after launch: too late to see the delay"
    await fixed_weather(device, 0)
    await device.wait_for("call_heat", is_on, boot + HEAT_OFF_S + 3 - now())
    on_after = now() - boot
    assert on_after >= 2.5, f"call_heat came on {on_after:.2f}s after launch"
    # All relays start off; nothing but W came on.
    for oid in ("call_heat", "call_cool", "call_fan"):
        assert device.history(oid)[0] is False, (oid, device.history(oid))
    assert never_on(device, "call_cool")
    assert never_on(device, "call_fan")


async def test_heat_calls_w_only(device):
    await fixed_weather(device, 0)
    await heat_to(device, 80)
    await device.wait_for("call_heat", is_on, HEAT_OFF_S + 5)
    await device.sleep(1)
    assert await device.state("call_heat") is True
    assert never_on(device, "call_cool")
    assert never_on(device, "call_fan")
    st = await device.state("main_thermostat")
    assert st.mode == ClimateMode.HEAT


async def test_cool_calls_y_and_g(device):
    await fixed_weather(device, 100)
    await cool_to(device, 60)
    await device.wait_for("call_cool", is_on, COOL_OFF_S + 5)
    await device.wait_for("call_fan", is_on, 1)
    await device.sleep(1)
    assert await device.state("call_cool") is True
    assert await device.state("call_fan") is True
    assert never_on(device, "call_heat")


async def test_fan_on_calls_g_alone_in_off(device):
    await fixed_weather(device, 68)
    await device.climate(mode="OFF", fan_mode="ON")
    await device.wait_for("call_fan", is_on, 3)
    # Past every startup delay: still G alone.
    await device.sleep(COOL_OFF_S + 1)
    assert await device.state("call_fan") is True
    assert never_on(device, "call_heat")
    assert never_on(device, "call_cool")
    st = await device.state("main_thermostat")
    assert st.mode == ClimateMode.OFF and st.fan_mode == ClimateFanMode.ON
    await device.climate(fan_mode="AUTO")
    await device.wait_for("call_fan", is_off, 3)


async def test_ob_never_on(device):
    ids = device.object_ids()
    # The relays (relay_ob included) are internal: nothing outside the logic can switch them.
    assert not [i for i in ids if i.startswith("relay")], ids
    # O/B has no call sensor: the call sensors are exactly W, Y and G.
    assert [i for i in ids if i.startswith("call_")] == ["call_cool", "call_fan", "call_heat"]
    # The test hook can't drive O/B either.
    assert device.action_args("test_force_relays") == ["cool", "heat"]


async def test_climate_modes_and_range(device):
    info = device.info("main_thermostat")
    assert set(info.supported_modes) == {ClimateMode.OFF, ClimateMode.HEAT, ClimateMode.COOL,
                                         ClimateMode.HEAT_COOL}
    assert set(info.supported_fan_modes) == {ClimateFanMode.AUTO, ClimateFanMode.ON}
    # Ruling R4: the range covers the derived setpoints, 48–92°F.
    assert info.visual_min_temperature <= f_to_c(48)
    assert info.visual_max_temperature >= f_to_c(92)
    # First boot: Off, fan Auto.
    st = await device.wait_for("main_thermostat", lambda v: v is not None, 3)
    assert st.mode == ClimateMode.OFF and st.fan_mode == ClimateFanMode.AUTO


async def test_min_run_holds_call(device):
    await fixed_weather(device, 0)
    await heat_to(device, 80)
    await device.wait_for("call_heat", is_on, HEAT_OFF_S + 5)
    started = now()
    await heat_to(device, 50)  # far below the room: heating is no longer wanted
    await device.wait_for("call_heat", is_off, HEAT_RUN_S + 3)
    ran = now() - started
    assert ran >= HEAT_RUN_S - EDGE_SLACK_S, f"furnace ran only {ran:.2f}s"


async def test_min_off_blocks_restart(device):
    await fixed_weather(device, 100)
    await cool_to(device, 60)
    await device.wait_for("call_cool", is_on, COOL_OFF_S + 5)
    await cool_to(device, 85)  # satisfied: the AC stops when its minimum run ends
    await device.wait_for("call_cool", is_off, COOL_RUN_S + 3)
    stopped = now()
    await cool_to(device, 60)  # wanted again at once
    await device.wait_for("call_cool", is_on, COOL_OFF_S + 4)
    off_for = now() - stopped
    assert off_for >= COOL_OFF_S - EDGE_SLACK_S, f"AC restarted after only {off_for:.2f}s off"


async def test_timer_number_clamps(device):
    assert await device.wait_for("cool_min_off", lambda v: v is not None, 3) == 5
    assert await device.set_number("cool_min_off", 2) >= 5
    assert await device.set_number("cool_min_off", 25) <= 20
    assert await device.set_number("heat_min_run", 1) >= 2
    assert await device.set_number("changeover_lockout", 5) >= 10


# Beyond the brief's eight (with test_climate_modes_and_range above): the timer numbers really reach the thermostat (at run time and
# through a restart's startup delay), and Fan On combined with heating, idle and cooling.

async def test_timer_number_extends_running_min_run(device):
    await fixed_weather(device, 0)
    await heat_to(device, 80)
    await device.wait_for("call_heat", is_on, HEAT_OFF_S + 5)
    started = now()
    # ESPHome stretches a running timer when its duration changes.
    assert await device.set_number("heat_min_run", 6) == 6
    await heat_to(device, 50)
    await device.wait_for("call_heat", is_off, 6 + 3)
    ran = now() - started
    assert ran >= 6 - EDGE_SLACK_S, f"furnace ran only {ran:.2f}s with a 6 s minimum run"


async def test_startup_delay_uses_restored_timer(device_keep_prefs):
    dev = device_keep_prefs
    assert await dev.set_number("heat_min_off", 8) == 8
    await dev.restart()
    boot = dev.started_at
    assert await dev.wait_for("heat_min_off", lambda v: v is not None, 3) == 8
    await heat_to(dev, 80)
    await fixed_weather(dev, 0)
    await dev.wait_for("call_heat", is_on, boot + 8 + 3 - now())
    on_after = now() - boot
    assert on_after >= 7.5, f"call_heat came on {on_after:.2f}s after launch with an 8 s minimum off"


async def test_fan_on_with_heat_and_idle(device):
    await fixed_weather(device, 0)
    await device.climate(mode="HEAT", fan_mode="ON", target_temperature_low=f_to_c(80),
                         target_temperature_high=f_to_c(82))
    await device.wait_for("call_heat", is_on, HEAT_OFF_S + 5)
    await device.wait_for("call_fan", is_on, 1)  # W + G
    await heat_to(device, 50)
    await device.wait_for("call_heat", is_off, HEAT_RUN_S + 3)
    await device.sleep(1)
    assert await device.state("call_fan") is True  # idle, Fan On: G stays
    await device.climate(fan_mode="AUTO")
    await device.wait_for("call_fan", is_off, 3)
    assert never_on(device, "call_cool")


async def test_fan_auto_keeps_g_while_cooling(device):
    await fixed_weather(device, 100)
    await device.climate(mode="COOL", fan_mode="ON", target_temperature_low=f_to_c(58),
                         target_temperature_high=f_to_c(60))
    await device.wait_for("call_cool", is_on, COOL_OFF_S + 5)
    await device.climate(fan_mode="AUTO")
    n = device.updates("call_fan")
    await device.sleep(2)
    assert await device.state("call_cool") is True
    assert False not in device.history("call_fan")[n:], "G dropped while the AC was running"
    assert await device.state("call_fan") is True
    await cool_to(device, 85)
    await device.wait_for("call_cool", is_off, COOL_RUN_S + 3)
    await device.wait_for("call_fan", is_off, 1)
    assert never_on(device, "call_heat")
