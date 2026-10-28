# Milestone 2: Main Thermostat logic and virtual house

*Design, 2026-10-28. Owner: mac-chestnut-console (branch `mac/thermostat-logic`). Status: draft, waiting on Dang's approval.*

Decisions are marked by who made them: **Dang** (asked in a survey), **PC** (pc-chestnut-console, Dang delegated the call), or **Mac call** (my default, open to change while you read this).

## Why

The Main Thermostat has to keep the house comfortable on its own. Home Assistant and Wi-Fi are extras: if either goes down, heating and cooling carry on (AGENTS.md, core decision). Nothing can be wired until Dang's next visit, so the logic is built and proven now against a **virtual house**: a simulated room whose temperature drifts toward the outdoor temperature and responds to virtual furnace, AC and fan relays. When the bench parts arrive (M4), the sensor and relay packages are swapped for real ones and the logic package doesn't change.

## What done looks like (Dang)

1. **Play with it in a browser.** The virtual Main Thermostat runs on a computer (ESPHome `host` platform) and serves the same kind of web page the Tab5 does. You can set the mode and target, change the outdoor temperature, break the sensor on purpose, and watch the virtual relays react.
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
- **ESPHome forces two setpoints when the thermostat has both heat and cool actions.** `thermostat/climate.py` sets `supports_two_points` automatically when `heat_action` and `cool_action` both exist. So the single-target behaviour has to be built on top: a **Comfort target** that we own, with the climate's low/high setpoints derived from it. See "Single target" below and open question Q1.
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

### Single target, Comfort and Eco

- **Source of truth: the Comfort target** (°F, whole degrees, 50–90°F, restored after reboot). It is the big number on the screen and what the user changes. (Range and step: Mac call.)
- **Eco offset**: N°F, default 4, editable 2–10°F (Mac call for the range).
- The climate's internal setpoints are derived from Comfort, the mode and Comfort/Eco (Mac call; the builder may refine the exact values within these rules):
  - **Heat:** heat to Comfort, or to Comfort − N in Eco.
  - **Cool:** cool to Comfort, or to Comfort + N in Eco.
  - **Auto:** the low setpoint is Comfort − 1°F and the high setpoint is Comfort + 1°F, both moved out by N in Eco. Each side keeps a small deadband and overrun so a target of 72°F reads as "heat below about 71, cool above about 73" (PC relaying Dang).
- **Auto changeover lockout:** after a heat call ends, no cool call for at least 30 minutes, and the other way around. It's editable within 10–120 min (Mac call). This stops ping-ponging on top of ESPHome's forced pass through idle.
- **Manual changes from HA or the web page**: a change to a climate setpoint from HA's card is read as "set Comfort to this and hold". It also leaves Eco, because the person evidently wants that temperature now. (Mac call.)
- Comfort/Eco shows in HA, ideally as the climate's standard `comfort` / `eco` presets so HA's card shows and switches it natively. If that fights the thermostat component's own preset handling, a `select` is fine. (Builder's call.)

### Schedule (Dang, defaults are a Mac call)

- Periods per day type: Wake, Leave, Return, Sleep. Each has a **start time** (an ESPHome `datetime` time entity) and a **level** (`select`: Comfort / Eco). There are two day types, weekdays (Mon–Fri) and weekends (Sat–Sun): 16 settings in all, restored after reboot.
- Default times and levels: weekdays Wake 6:30 Comfort, Leave 8:30 Eco, Return 17:30 Comfort, Sleep 22:30 Eco. Weekends Wake 8:00 Comfort, Leave 10:00 Comfort, Return 17:00 Comfort, Sleep 23:00 Eco.
- The schedule **only switches Comfort ↔ Eco**. It never changes the mode or the Comfort target. Off stays Off.
- **Schedule on/off** switch (default on, restored).
- **Hold:** any manual change (Comfort target, Comfort/Eco, or a setpoint from HA) starts a hold. The hold ends when the next period starts, which then applies its own level. A **Resume schedule** button ends the hold early. A status text says what's happening, e.g. "Eco until 17:30 (schedule)" or "Hold: Comfort 70°F until 22:30".
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

   A single-reading jump of more than 2°C is held back for one more reading before it's believed: a spike is filtered, a real change gets through. On a bad reading, the checked temperature becomes NaN. ESPHome's thermostat then goes straight to the OFF action, all calls stop, and a **`sensor_fault`** problem sensor turns on. After **5 minutes** of good readings it clears by itself and normal control resumes. Minimum off times still apply, so the compressor can't short-cycle on recovery. Humidity faults only make humidity unknown; they never affect control.
