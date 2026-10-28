"""Scenario-test harness: runs the host build of tests/main-thermostat-test.yaml and drives it
over the native API (aioesphomeapi).

`run.sh scenarios` compiles the test entry once, then runs pytest. Each test gets its own
device process. Entities are looked up by object_id (the snake_case of the entity name).
"""
import asyncio
import os
import re
import shutil
import signal
import subprocess
from pathlib import Path

import pytest
import pytest_asyncio
from aioesphomeapi import APIClient, ClimateFanMode, ClimateInfo, ClimateMode, ClimateState

TESTS_DIR = Path(__file__).resolve().parent.parent
DEVICE_NAME = "main-thermostat-test"
# Where `esphome compile tests/main-thermostat-test.yaml` puts the host program (found in Task 5, Step 1).
BINARY = TESTS_DIR / ".esphome" / "build" / DEVICE_NAME / ".pioenvs" / DEVICE_NAME / "program"
# The host platform keeps its preferences in $ESPHOME_PREFDIR/<device name>.prefs
# (esphome/components/host/preferences.cpp; without the variable it uses ~/.esphome/prefs).
PREFS_ENV = "ESPHOME_PREFDIR"
# Kept prefs dirs (device_keep_prefs) and device logs for inspection; gitignored.
PREFS_ROOT = TESTS_DIR / ".prefs"
API_HOST = "127.0.0.1"  # pytest and the program run in the same container
API_PORT = 6053
START_TIMEOUT_S = 20
STOP_TIMEOUT_S = 5
ALIVE_CHECK_S = 0.2  # how often a wait checks that the program is still running
SET_WAIT_S = 2  # how long set_number/select/switch wait to see the new state


def f_to_c(f):
    return (f - 32) * 5 / 9


def c_to_f(c):
    return c * 9 / 5 + 32


def _plain(state):
    """An API state message as a plain value: None while unknown, enums kept as enums,
    climates returned whole (ClimateState)."""
    if getattr(state, "missing_state", False):
        return None
    if isinstance(state, ClimateState):
        return state
    return getattr(state, "state", state)


def _enum(enum_cls, value):
    if value is None or isinstance(value, enum_cls):
        return value
    return enum_cls[str(value).upper()]


