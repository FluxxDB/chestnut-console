# Milestone 2: Main Thermostat logic and virtual house

*Design, 2026-10-28. Owner: mac-chestnut-console (branch `mac/thermostat-logic`). Status: ready for Dang's approval. Builder check done; Q1–Q3 answered by Dang.*

Decisions are marked by who made them: **Dang** (asked in a survey), **PC** (pc-chestnut-console, Dang delegated the call), or **Mac call** (my default, open to change while you read this).

## Why

The Main Thermostat has to keep the house comfortable on its own. Home Assistant and Wi-Fi are extras: if either goes down, heating and cooling carry on (AGENTS.md, core decision). Nothing can be wired until Dang's next visit, so the logic is built and proven now against a **virtual house**: a simulated room whose temperature drifts toward the outdoor temperature and responds to virtual furnace, AC and fan relays. When the bench parts arrive (M4), the sensor and relay packages are swapped for real ones and the logic package doesn't change.

## What done looks like (Dang)

1. **Play with it in a browser.** You set the mode and target, change the outdoor temperature, break the sensor on purpose, and watch the virtual relays react. **Catch:** ESPHome's `web_server` doesn't build for the `host` platform (its `only_on` list in 2026.10.1 leaves out `host`), so the computer-run sim can't serve that page. **Dang (Q2):** the browser play happens on the **Tab5's own web page**, with the Tab5 running the logic against the virtual house (criterion 4). The computer-run sim shows up in **HA** and runs the automated tests.
2. **See it in Home Assistant.** The simulated device connects to HA like the real one does, so the HA thermostat card, history graphs and alerts can be tried before the Tab5 runs the logic.
3. **Automated safety tests.** Scripted scenarios check each safety rule on their own and report pass/fail.
4. **The same logic package runs on the Tab5**, with the virtual house package standing in for the real sensor and relays until M4.

Dang did not ask for a fast-forward mode for playing with it: the browser sim runs in real time. The automated tests do run with shortened timers and sped-up physics, so they finish in minutes. The shipped values stay real. (Mac call.)

## Goals

- ESPHome `thermostat` climate `main_thermostat` controlling a **gas furnace + central AC** (PC, from research.md section 0).
- Modes **Off, Heat, Cool, Auto**. Fan **Auto, On** (Dang).
- **One target temperature in every mode, Auto included** (Dang, relayed by PC). In Auto it heats when the room is about 1°F below the target, cools when it's about 1°F above, and idles in between.
- **Comfort / Eco** instead of named presets (Dang). There's one Comfort target. Eco lets the house drift a set number of degrees (default 4°F, adjustable) the money-saving way: cooler while heating, warmer while cooling, both ways in Auto.
- An **on-device weekly schedule** that keeps running without HA or Wi-Fi (Dang). Four periods, **Wake / Leave / Return / Sleep**, each a start time plus Comfort or Eco, with one set for **weekdays** and one for **weekends**. It's editable from HA, from the Tab5 web page, and later from the touchscreen (Dang; the screen is PC/M3 work).
- **A manual change holds until the next schedule period**, then the schedule takes over again (Dang).
- All the safety requirements from AGENTS.md: min run/off times, `startup_delay`, a heat/cool interlock, sensor sanity checks, no reboots on HA or Wi-Fi loss.
- **Safety timers editable from HA and the web page, clamped to safe ranges** (Dang).
- A **simple virtual house with knobs** (Dang).

## Non-goals (for M2)

