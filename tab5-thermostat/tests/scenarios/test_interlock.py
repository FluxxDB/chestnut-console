"""Interlock watchdog (thermostat/logic.yaml, spec Safety 3): if W and Y are ever both on, the
watchdog cuts both at once (ignoring minimum run times), latches `interlock_fault`, and while
latched no heat or cool call goes through, until the Clear button is pressed (or a reboot).

The test hook `test_force_relays` switches the relays directly, which is the only way to reach
the both-on state: the logic's own actions always turn the opposite relay off first.
Timers are the test build's: furnace minimum run / off 3 s, AC 5 s.
"""
import asyncio

from aioesphomeapi import ClimateMode

from conftest import f_to_c

from test_core import (COOL_OFF_S, HEAT_OFF_S, fixed_weather, heat_to, cool_to, is_off, is_on,
                       never_on, now)


async def trip(dev):
    """Both relays on, then wait for the watchdog to latch the fault."""
    await dev.action("test_force_relays", heat=True, cool=True)
    await dev.wait_for("interlock_fault", is_on, 1)
    await dev.wait_for("call_heat", is_off, 1)
    await dev.wait_for("call_cool", is_off, 1)


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
    assert True not in device.history("call_heat")[n:], "heat call went through while latched"
    assert await device.state("interlock_fault") is True
    assert True not in device.history("call_cool")[nc:]


async def test_clear_restores(device):
    await trip(device)
    await fixed_weather(device, 0)
    nc = device.updates("call_cool")
    await heat_to(device, 73)
    # Let the thermostat reach HEATING (relays stay off), so its own state has to be reset.
    await device.sleep(HEAT_OFF_S + 2)
    assert await device.state("call_heat") is False
    await device.press("clear_interlock_fault")
    await device.wait_for("interlock_fault", is_off, 1)
    await device.wait_for("call_heat", is_on, 8)
    st = await device.state("main_thermostat")
    assert st.mode == ClimateMode.HEAT  # the user's mode was put back
    assert True not in device.history("call_cool")[nc:]
    assert await device.state("interlock_fault") is False


async def test_clear_when_healthy_is_harmless(device):
    await fixed_weather(device, 100)
    await cool_to(device, 60)
    await device.wait_for("call_cool", is_on, COOL_OFF_S + 5)
    await device.press("clear_interlock_fault")
    await device.sleep(1)
    assert await device.state("call_cool") is True
    assert await device.state("interlock_fault") is False
    st = await device.state("main_thermostat")
    assert st.mode == ClimateMode.COOL


async def test_heat_to_cool_handover_does_not_trip(device):
    await fixed_weather(device, 0)
    await heat_to(device, 80)
    await device.wait_for("call_heat", is_on, HEAT_OFF_S + 5)
    # Change of mind: now cooling is wanted. The furnace stops, then the AC starts.
    await cool_to(device, 60)
    await device.wait_for("call_cool", is_on, 15)
    assert await device.state("call_heat") is False
    assert await device.state("interlock_fault") is False
    assert never_on(device, "interlock_fault")