class Dev:
    """One running device program plus an API connection to it."""

    def __init__(self, prefs_dir: Path, log_path: Path):
        self.prefs_dir = prefs_dir
        self.log_path = log_path
        self._proc = None
        self._log = None
        self._client = None
        self._entities = {}  # object_id -> EntityInfo
        self._names = {}  # key -> object_id
        self._services = {}  # name -> UserService
        self._climate = None
        self._values = {}  # object_id -> latest plain value
        self._history = {}  # object_id -> every value received, in order
        self._times = {}  # object_id -> event-loop arrival time of each value in _history
        self._changed = asyncio.Event()
        self.started_at = None  # event-loop time just before the program was launched

    # --- process lifecycle ---

    async def start(self):
        if not BINARY.exists():
            raise RuntimeError(f"{BINARY} not found; run `tests/run.sh build` (run.sh scenarios builds it)")
        self.prefs_dir.mkdir(parents=True, exist_ok=True)
        self._log = open(self.log_path, "ab")
        self.started_at = asyncio.get_running_loop().time()
        self._proc = subprocess.Popen(
            [str(BINARY)],
            env={**os.environ, PREFS_ENV: str(self.prefs_dir)},
            stdout=self._log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
        )
        await self._connect()

    async def _connect(self):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + START_TIMEOUT_S
        last_err = None
        while loop.time() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(f"device exited with {self._proc.returncode}\n{self.log_tail()}")
            client = APIClient(API_HOST, API_PORT, None, expected_name=DEVICE_NAME)
            try:
                await client.connect(login=True)
            except Exception as err:  # not listening yet
                last_err = err
                await asyncio.sleep(0.2)
                continue
            self._client = client
            break
        else:
            raise RuntimeError(f"API did not answer within {START_TIMEOUT_S}s: {last_err}\n{self.log_tail()}")

        entities, services = await self._client.list_entities_services()
        self._entities = {e.object_id: e for e in entities}
        self._names = {e.key: e.object_id for e in entities}
        self._services = {s.name: s for s in services}
        climates = [e for e in entities if isinstance(e, ClimateInfo)]
        self._climate = climates[0] if len(climates) == 1 else None
        self._values.clear()
        self._history.clear()
        self._times.clear()
        self._client.subscribe_states(self._on_state)

    def _on_state(self, state):
        oid = self._names.get(state.key)
        if oid is None:
            return
        value = _plain(state)
        self._values[oid] = value
        self._history.setdefault(oid, []).append(value)
        self._times.setdefault(oid, []).append(asyncio.get_running_loop().time())
        self._changed.set()
        self._changed = asyncio.Event()

    def _check_alive(self):
        """Fail loudly if the program is gone, so a crash never reads as "nothing happened"."""
        if self._proc is None:
            raise RuntimeError("device is not running")
        rc = self._proc.poll()
        if rc is not None:
            raise RuntimeError(f"device exited with code {rc}\n{self.log_tail()}")

    async def stop(self, expect_dead=False):
        """Graceful stop: SIGTERM makes the host program flush its preferences.
        Fails if the program had already exited (it crashed during the test), unless
        expect_dead, or if it doesn't exit cleanly on SIGTERM."""
        if self._client is not None:
            try:
                await asyncio.wait_for(self._client.disconnect(), 2)
            except Exception:
                pass
            self._client = None
        problem = None
        if self._proc is not None:
            rc = self._proc.poll()
            if rc is not None:
                if not expect_dead:
                    problem = f"device had already exited with code {rc} before the test stopped it"
            else:
                self._proc.send_signal(signal.SIGTERM)
                try:
                    rc = await asyncio.to_thread(self._proc.wait, STOP_TIMEOUT_S)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    await asyncio.to_thread(self._proc.wait)
                    problem = f"device did not stop within {STOP_TIMEOUT_S}s of SIGTERM (killed)"
                else:
                    if rc != 0:
                        problem = f"device exited with code {rc} on SIGTERM"
        self._proc = None
        if self._log is not None:
            self._log.close()
            self._log = None
        if problem:
            raise RuntimeError(f"{problem}\n{self.log_tail()}")

    async def restart(self):
        """Stop and start the program again with the same preferences dir."""
        await self.stop()
        await self.start()

    def log_tail(self, lines=40):
        try:
            text = self.log_path.read_text(errors="replace")
        except OSError:
            return ""
        return "\n".join(text.splitlines()[-lines:])

    # --- reading ---

    def _info(self, object_id):
        try:
            return self._entities[object_id]
        except KeyError:
            raise KeyError(f"no entity with object_id {object_id!r}; have {sorted(self._entities)}") from None

    def info(self, object_id):
        """The entity's API description (e.g. a ClimateInfo with its supported modes)."""
        return self._info(object_id)

    def object_ids(self):
        """The object_ids of every entity the device exposes over the API."""
        self._check_alive()
        return sorted(self._entities)

    def action_args(self, name):
        """The argument names of an API action (`api: actions:`)."""
        try:
            service = self._services[name]
        except KeyError:
            raise KeyError(f"no API action {name!r}; have {sorted(self._services)}") from None
        return sorted(arg.name for arg in service.args)

    async def state(self, object_id):
        """The latest value: float, bool, str, a ClimateState, or None while unknown."""
        self._info(object_id)
        self._check_alive()
        return self._values.get(object_id)

    def updates(self, object_id):
        """How many states have arrived for the entity since connecting."""
        self._info(object_id)
        self._check_alive()
        return len(self._history.get(object_id, ()))

    def history(self, object_id):
        """Every value received for the entity since connecting, oldest first."""
        self._info(object_id)
        self._check_alive()
        return list(self._history.get(object_id, ()))

    def timed_history(self, object_id):
        """Like history(), as (arrival time, value) pairs; times are the event loop's (now())."""
        self._info(object_id)
        self._check_alive()
        return list(zip(self._times.get(object_id, ()), self._history.get(object_id, ())))

    async def _wait_change(self, deadline):
        """Wait for any new state until deadline; False on timeout. Raises if the program
        exits meanwhile (checked every ALIVE_CHECK_S)."""
        loop = asyncio.get_running_loop()
        changed = self._changed
        while True:
            self._check_alive()
            remaining = deadline - loop.time()
            if remaining <= 0:
                return False
            try:
                await asyncio.wait_for(changed.wait(), min(remaining, ALIVE_CHECK_S))
            except asyncio.TimeoutError:
                continue
            return True

    async def sleep(self, seconds):
        """asyncio.sleep that fails at once if the program exits meanwhile. Use it for
        "wait and check nothing happened" steps."""
        deadline = asyncio.get_running_loop().time() + seconds
        while await self._wait_change(deadline):
            pass

    async def wait_for(self, object_id, pred, timeout_s):
        """Wait until pred(value) is true; returns the value. Fails the test on timeout."""
        self._info(object_id)
        deadline = asyncio.get_running_loop().time() + timeout_s
        while True:
            self._check_alive()
            value = self._values.get(object_id)
            try:
                ok = bool(pred(value))
            except TypeError:  # e.g. comparing None while the state is unknown
                ok = False
            if ok:
                return value
            if not await self._wait_change(deadline):
                raise AssertionError(f"{object_id}: condition not met within {timeout_s}s (last value {value!r})")

    async def next_value(self, object_id, timeout_s):
        """The next state that arrives for the entity after this call."""
        n = self.updates(object_id)
        await self.wait_for(object_id, lambda _: self.updates(object_id) > n, timeout_s)
        return self._history[object_id][n]

    # --- commands ---

    def _live_client(self):
        self._check_alive()
        return self._client

    async def _sync(self):
        # The device handles messages in order, so a reply to a later request means
        # the earlier command has been processed.
        self._check_alive()
        await self._client.device_info()

    async def _settle(self, object_id, matches, n_before):
        """After a command: wait (briefly, without failing) until the state matches the
        request or any new state arrives (a refused or clamped value shows up that way)."""
        await self._sync()
        deadline = asyncio.get_running_loop().time() + SET_WAIT_S
        while not (matches(self._values.get(object_id)) or self.updates(object_id) > n_before):
            if not await self._wait_change(deadline):
                break
        return self._values.get(object_id)

    async def set_number(self, object_id, value):
        n = self.updates(object_id)
        self._live_client().number_command(self._info(object_id).key, float(value))
        return await self._settle(object_id, lambda v: v is not None and abs(v - value) < 1e-3, n)

    async def select(self, object_id, option):
        n = self.updates(object_id)
        self._live_client().select_command(self._info(object_id).key, option)
        return await self._settle(object_id, lambda v: v == option, n)

    async def switch(self, object_id, on):
        n = self.updates(object_id)
        self._live_client().switch_command(self._info(object_id).key, bool(on))
        return await self._settle(object_id, lambda v: v == bool(on), n)

    async def press(self, object_id):
        self._live_client().button_command(self._info(object_id).key)
        await self._sync()

    async def climate(self, mode=None, fan_mode=None, target_temperature=None,
                      target_temperature_low=None, target_temperature_high=None,
                      custom_preset=None):
        """A climate call on the device's climate (temperatures in °C). Modes and fan modes
        take the aioesphomeapi enums or their names ("HEAT", "HEAT_COOL", "ON", ...)."""
        if self._climate is None:
            raise KeyError("the device has no single climate entity")
        self._live_client().climate_command(
            self._climate.key,
            mode=_enum(ClimateMode, mode),
            fan_mode=_enum(ClimateFanMode, fan_mode),
            target_temperature=target_temperature,
            target_temperature_low=target_temperature_low,
            target_temperature_high=target_temperature_high,
            custom_preset=custom_preset,
        )
        await self._sync()

    async def action(self, name, **kwargs):
        """Run an API action (`api: actions:`) with keyword arguments."""
        try:
            service = self._services[name]
        except KeyError:
            raise KeyError(f"no API action {name!r}; have {sorted(self._services)}") from None
        await self._live_client().execute_service(service, kwargs)
        await self._sync()


