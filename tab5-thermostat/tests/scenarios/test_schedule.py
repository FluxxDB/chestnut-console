"""On-device schedule (thermostat/logic.yaml, spec "Schedule").

Four periods a day (Wake, Leave, Return, Sleep), one set for weekdays and one for weekends; the
schedule only switches comfort_level. A manual change holds until the next period starts (a
temperature hold from set_target, a level hold from comfort_level), or until Resume.

The tests drive the schedule's clock with the test-only API action test_clock(dow 0=Mon..6=Sun,
minute of day, valid); the real clock only drives it at boot (the test entry's schedule_tick
is 24 h, its first run 24 h after boot). The device fixture pins the clock at Mon 7:00 (Wake,
Comfort) right after boot, so other tests don't depend on the time of day.

Defaults: weekdays Wake 6:30 Comfort, Leave 8:30 Eco, Return 17:30 Comfort, Sleep 22:30 Eco;
weekends Wake 8:00 Comfort, Leave 10:00 Comfort, Return 17:00 Comfort, Sleep 23:00 Eco.
Comfort target 72, Eco offset 4: in Heat, Comfort is 72 and Eco 68.
"""
import datetime
from zoneinfo import ZoneInfo

from test_core import fixed_weather, is_off, is_on, set_target

MON, TUE, FRI, SAT, SUN = 0, 1, 4, 5, 6
WAIT_S = 2  # for a state to arrive after a command (API batching is ~0.1 s)
QUIET_S = 0.5  # "nothing changed": longer than the API's batching (>= 0.3 s)

# The defaults as (start minute, eco), index 0..3 = Wake, Leave, Return, Sleep.
NAMES = ["Wake", "Leave", "Return", "Sleep"]
WEEKDAY = [(6 * 60 + 30, False), (8 * 60 + 30, True), (17 * 60 + 30, False), (22 * 60 + 30, True)]
WEEKEND = [(8 * 60, False), (10 * 60, False), (17 * 60, False), (23 * 60, True)]


def hm(h, m=0):
    return h * 60 + m


async def clock(dev, dow, minute, valid=True):
    await dev.action("test_clock", dow=dow, minute=minute, valid=valid)


async def status(dev, text):
    return await dev.wait_for("schedule_status", lambda v: v == text, WAIT_S)


async def level(dev, option):
    return await dev.wait_for("comfort_level", lambda v: v == option, WAIT_S)


async def effective(dev, f):
    return await dev.wait_for("effective_target", lambda v: v == f, WAIT_S)


async def heat_at_68(dev):
    """Heat mode with the room held at 68, so Comfort's effective target is 72 and Eco's 68."""
    await dev.wait_for("effective_target", lambda v: v is not None, 3)
    await fixed_weather(dev, 68)
    await dev.climate(mode="HEAT")


def expected_now(weekday=WEEKDAY, weekend=WEEKEND):
    """(period name, eco) the schedule gives for the real clock now, in New York."""
    now = datetime.datetime.now(ZoneInfo("America/New_York"))
    return expected_at(now.weekday(), now.hour * 60 + now.minute, weekday, weekend)


def expected_at(dow, minute, weekday=WEEKDAY, weekend=WEEKEND):
    """(period name, eco) the schedule gives at this day (0=Mon..6=Sun) and minute of day."""
    def day(d):
        return weekend if d >= 5 else weekday

    started = [(start, i) for i, (start, _) in enumerate(day(dow)) if start <= minute]
    if started:
        i = max(started)[1]
        return NAMES[i], day(dow)[i][1]
    yesterday = day((dow + 6) % 7)
    i = max((start, i) for i, (start, _) in enumerate(yesterday))[1]
    return NAMES[i], yesterday[i][1]


# --- Periods ---

async def test_period_switches_level(device):
    await clock(device, MON, hm(8, 29))
    await level(device, "Comfort")
    await device.wait_for("schedule_period", lambda v: v == "Wake", WAIT_S)
    await status(device, "Comfort until 8:30 am")
    await clock(device, MON, hm(8, 30))
    await level(device, "Eco")
    await device.wait_for("schedule_period", lambda v: v == "Leave", WAIT_S)
    await device.wait_for("schedule_next_change", lambda v: v == "5:30 pm", WAIT_S)
    await status(device, "Eco until 5:30 pm")
    assert True not in device.history("schedule_hold")  # the schedule's own switch isn't a hold


