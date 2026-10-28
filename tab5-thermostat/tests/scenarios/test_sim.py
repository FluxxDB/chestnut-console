"""The virtual house (sim/virtual-house.yaml), driven through the test build.

The test entry runs the physics 600x faster (one 1 s step = 10 simulated minutes) and
publishes room_temperature every 250 ms. The relays are internal, so the tests see their
effect through sim_room_f, the true room temperature.
"""
import asyncio

from conftest import f_to_c


async def fixed_weather(dev, outdoor_f):
    await dev.select("sim_weather", "Fixed")
    await dev.set_number("sim_outdoor_f", outdoor_f)


async def test_room_drifts_toward_outdoor(device):
    await fixed_weather(device, 30)
    await device.wait_for("sim_room_f", lambda f: f < 67, 20)


async def test_forced_heat_warms(device):
    # Outdoor equal to the starting room, so drift alone never takes the room above 68.
    await fixed_weather(device, 68)
    await device.action("test_force_relays", heat=True, cool=False)
    await device.wait_for("sim_room_f", lambda f: f > 69, 20)


async def test_room_temperature_is_celsius_with_noise(device):
    await fixed_weather(device, 68)
    await asyncio.sleep(1.5)  # let the room settle near 68 so it barely moves between readings
    a = await device.next_value("room_temperature", 3)
    b = await device.next_value("room_temperature", 3)
    room_c = f_to_c(await device.state("sim_room_f"))
    assert a != b, "two readings in a row are identical: no noise"
    assert abs(a - room_c) < 0.2, (a, room_c)
    assert abs(b - room_c) < 0.2, (b, room_c)


async def test_fault_unplugged_stops_publishing(device):
    await device.next_value("room_temperature", 3)  # it is publishing
    await device.select("sim_fault", "Unplugged")
    await asyncio.sleep(0.5)  # a reading already in flight may still arrive
    before = device.updates("room_temperature")
    await asyncio.sleep(2)
    assert device.updates("room_temperature") == before


async def test_fault_out_of_range(device):
    await device.select("sim_fault", "Out of range")
    await device.wait_for("room_temperature", lambda c: c == 60.0, 3)


# Beyond the brief's five: the other two fault modes (Task 8's sanity tests rely on them) and
# the restored knobs (which also exercises the harness's restart).

async def test_fault_frozen_repeats_last_value(device):
    await device.next_value("room_temperature", 3)
    await device.select("sim_fault", "Frozen")
    await asyncio.sleep(0.5)
    a = await device.next_value("room_temperature", 3)
    b = await device.next_value("room_temperature", 3)
    c = await device.next_value("room_temperature", 3)
    assert a == b == c


async def test_fault_spike_is_one_reading_then_none(device):
    await fixed_weather(device, 68)
    await asyncio.sleep(1.5)
    base = await device.next_value("room_temperature", 3)
    n = device.updates("room_temperature")
    await device.select("sim_fault", "Spike")
    await asyncio.sleep(1.5)  # about six readings
    seen = device.history("room_temperature")[n:]
    spikes = [v for v in seen if v > base + 5]
    assert len(spikes) == 1, seen
    assert abs(spikes[0] - base - 10) < 0.3, (base, spikes)
    await device.wait_for("sim_fault", lambda o: o == "None", 2)


async def test_knobs_survive_restart(device_keep_prefs):
    dev = device_keep_prefs
    await dev.set_number("sim_outdoor_f", 50)
    await dev.select("sim_weather", "Summer day")
    await dev.select("sim_fault", "Frozen")
    await dev.restart()
    assert await dev.wait_for("sim_outdoor_f", lambda v: v is not None, 3) == 50
    assert await dev.wait_for("sim_weather", lambda v: v is not None, 3) == "Summer day"
    assert await dev.wait_for("sim_fault", lambda v: v is not None, 3) == "Frozen"
    # The room itself is not restored: it starts again at 68.
    assert abs(await dev.wait_for("sim_room_f", lambda v: v is not None, 3) - 68) < 3