# Record test failures so the device fixture can print the device log on failure only.
_FAILED = pytest.StashKey[bool]()


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    report = yield
    if report.when == "call" and report.failed:
        item.stash[_FAILED] = True
    return report


def _slug(nodeid):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", nodeid).strip("_")


async def _run_device(request, prefs_dir):
    PREFS_ROOT.mkdir(exist_ok=True)
    dev = Dev(prefs_dir, PREFS_ROOT / f"{_slug(request.node.nodeid)}.log")
    dev.log_path.unlink(missing_ok=True)
    try:
        await dev.start()
        yield dev
    finally:
        await dev.stop()
        if request.node.stash.get(_FAILED, False):
            print(f"--- device log tail ({dev.log_path}) ---\n{dev.log_tail()}")


@pytest_asyncio.fixture
async def device(request, tmp_path):
    """A freshly started device with empty preferences (a new dir per test)."""
    async for dev in _run_device(request, tmp_path / "prefs"):
        yield dev


@pytest_asyncio.fixture
async def device_keep_prefs(request):
    """Like `device`, for restart tests: its preferences live in tests/.prefs/<test>/ and stay
    there after the test, so they can be inspected. Each run still starts from empty."""
    prefs = PREFS_ROOT / _slug(request.node.nodeid)
    shutil.rmtree(prefs, ignore_errors=True)
    async for dev in _run_device(request, prefs):
        yield dev