async def test_weekend_uses_weekend_set(device):
    await clock(device, SAT, hm(9))  # weekday 9:00 would be Leave (Eco)
    await device.wait_for("schedule_period", lambda v: v == "Wake", WAIT_S)
    await level(device, "Comfort")
    await status(device, "Comfort until 10:00 am")
    await clock(device, SUN, hm(10, 30))
    await device.wait_for("schedule_period", lambda v: v == "Leave", WAIT_S)
    await status(device, "Comfort until 5:00 pm")
    await clock(device, SAT, hm(23, 30))
    await level(device, "Eco")
    await status(device, "Eco until 8:00 am")  # Sunday's Wake
    # Friday night runs the weekday Sleep; the next change is Saturday's (weekend) Wake.
    await clock(device, FRI, hm(23))
    await device.wait_for("schedule_period", lambda v: v == "Sleep", WAIT_S)
    await status(device, "Eco until 8:00 am")


async def test_edit_period_reevaluates(device):
    await clock(device, MON, hm(8, 45))
    await level(device, "Eco")
    await device.set_time("sched_weekday_leave_time", 9, 0)
    await level(device, "Comfort")  # Wake again, at once
    await device.wait_for("schedule_period", lambda v: v == "Wake", WAIT_S)
    await status(device, "Comfort until 9:00 am")
    await device.select("sched_weekday_wake_level", "Eco")
    await level(device, "Eco")
    await status(device, "Eco until 9:00 am")
    assert True not in device.history("schedule_hold")


# --- Holds ---

async def test_hold_until_next_period(device):
    await heat_at_68(device)
    await clock(device, MON, hm(9))
    await level(device, "Eco")
    await effective(device, 68)
    await set_target(device, 70)
    await device.wait_for("schedule_hold", is_on, WAIT_S)
    await status(device, "Holding 70° until 5:30 pm")
    await effective(device, 70)
    await clock(device, MON, hm(17, 29))
    await device.sleep(QUIET_S)
    assert await device.state("schedule_hold") is True
    assert await device.state("effective_target") == 70
    assert await device.state("schedule_status") == "Holding 70° until 5:30 pm"
    await clock(device, MON, hm(17, 30))
    await device.wait_for("schedule_hold", is_off, WAIT_S)
    await level(device, "Comfort")
    await effective(device, 72)  # the Comfort target
    await status(device, "Comfort until 10:30 pm")
    assert await device.state("comfort_target") == 72


async def test_hold_survives_midnight(device):
    await heat_at_68(device)
    await clock(device, MON, hm(23))
    await level(device, "Eco")
    await set_target(device, 70)
    await status(device, "Holding 70° until 6:30 am")
    await clock(device, TUE, hm(2))  # still Monday's Sleep
    await device.sleep(QUIET_S)
    assert await device.state("schedule_hold") is True
    assert await device.state("effective_target") == 70
    await clock(device, TUE, hm(6, 30))
    await device.wait_for("schedule_hold", is_off, WAIT_S)
    await level(device, "Comfort")
    await effective(device, 72)
    await status(device, "Comfort until 8:30 am")


async def test_resume_clears_hold(device):
    await heat_at_68(device)
    await clock(device, MON, hm(9))
    await level(device, "Eco")
    await set_target(device, 70)
    await device.wait_for("schedule_hold", is_on, WAIT_S)
    await device.press("resume_schedule")
    await device.wait_for("schedule_hold", is_off, WAIT_S)
    await effective(device, 68)  # back to the period's Eco
    await status(device, "Eco until 5:30 pm")
    # A level hold ends the same way, and the period's level comes back.
    await device.select("comfort_level", "Comfort")
    await status(device, "Holding Comfort until 5:30 pm")
    await device.press("resume_schedule")
    await level(device, "Eco")
    await device.wait_for("schedule_hold", is_off, WAIT_S)
    await status(device, "Eco until 5:30 pm")


async def test_level_hold_until_next_period(device):
    await heat_at_68(device)
    await device.select("sched_weekday_leave_level", "Comfort")
    await clock(device, MON, hm(9))
    await level(device, "Comfort")
    await device.select("comfort_level", "Eco")  # by hand
    await device.wait_for("schedule_hold", is_on, WAIT_S)
    await status(device, "Holding Eco until 5:30 pm")
    await effective(device, 68)
    await clock(device, MON, hm(17, 29))
    await device.sleep(QUIET_S)
    assert await device.state("comfort_level") == "Eco"
    assert await device.state("schedule_hold") is True
    await clock(device, MON, hm(17, 30))
    await device.wait_for("schedule_hold", is_off, WAIT_S)
    await level(device, "Comfort")  # Return's level
    await effective(device, 72)
    await status(device, "Comfort until 10:30 pm")