5. **No reboot on HA or Wi-Fi loss** (see Constraints).
6. **Nothing in the logic depends on HA, the API, Wi-Fi or SNTP being up.**

### Entities the screen and HA can use (contract additions for M3 and HA)

Final names are the builder's, but the ids are fixed so the PC can build the screen against them. Entities that HA or the web page can change are restored after a reboot.

| id | type | what |
|---|---|---|
| `main_thermostat` | climate | the thermostat (existing contract) |
| `comfort_target` | number (°F, step 1, 50–90) | the single target |
| `eco_offset` | number (°F, 2–10) | how far Eco drifts |
| `comfort_level` | select or climate preset: Comfort / Eco | the current level |
| `schedule_enabled` | switch | schedule on/off |
| `schedule_status` | text_sensor | e.g. "Eco until 17:30 (schedule)" |
| `schedule_hold` | binary_sensor | a manual hold is active |
| `resume_schedule` | button | end the hold |
| `sched_{weekday,weekend}_{wake,leave,return,sleep}_time` | datetime (time) | period start times |
| `sched_{weekday,weekend}_{wake,leave,return,sleep}_level` | select | Comfort / Eco per period |
| `heat_min_run`, `heat_min_off`, `cool_min_run`, `cool_min_off`, `changeover_lockout` | number (min) | safety timers |
| `sensor_fault` | binary_sensor (problem) | bad temperature reading, calls stopped |
| `interlock_fault` | binary_sensor (problem) | heat+cool caught together, latched |
| `clear_interlock_fault` | button | reset the latch |
| `call_heat`, `call_cool`, `call_fan` | binary_sensor | read-only W / Y / G state, for the screen, HA history and the sim page |

The current action (heating/cooling/idle) comes from `main_thermostat`'s action, which HA and the screen already read.

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
| `tab5-thermostat/main-thermostat-sim.yaml` | `host` entry: logic + sim, `api` (own key, `reboot_timeout: 0s`), `web_server` v3 with digest auth, host time in America/New_York. Device name `main-thermostat-sim`, shown as "Main Thermostat (Sim)" so HA keeps it apart from the real one. | Mac |
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
7. Sensor faults (unplugged, frozen, out of range): calls stop at once and `sensor_fault` turns on. Recovery comes after 5 minutes of good readings, and the AC minimum off is still honoured. A single spike does not trip a fault.
8. Eco: the band moves N°F the saving way in Heat, Cool and Auto.
9. Schedule: period changes switch the level; a manual change holds until the next period; Resume ends a hold; with the schedule off, nothing switches; an invalid clock pauses it.
10. Timer settings outside their range are refused or clamped.
11. Persistence: mode, Comfort target, Eco offset, schedule and timers survive a restart.

## Left to the builder

- The exact YAML and C++ structure, including how the derived setpoints are kept in sync and whether Comfort/Eco is a climate preset or a `select`.
- Deadband and overrun values within the behaviour above.
- How the sim runs in Docker on the Mac, and how the tests get time control.
- Friendly names, icons and entity categories.

## Open questions for Dang

- **Q1. HA's thermostat card in Auto.** Because of ESPHome's forced two setpoints, HA's card in Auto will show a narrow range (two handles, e.g. 71–73°F) that move together, instead of one number. Heat and Cool show one number. Showing one number in Auto too needs a small custom C++ wrapper around ESPHome's thermostat. *(Asked of Dang after the builder check.)*
