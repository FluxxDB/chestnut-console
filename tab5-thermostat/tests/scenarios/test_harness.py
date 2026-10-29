"""Self-tests for the harness: a program that dies mid-test must fail the test loudly, never
read as "nothing happened" (stale cached states, or a negative check that passes)."""
import asyncio
import signal

import pytest


def crash(dev):
    dev._proc.send_signal(signal.SIGKILL)
    dev._proc.wait()


async def test_reads_after_crash_raise(device):
    await device.wait_for("sim_room_f", lambda v: v is not None, 3)
    crash(device)
    with pytest.raises(RuntimeError, match="device exited"):
        await device.state("sim_room_f")
    with pytest.raises(RuntimeError, match="device exited"):
        device.updates("room_temperature")
    with pytest.raises(RuntimeError, match="device exited"):
        await device.select("sim_fault", "Frozen")
    await device.stop(expect_dead=True)


async def test_crash_during_wait_raises_promptly(device):
    loop = asyncio.get_running_loop()
    loop.call_later(0.5, crash, device)
    start = loop.time()
    with pytest.raises(RuntimeError, match="device exited"):
        # A "nothing happens for 5 s" check, and a wait that would otherwise time out.
        await device.sleep(5)
    assert loop.time() - start < 2
    await device.stop(expect_dead=True)


async def test_crash_during_wait_for_raises(device):
    asyncio.get_running_loop().call_later(0.5, crash, device)
    with pytest.raises(RuntimeError, match="device exited"):
        await device.wait_for("sim_room_f", lambda v: v > 500, 5)
    await device.stop(expect_dead=True)


async def test_stop_fails_if_device_already_exited(device):
    crash(device)
    with pytest.raises(RuntimeError, match="already exited"):
        await device.stop()


async def test_clean_stop_and_restart(device):
    await device.restart()  # SIGTERM exits 0, so this must not raise
    await device.wait_for("sim_room_f", lambda v: v is not None, 3)
