"""Thermostat core (thermostat/logic.yaml): equipment calls, startup delay, minimum run and off
times, and the timer settings.

The test entry runs the timers with one "minute" = 1 s (timer_unit_s), so the defaults are:
furnace minimum run / off 3 s, AC minimum run / off 5 s, min_idle_time 1 s. Physics runs at
600x (furnace about +1.7°F per real second with no losses), with Fixed weather in every test.
Targets go through set_target (°F), as the screen's − / + do: the climate's low / high are
derived from it (a Heat target of T is low T / high T+2, a Cool target low T-2 / high T).
"""
import asyncio

from aioesphomeapi import ClimateFanMode, ClimateMode

from conftest import f_to_c

HEAT_RUN_S = 3
HEAT_OFF_S = 3
COOL_RUN_S = 5
COOL_OFF_S = 5
# Durations are measured on the device: the test entry publishes each relay edge's device time
# (ms since boot; conftest's Dev.edge), so API batching doesn't blur them. A timer-bound edge
# lands within one loop pass of the timer's end, so +-150 ms is plenty around the configured
# value, and still far from the ~0-1 s a broken timer would give against 3-5 s.
TOL_MS = 150


def assert_near(ms, expected_s, what, tol_ms=TOL_MS, late_ms=None):
    """ms (a device-measured duration) is expected_s seconds, within -tol_ms / +late_ms
    (late_ms defaults to tol_ms)."""
    lo, hi = expected_s * 1000 - tol_ms, expected_s * 1000 + (tol_ms if late_ms is None else late_ms)
    assert lo <= ms <= hi, f"{what}: {ms / 1000:.3f}s, expected {expected_s}s (-{tol_ms} / +{hi - expected_s * 1000:.0f} ms)"


async def run_ms(dev, call, timeout_s):
    """Waits for the call's relay to go off; returns (on, off), the device times (ms since boot)
    of the last on edge before that off edge and of the off edge."""
    on = dev.edges(call, True)[-1] if dev.edges(call, True) else await dev.edge(call, True)
    off = await dev.edge(call, False, on, timeout_s)
    return on, off


def now():
    return asyncio.get_running_loop().time()


async def fixed_weather(dev, outdoor_f):
    await dev.select("sim_weather", "Fixed")
    await dev.set_number("sim_outdoor_f", outdoor_f)


async def set_target(dev, target_f):
    """set_target, as the screen's − / + do: a hold at target_f (or nothing if it's already the
    effective target). Fails if the device refused it."""
    got = await dev.set_number("set_target", target_f)
    assert got == target_f, f"set_target {target_f} read back {got}"


async def heat_to(dev, target_f):
    await dev.climate(mode="HEAT")
    await set_target(dev, target_f)


async def cool_to(dev, target_f):
    await dev.climate(mode="COOL")
    await set_target(dev, target_f)


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
    # Wanted from the start: W comes on when the boot-time minimum off ends.
    assert_near(await device.edge("call_heat", True), HEAT_OFF_S, "call_heat after boot")
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
    # O/B has no call sensor: the call sensors are exactly W, Y and G (call_wait_reason is text).
    calls = [i for i in ids if i.startswith("call_") and i != "call_wait_reason"]
    assert calls == ["call_cool", "call_fan", "call_heat"]
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
    await heat_to(device, 50)  # far below the room: heating is no longer wanted
    on, off = await run_ms(device, "call_heat", HEAT_RUN_S + 3)
    assert_near(off - on, HEAT_RUN_S, "furnace run")


async def test_min_off_blocks_restart(device):
    await fixed_weather(device, 100)
    await cool_to(device, 60)
    await device.wait_for("call_cool", is_on, COOL_OFF_S + 5)
    await cool_to(device, 85)  # satisfied: the AC stops when its minimum run ends
    _, stopped = await run_ms(device, "call_cool", COOL_RUN_S + 3)
    await cool_to(device, 60)  # wanted again at once
    restarted = await device.edge("call_cool", True, stopped, COOL_OFF_S + 4)
    assert_near(restarted - stopped, COOL_OFF_S, "AC off time")


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
    # ESPHome stretches a running timer when its duration changes.
    assert await device.set_number("heat_min_run", 6) == 6
    await heat_to(device, 50)
    on, off = await run_ms(device, "call_heat", 6 + 3)
    assert_near(off - on, 6, "furnace run with a 6 s minimum run")


async def test_startup_delay_uses_restored_timer(device_keep_prefs):
    dev = device_keep_prefs
    assert await dev.set_number("heat_min_off", 8) == 8
    await dev.restart()
    boot = dev.started_at
    assert await dev.wait_for("heat_min_off", lambda v: v is not None, 3) == 8
    await heat_to(dev, 80)
    await fixed_weather(dev, 0)
    await dev.wait_for("call_heat", is_on, boot + 8 + 3 - now())
    assert_near(await dev.edge("call_heat", True), 8, "call_heat after boot with an 8 s minimum off")


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