- **Heat pumps.** `relay_ob` exists and stays off. When the survey says heat pump, support gets **added as configuration only**: O/B polarity, aux heat on W, and a conventional/heat-pump setting. Nothing gets restructured (PC's condition, Mac agrees). The M2 structure must leave room for that.
- Multi-stage heat or cool, humidity control, the top floor, weather or occupancy integrations.
- Screens on the Tab5 (PC owns M3), HA dashboards and notification automations (PC owns `home-assistant/`), real sensor and relay drivers (M4).

## Anti-goals: failure even if it "works"

- The house gets too hot or too cold because something crashed, rebooted or lost the network.
- Short-cycling the compressor or furnace. **Heat and cool on at the same time, ever.**
- A schedule that fights the person standing at the thermostat.
- Test hooks or simulation code that ends up able to drive real relays on the Tab5.
- Timers someone can set to unsafe values from a phone.
- An Auto mode that ping-pongs between heating and cooling.

## Constraints

- ESPHome 2026.10.1 (pinned in `docker-compose.yml`). C++ only for custom bits (AGENTS.md).
- **ESPHome forces two setpoints when the thermostat has both heat and cool actions.** `thermostat/climate.py` sets `supports_two_points` automatically when `heat_action` and `cool_action` both exist. So the single-target behaviour is built on top: the logic owns the effective target and derives the climate's low/high setpoints from it. See "Single target" below and Q1 (answered: stock thermostat, range in Auto).
- **ESPHome's `web_server` is not available on `host`** (Dang's answer to Q2: browser play is on the Tab5's own page; the host sim is for HA and the tests).
- Climate values are °C inside ESPHome. The UI and HA show °F. Setpoints change in **whole °F** steps.
- The package contract in AGENTS.md: the logic package uses `room_temperature`, `room_humidity`, `relay_heat`, `relay_cool`, `relay_fan` and `relay_ob`, and provides `main_thermostat`. It never knows whether the sim or real hardware is loaded.
- The Tab5's `api:` and `wifi:` have `reboot_timeout: 0s` (on `pc/no-reboot-timeout`, approved). The sim entry point does the same for `api:`.
- The repo is public: no secrets, addresses or Wi-Fi details. The sim gets its own API key in `secrets.yaml` (a new `sim_api_encryption_key` line in `secrets.yaml.example`).

## How it behaves

### Equipment calls (PC, Mac agrees)

| Action | Relays on |
|---|---|
| Heating | W only. A gas furnace runs its own blower in heat (`fan_with_heating: false`). |
| Cooling | Y + G. The air handler needs G for the blower (`fan_with_cooling: true`). |
| Fan On (any mode, including Off) | G |
| Idle / Off | none (except G when the fan is On) |
| O/B | never on in M2 |

### Single target, Comfort, Eco and holds

- **Settings** (restored after reboot; ranges are a Mac call):
  - **Comfort target**: °F, whole degrees, 50–90°F.
  - **Eco offset**: N°F, default 4, 2–10°F.
- **The effective target** is the one temperature the thermostat is holding right now. It's the **big number on the screen** (Dang, via PC):
  - In a **hold**: the held temperature.
  - In **Comfort**: the Comfort target.
  - In **Eco**: Comfort − N in Heat, Comfort + N in Cool. In Auto the screen shows the Eco band edges.

  When Eco is on, the screen shows Comfort small, beside the big number (PC's screen spec).
- **− / + on the screen, or a setpoint change from HA or the web page, starts a hold** at that temperature. The hold lasts until the next schedule period starts or Resume schedule is pressed. The Comfort target and Eco offset settings are untouched. Example: in Eco at 68°, + gives a hold at 69° (Dang, via PC). The same applies in a Comfort period (Mac call, following Dang's "a manual change holds until the next period"). The Comfort target itself only changes through its setting, in HA or on the web page, and later in a settings screen.
- **Hold in Auto**: the held temperature becomes the centre of the normal ±1°F band, with no Eco widening. In Auto with Eco on, the first tap starts from the Comfort target. (Mac call.)
- The climate's internal low/high setpoints are always **derived from the effective target and the mode** (Mac call; the builder may refine the exact values within these rules):
  - **Heat:** heat to the effective target.
  - **Cool:** cool to the effective target.
  - **Auto:** low = target − 1°F, high = target + 1°F. In Eco without a hold, both move out by N. Each side keeps a small deadband and overrun, so a target of 72°F reads as "heat below about 71, cool above about 73" (PC relaying Dang).
- **A mode change mid-run** (ESPHome behaviour, kept; the screen's "Finishing up" line relies on it):
  - `main_thermostat` reports the new mode at once, but the action stays HEATING (or COOLING) until that call's minimum run ends. Switching to Off works the same way.
  - Then it passes through IDLE (for `min_idle_time`). The new call starts at the next update once its own minimum off time allows; `call_wait_reason` names the wait meanwhile.
  - A *manual* Heat→Cool switch gets no 30-minute changeover lockout, only the AC's minimum off. The lockout is for Auto's own switching. (Mac call.)
- **"Auto" is ESPHome's `HEAT_COOL` mode** (heat or cool between setpoints). ESPHome's `AUTO` mode is not offered.
- **What HA's card shows** (checked in HA's ESPHome integration, `climate.py` on HA `dev`). ESPHome marks this climate as *supporting* two setpoints, not *requiring* them. So HA's card shows **one number in Heat and Cool** (the effective target) and a **narrow range in Auto**. **Dang (Q1): the range in Auto is fine.** Stock ESPHome thermostat, no C++ wrapper.
- **Auto changeover lockout:** after a heat call ends, no cool call for at least 30 minutes, and the other way around. It's editable within 10–120 min (Mac call). This stops ping-ponging on top of ESPHome's forced pass through idle.
- **Comfort/Eco is always a `select` (`comfort_level`).** The screen and HA bind to it. If it can also be mirrored to the climate's standard `comfort` / `eco` presets without fighting the thermostat's own preset handling, do that too, so HA's card shows it (builder's call).

### Schedule (Dang, defaults are a Mac call)

- Periods per day type: Wake, Leave, Return, Sleep. Each has a **start time** (an ESPHome `datetime` time entity) and a **level** (`select`: Comfort / Eco). There are two day types, weekdays (Mon–Fri) and weekends (Sat–Sun): 16 settings in all, restored after reboot.
- Default times and levels: weekdays Wake 6:30 Comfort, Leave 8:30 Eco, Return 17:30 Comfort, Sleep 22:30 Eco. Weekends Wake 8:00 Comfort, Leave 10:00 Comfort, Return 17:00 Comfort, Sleep 23:00 Eco.
- The schedule **only switches Comfort ↔ Eco**. It never changes the mode or the Comfort target. Off stays Off.
- **Schedule on/off** switch (default on, restored).
- **Hold:** a manual temperature change (see above) or a manual Comfort/Eco switch starts a hold. The hold ends when the next period starts, which then applies its own level. A **Resume schedule** button ends the hold early. With the schedule off, a manual change simply stays: there is no hold and no "until".
- **What the screen needs as data, not just text** (from the PC's screen spec): the current period name, its level, the next period's start time, whether a hold is on, and the held temperature. A ready-made status text also exists for HA and the web page, e.g. "Eco until 5:30 pm" or "Holding 69° until 10:30 pm". Times use 12-hour format.
- **Clock:** the schedule uses the device clock (on the Tab5, the battery-backed RTC, then SNTP; on the host, the system clock), in America/New_York. If the clock isn't valid, the schedule pauses at the current level and says so in its status. Heating and cooling carry on regardless.
- **After a reboot** the schedule re-applies the current period's level. A hold doesn't survive a reboot. (Mac call: simplest, and a reboot is rare.)

### Safety

1. **Startup delay**: `startup_delay: true`, so after any boot, heat and cool wait out their minimum off times before the first call.
2. **Minimum run and off times** (editable, clamped; Mac call for the defaults and ranges, to be retuned from the equipment manuals at install):

   | Setting | Default | Allowed |
   |---|---|---|
   | Furnace minimum run | 3 min | 2–20 min |
   | Furnace minimum off | 3 min | 2–20 min |
   | AC minimum run | 5 min | 3–20 min |
   | AC minimum off | 5 min | 5–20 min |
   | Auto changeover lockout | 30 min | 10–120 min |

   They're HA/web `number` entities (category `config`, restored). The values are applied with the thermostat's runtime setters (`set_heating_minimum_run_time_in_sec` and friends). ESPHome adjusts a timer that's already running when its value changes. A value outside the allowed range can't be entered.
3. **Interlock: heat and cool never on together**, at three layers:
   - The thermostat only ever has one action, and goes through idle between heating and cooling (ESPHome behaviour).
   - The logic package's heat and cool actions turn the opposite relay off before turning theirs on.
   - An **independent watchdog** in the logic package, separate from the thermostat: if `relay_heat` and `relay_cool` are ever both on, it turns both off at once and latches an **`interlock_fault`** problem sensor. The latch holds until a reboot or a **Clear interlock fault** button press, and while it's latched no heat or cool call goes through.
   - All `relay_*` switches are `internal: true`, in both the sim and hardware packages (a contract addition). Nothing but the logic package can drive them: no HA toggle, no web page toggle. Read-only "call" sensors (below) show their state.
4. **Sensor sanity** (thresholds are a Mac call, tunable in one place). The logic package feeds the thermostat a *checked* temperature, not `room_temperature` directly. A reading counts as bad when:
   - it's NaN or missing, or no new reading has arrived for 2 minutes;
   - it's outside 2–40°C (36–104°F);
   - it hasn't changed at all for 30 minutes. (The SHT40 always has a little noise, so an identical value for that long means a stuck sensor. The sim adds similar noise.)

   A single-reading jump of more than 2°C is held back for one more reading before it's believed: a spike is filtered, a real change gets through. On a bad reading:
   - the checked temperature becomes NaN, and a **`sensor_fault`** problem sensor turns on at once;
   - ESPHome's thermostat asks for the OFF action, so no new call starts;
   - **a call already running still finishes its minimum run time** (at most 5 min for the AC, 3 min for the furnace), because ESPHome's switch to OFF waits for the run timers (`idle_action_ready_`, checked in the 2026.10.1 source). **Dang (Q3): accepted.** No custom early cut.

   After **5 minutes** of good readings the fault clears by itself and normal control resumes. Minimum off times still apply, so the compressor can't short-cycle on recovery. Humidity faults only make humidity unknown; they never affect control.
   - The interlock fault is different: it **cuts both relays at once**, minimum run or not. Two calls together is the one thing worse than a short cycle. (Mac call.)
5. **No reboot on HA or Wi-Fi loss** (see Constraints).
6. **Nothing in the logic depends on HA, the API, Wi-Fi or SNTP being up.**

### Entities the screen and HA can use (contract additions for M3 and HA)

Final names are the builder's, but the ids are fixed so the PC can build the screen against them. Entities that HA or the web page can change are restored after a reboot.

| id | type | what |
|---|---|---|
| `main_thermostat` | climate | the thermostat (existing contract). Modes OFF / HEAT / COOL / HEAT_COOL; fan modes AUTO / ON. |
| `effective_target` | sensor (°F) | the big number: the temperature being held right now. In Auto with Eco and no hold, the band centre (the screen shows the edges from `effective_low` / `effective_high`). |
| `effective_low`, `effective_high` | sensor (°F) | the band edges in Auto |
| `set_target` | number (°F, step 1, 50–90) | what − / + and HA writes go to: setting it starts a hold at that value (or just sets it, with the schedule off) |
| `comfort_target` | number (°F, step 1, 50–90) | the Comfort setting |
| `eco_offset` | number (°F, 2–10) | how far Eco drifts |
| `comfort_level` | select: Comfort / Eco | the current level; a manual change starts a hold, **but only when the value actually changes**. A template select fires `on_value` again when it's set to the same option, so re-tapping the lit pill must not start a hold. The same goes for `set_target` set to the current effective target. |
| `schedule_enabled` | switch | schedule on/off |
| `schedule_hold` | binary_sensor | a manual hold is active |
| `schedule_period` | text_sensor | Wake / Leave / Return / Sleep (empty with the schedule off or paused) |
| `schedule_next_change` | text_sensor | next period's start, 12-hour, e.g. "10:30 pm" |
| `schedule_status` | text_sensor | ready-made text, e.g. "Eco until 5:30 pm", "Holding 69° until 10:30 pm", "Schedule paused: clock not set" |
| `resume_schedule` | button | end the hold |
| `call_wait_reason` | text_sensor | why the room is off target but nothing is running: "Starting up", "Short-cycle protection", "Changeover wait", "Sensor fault", "Interlock fault", or empty |
| `action_elapsed` | sensor (s) | seconds since the current heating/cooling/idle action began, published at once on each action change and every 30 s after, for "18 min so far". (Not an epoch timestamp: a float sensor only holds those to about ±2 min.) |
| `checked_temperature` | sensor (°F) | the sanity-checked room temperature the thermostat acts on; the screen's big room number should use it |
| `sched_{weekday,weekend}_{wake,leave,return,sleep}_time` | datetime (time) | period start times |
| `sched_{weekday,weekend}_{wake,leave,return,sleep}_level` | select | Comfort / Eco per period |
| `heat_min_run`, `heat_min_off`, `cool_min_run`, `cool_min_off`, `changeover_lockout` | number (min) | safety timers |
| `sensor_fault` | binary_sensor (problem) | bad temperature reading, calls stopped |
| `interlock_fault` | binary_sensor (problem) | heat+cool caught together, latched |
| `clear_interlock_fault` | button | reset the latch |
| `call_heat`, `call_cool`, `call_fan` | binary_sensor | read-only W / Y / G state, for the screen, HA history and the sim page |

The current action (heating/cooling/idle) comes from `main_thermostat`'s action. The fan's state always comes from `call_fan`, because ESPHome only reports a fan action in fan-only mode, which we don't use, while G runs with Fan On in any mode, including Off.

## Virtual house (Dang: simple, with knobs)

A `sim` package that provides the contract ids `room_temperature`, `room_humidity` and `relay_*`:

- **Model** (Mac call for the defaults): `dT/dt = (T_outdoor − T) / τ + heat_rate·W + cool_rate·Y`. Defaults: τ = 8 h, furnace +10°F/h, AC −5°F/h. The room starts at 68°F. It steps every second and publishes `room_temperature` every 10 s with about ±0.05°C noise. G alone doesn't change the temperature.
- **Knobs in the browser and HA**: outdoor temperature (°F); weather = Fixed / Winter day (outdoor follows a daily curve, about 25–45°F) / Summer day (about 70–95°F); leakiness (τ); furnace and AC strength; humidity (default 45%).
- **Break-it-on-purpose control** (`select`): None / Unplugged (stops publishing) / Frozen (repeats the last value with no noise) / Out of range (publishes 60°C) / Spike (one 10°C jump).
- **Relays** are template switches, optimistic, `restore_mode: ALWAYS_OFF`, `internal: true`. The `call_*` sensors show them.
- **Test-only hooks** live in the test entry point, never in the logic or sim packages the Tab5 uses: forcing both relays on (for the interlock test), setting the schedule's clock, and scaling the physics and the timers.

## Entry points and files (ownership per AGENTS.md)

| File | What | Owner |
|---|---|---|
| `tab5-thermostat/thermostat/logic.yaml` (plus small C++ helpers if needed) | climate, safety, Comfort/Eco, schedule | Mac |
| `tab5-thermostat/sim/virtual-house.yaml` | the virtual house | Mac |
| `tab5-thermostat/main-thermostat-sim.yaml` | `host` entry: logic + sim, `api` (own key, `reboot_timeout: 0s`), host time in America/New_York, no `web_server` (not available on host). Device name `main-thermostat-sim`, shown as "Main Thermostat (Sim)" so HA keeps it apart from the real one. | Mac |
| `tab5-thermostat/tests/` | the test entry point (short timers, fast physics, hooks) and the scenario tests | Mac |
| `tab5-thermostat.yaml` | adds the logic + sim packages so the Tab5 runs the same logic against the virtual house until M4 | PC (Mac sends the change for review) |
| `docker-compose.yml`, `home-assistant/` | a way to run the sim next to HA if needed; an HA notification automation for `sensor_fault` / `interlock_fault` | PC (Mac asks) |

**Running the sim:** build and run it with the same pinned ESPHome image, on the Mac for development (published ports for the API and the web page). It must work the same way on the PC. For the HA demo, either HA (on the PC) connects to the Mac's sim over Tailscale, or the PC runs the sim next to HA. Builder's call, agreed with the PC agent.

## Automated tests

Python scenario tests talk to the test build over ESPHome's native API (`aioesphomeapi`), using pytest in a container, so nothing gets installed on the Mac. Each one sets up a situation through the sim knobs and hooks, then checks the relay call sensors and the fault sensors. Required scenarios:

1. Boot: all relays off, and no heat or cool call until the startup delay has passed.
2. Heat calls W only, cool calls Y+G, fan On calls G alone, `relay_ob` never turns on.
3. Minimum run: a target change mid-run doesn't stop the equipment before its minimum run time.
4. Minimum off: no restart before the minimum off time (short-cycle protection).
5. Auto: heats and cools toward one target, idles inside the band, and honours the changeover lockout.
6. Interlock: forcing both relays on trips the watchdog within a second; both go off, the fault latches, and calls stay blocked until cleared.
7. Sensor faults (unplugged, frozen, out of range): `sensor_fault` turns on at once, no new call starts, and a running call ends no later than its minimum run time (Q3). Recovery comes after 5 minutes of good readings, and the AC minimum off is still honoured. A single spike does not trip a fault.
8. Eco: the band moves N°F the saving way in Heat, Cool and Auto, and `effective_target` follows it.
9. Schedule: period changes switch the level. A `set_target` change or a Comfort/Eco switch holds until the next period, with `comfort_target` untouched. Resume ends a hold. With the schedule off, nothing switches and there's no hold. An invalid clock pauses it. `schedule_period`, `schedule_next_change` and `call_wait_reason` report correctly.
10. Timer settings outside their range are refused or clamped.
11. Persistence: mode, Comfort target, Eco offset, schedule and timers survive a restart.

## Left to the builder

- The exact YAML and C++ structure, including how the derived setpoints are kept in sync and whether Comfort/Eco is a climate preset or a `select`.
- Deadband and overrun values within the behaviour above.
- How the sim runs in Docker on the Mac, and how the tests get time control.
- Friendly names, icons and entity categories.
- **Packaging rule (from the PC's M3 work):** write every `esphome: on_boot:` as a list item (`on_boot: [- priority: X, then: ...]`), never a mapping. ESPHome's package merge folds mapping-form `on_boot` blocks from different packages into one automation, keeping only the last package's priority.

## Answered by Dang after the builder check

- **Q1. HA's card in Auto:** a narrow range is fine. Stock ESPHome thermostat, no C++ wrapper.
- **Q2. Browser play:** on the Tab5's own web page (Tab5 running logic + virtual house). The host sim shows up in HA and runs the tests. No separate web page for the sim.
- **Q3. Bad sensor mid-run:** the running call finishes its minimum run (at most 5 min). No new call starts, and the alert shows at once.

## Calls I made that you may want to check

- Setpoints 50–90°F in whole degrees; Eco offset 2–10°F (default 4).
- Timer defaults and allowed ranges (the table under Safety), plus the 30-minute Auto changeover lockout.
- Any − / + or HA setpoint change is a hold until the next period, in Comfort periods too. Comfort itself only changes in its setting.
- In Auto, a hold is a ±1°F band around the held temperature, with no Eco widening.
- A hold doesn't survive a reboot; the schedule re-applies the current period.
- Sensor sanity thresholds: 2 min stale, 2–40°C, 30 min frozen, 5 min of good readings to recover.
- An interlock fault cuts both relays at once, ignoring minimum run, and latches until cleared.
- Default schedule times and levels.
- The tests use shortened timers and sped-up physics; the shipped values stay real.