async def test_level_hold_not_reverted_within_period(device):
    await clock(device, MON, hm(9))
    await level(device, "Eco")
    await device.select("comfort_level", "Comfort")
    await status(device, "Holding Comfort until 5:30 pm")
    await clock(device, MON, hm(12))  # a tick in the same period
    await device.set_time("sched_weekday_sleep_time", 23, 0)  # an edit that keeps the period
    await device.sleep(QUIET_S)
    assert await device.state("comfort_level") == "Comfort"
    assert await device.state("schedule_hold") is True


# --- Schedule off, clock not set ---

async def test_schedule_off(device):
    await heat_at_68(device)
    await clock(device, MON, hm(9))
    await set_target(device, 70)
    await device.wait_for("schedule_hold", is_on, WAIT_S)
    assert await device.switch("schedule_enabled", False) is False
    await device.wait_for("schedule_hold", is_off, WAIT_S)  # turning it off ends the hold
    await status(device, "Schedule off")
    await device.wait_for("schedule_period", lambda v: v == "", WAIT_S)
    await device.wait_for("schedule_next_change", lambda v: v == "", WAIT_S)
    await effective(device, 68)  # the level stays where it was (Eco)
    n_hold = device.updates("schedule_hold")
    # No switching.
    await clock(device, MON, hm(17, 30))
    await device.sleep(QUIET_S)
    assert await device.state("comfort_level") == "Eco"
    # set_target just sets the target: it moves comfort_target, with no hold.
    await device.select("comfort_level", "Comfort")
    await effective(device, 72)
    await set_target(device, 70)
    await device.wait_for("comfort_target", lambda v: v == 70, WAIT_S)
    await effective(device, 70)
    await device.select("comfort_level", "Eco")  # a manual level change: no hold either
    await effective(device, 66)
    await device.sleep(QUIET_S)
    assert True not in device.history("schedule_hold")[n_hold:]
    assert await device.state("schedule_status") == "Schedule off"
    # Back on: the current period (Monday 17:30, Return) applies at once.
    assert await device.switch("schedule_enabled", True) is True
    await level(device, "Comfort")
    await status(device, "Comfort until 10:30 pm")


async def test_clock_invalid_pauses(device):
    await clock(device, MON, hm(7))
    await level(device, "Comfort")
    await clock(device, MON, hm(10), valid=False)  # Leave (Eco), if the clock were right
    await status(device, "Schedule paused: clock not set")
    await device.wait_for("schedule_period", lambda v: v == "", WAIT_S)
    await device.sleep(QUIET_S)
    assert await device.state("comfort_level") == "Comfort"
    await clock(device, MON, hm(10))
    await level(device, "Eco")
    await status(device, "Eco until 5:30 pm")


# --- Boot ---

async def test_boot_uses_real_clock_and_drops_hold(device):
    await clock(device, MON, hm(9))
    await set_target(device, 70)
    await device.wait_for("schedule_hold", is_on, WAIT_S)
    await device.set_time("sched_weekday_return_time", 18, 15)  # restored
    week = (WEEKDAY[:2] + [(hm(18, 15), False)] + WEEKDAY[3:], WEEKEND)
    before = expected_now(*week)
    await device.restart()  # no pinned clock this time: boot reads the real one
    period = await device.wait_for("schedule_period", lambda v: v, 3)
    after = expected_now(*week)
    assert period in (before[0], after[0]), f"real clock gives {before} / {after}"
    eco = before[1] if period == before[0] else after[1]
    await level(device, "Eco" if eco else "Comfort")
    assert await device.wait_for("schedule_hold", lambda v: v is not None, 3) is False
    st = await device.wait_for("schedule_status", lambda v: v, 3)
    assert st.startswith("Eco until" if eco else "Comfort until"), st
    t = await device.wait_for("sched_weekday_return_time", lambda v: v is not None, 3)
    assert (t.hour, t.minute) == (18, 15)


async def test_schedule_off_survives_restart_and_keeps_level(device):
    assert await device.switch("schedule_enabled", False) is False
    await device.select("comfort_level", "Eco")  # with the schedule off: no hold
    await device.restart()  # boot reads the real clock, but the schedule is off
    assert await device.wait_for("schedule_enabled", lambda v: v is not None, 3) is False
    await status(device, "Schedule off")
    assert await device.wait_for("comfort_level", lambda v: v is not None, 3) == "Eco"
    assert await device.state("schedule_hold") is False
