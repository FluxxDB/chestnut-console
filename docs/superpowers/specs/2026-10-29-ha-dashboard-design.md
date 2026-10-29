# Chestnut dashboard in Home Assistant (M2 addendum)

*Design, 2026-10-29. Owner: pc-chestnut-console. Status: mockup approved by Dang. Builder check by mac-chestnut-console done (8 points, settled below). Document approved by Dang 2026-10-29.*

Marks: **Dang** = he decided it; **PC call** = my default, open to change.

## Why

Dang wants one page on his phone and PC to watch and control the Main Thermostat, and to *see* the simulated house: a top-down room where warm and cool air visibly spreads, with the furnace, AC and other equipment around it. It started as a redesign of the Tab5's own web page. That page only works on the house Wi-Fi, though, and Home Assistant's app already solves remote access, login and notifications. So **Dang** moved the whole thing into Home Assistant and asked for **all of HA restyled** in the Axiom design (`tab5-thermostat/docs/design/axiom/`).

## Goals

1. A custom **"Chestnut" dashboard** that **replaces HA's Overview** (Dang: opening HA, app or browser, lands on it, with no stock dashboard left over), laid out like the approved mockup: Home, Schedule, Simulation and System tabs.
2. A **room view** with a live 2D heat-flow animation, driven by the thermostat's real state. It's honest: the field's average always equals the measured room temperature.
3. **Every control a user needs** that the Tab5's own page exposes (list below). Debug-only entities stay off the page.
4. **HA itself in Axiom**: sidebar, settings pages, more-info pop-ups and dialogs.
5. **Fault alerts** to Dang's phone through the HA app. This is the notification the M2 hand-off asked for.

## Non-goals and anti-goals

- **Non-goal:** changing the Tab5's own web page or the wall console. The wall console keeps its Co2 look.
- **Non-goal:** remote access setup. **Dang:** decide later (he has WireGuard on the future HA server).
- **Non-goal:** new thermostat behaviour. The dashboard only reads the M2 contract and writes what HA's card could already write.
- **Anti-goal:** the dashboard becomes something heating depends on. HA or the dashboard down must never matter to the thermostat. Everything here is display and remote control.
- **Anti-goal:** a pretty picture that lies. The heat map must never show heating that isn't happening.

## The approved mockup

`docs/design-mockups/ha-dashboard/` holds the approved artboards: `Main.dc.html` (desktop, all tabs), `Phone.dc.html` and `Theme.dc.html`. Live copy: https://claude.ai/artifact/3rMAYpPLmZPuwcqRumrxgv (private to Dang). The files use a mockup format (`<x-dc>`, `{{holes}}`, a `DCLogic` class), but their markup, inline styles and JS logic port directly. **The mockup is the visual spec.** Where this document and the mockup disagree, this document wins.

## Style (Axiom, as Dang approved it)

- Dark only. Page `#000000`, cards `#111111`, the thermostat card and dialogs `#191919`, hairlines `#202020`, outlines `#3a3a3a`. Text: `#eeeeee`, secondary `#b4b4b4`, labels `#7e7e7e` (at least 4.5:1 on black, so not `#606060`).
- **JetBrains Mono** everywhere, standing in for Axiom's paid BerkeleyMono, self-hosted (no CDN), with its OFL licence alongside. Uppercase 12px letter-spaced labels. Big numbers (64px target, 48px room) go past Axiom's 32px cap on purpose, for readability.
- 2px corners. 9999px only for tiny badges. No shadows, no gradients except data.
- **Ember `#da5c2c`** only for heat data and the one primary action per view ("Resume schedule →"). **Blue `#2a7fff`** only for cooling data. Selected segment = white fill with black text. Status uses symbols (▲ ▼ · ⊘ ✓ ⚠), not coloured badges.
- **Heat-map scale (Dang):** a two-colour gradient from blue at 60°F to Ember at 80°F, blended in OKLab, smoothstepped, at 0.9 opacity. Air past either end (supply air) clamps to the full colour. Legend "60° [scale] 80°F".

## Layout

### Frame

The Chestnut dashboard **is HA's main (Overview) dashboard**, in YAML mode from the repo, with a single panel view hosting one custom element that draws the whole page from the mockup: header, `~/chestnut/main-thermostat` prompt, title (no blinking cursor, **Dang**), schedule line, clock, connection state, and its own tab bar. **PC call:** one panel card, so the tabs, the phone hiding and the layout can match the mockup exactly; HA's native view tabs can't hide a tab by screen width. HA's own sidebar and app bar stay HA's, themed.

### Responsive (Dang)

Desktop and laptop: as in `Main.dc.html`. At **≤ 860px**:
- the **Simulation tab is hidden**;
- the **room view is hidden**, so Home opens on the thermostat card;
- everything else stacks.

### Home tab

1. **Room view** (desktop only): top-down room. Windows on the outside wall, two supply vents on the top wall and one on the right, a return grille, the Tab5 on the right wall with the sensor reading. Readout row: room average, target, supply air, airflow, humidity.
   - **Outdoor column:** outdoor °F, weather, AC outdoor unit (fan spins about its centre while Y is on, blue outline).
   - **Equipment closet column:** cooling coil (Y, blue while cooling), interlock line ("armed · never both", or tripped), furnace (W, Ember outline and flame while firing), blower (G, spins while air moves).
2. **Thermostat card:** label (COMFORT TARGET / ECO TARGET / HOLD / TARGET, plus "Target" for the schedule-off manual number), − / + (target, 50–90), status line, MODE Off/Heat/Cool/Auto, FAN Auto/On, LEVEL Comfort/Eco, schedule line, and **Resume schedule →** only while a hold is on.
3. **Last 12 hours:** room-temperature line with the dashed target, log-bars for heat W / cool Y / fan G (6-minute buckets), and runtime totals.
4. **Today:** a 24-hour Comfort/Eco bar for today's day type with a now-marker, linking to Schedule. **Status:** equipment, interlock, sensor, HA connection, linking to System.

### Schedule tab

- **Editor:** on/off switch; Weekday/Weekend toggle; per period (wake, leave, return, sleep) a time input and a Comfort/Eco select; Comfort temperature and Eco offset steppers. The current period is marked "›". Rows dim while the schedule is off.
- **The week:** Mon–Fri and Sat–Sun 24-hour bars, white for Comfort and `#3a3a3a` for Eco, updating live.
- No holds card (**Dang** removed it to give the editor room).

### Simulation tab (desktop only)

The room view plus a panel: outdoor temperature, weather, sensor fault, insulation (hours), furnace rate, AC rate, humidity, and the one-line physics. "BENCH ONLY" label. At M4 the tab disappears (below).

### System tab

- **Safety:** furnace and AC minimum run/off with countdown bars, interlock, sensor. **Countdowns (builder check 2):** M2 publishes no remaining times. Bars come from the device's own `action_elapsed`: the running unit's min run, and the idle unit's min off, counted from when that action began (published every 30 s and interpolated in the browser). That survives HA restarts. The startup delay and the changeover lockout show as `call_wait_reason` text, not bars. Where a bar can't be known, it shows "—"; editable timer settings (minutes, with the M2 limits); Clear interlock fault (enabled only while latched).
- **Alerts · Home Assistant app:** switches for sensor fault, interlock fault, thermostat offline for 10 min (**PC call:** these three).
- **Wall screen:** brightness in use, dim brightness, dark theme ("follows sunset and sunrise").
- **Device:** name, address, firmware, Wi-Fi, uptime, clock state.
- **Event log:** recent furnace/AC on/off, sensor faults and recoveries, interlock trips, holds, schedule changes, newest first.

### HA in Axiom (Theme.dc.html)

An HA theme `axiom`, set as the default for all users, so settings, history, logbook, more-info and dialogs follow the style. Primary action = Ember; switches and selections = white on black; surfaces, text and font as above.

## Data: entity bindings

All of these are the M2 contract on the Tab5, through HA's ESPHome integration.

- **Finding entities (PC call, builder check 1):** don't hard-code entity ids. Resolve each one through HA's entity registry by the ESPHome object id within the Tab5's device. HA keeps old registry ids from M1 and the M3 stub, and the climate may come out as `climate.main_thermostat`. Only the Tab5 device is targeted: the host sim ("Main Thermostat (Sim)") is a dev toy.
- **HA domains:** ESPHome `datetime` (type time) appears in HA as `time.` (write with `time.set_value`), and `text_sensor` appears as `sensor.`.
- **Units (builder check 7):** read each entity's unit and convert, so the page always shows °F and writes `set_target` in the entity's unit, whatever HA's unit system is.

| Dashboard element | Reads | Writes |
|---|---|---|
| Room avg, sensor reading | `sensor.checked_temperature` (°F) | |
| Heat flow, equipment, log-bars | `binary_sensor.call_heat/cool/fan` | |
| Status word / subline | climate `hvac_action`, mode, faults, `call_wait_reason`, `action_elapsed`, `call_heat/cool`. **The wall console's rules, which win over the mockup:** any fault (sensor *or* interlock) → PAUSED, with "Finishing up · stops soon" while a call is still on. Mode switched mid-call → "Finishing up · stops soon". Idle off target → "Waiting · <reason>". | |
| Target, label, band | `sensor.effective_target/low/high`, `select.comfort_level`, `binary_sensor.schedule_hold`, `binary_sensor.manual_target`; the hold kind comes from `schedule_status`'s documented formats ("Holding 69° until …" = temperature hold, "Holding Eco until …" = level hold) | − / + → `number.set_target` |
| Mode / fan | climate | `climate.set_hvac_mode`, `climate.set_fan_mode` |
| Level | `select.comfort_level` | `select.select_option`. **Follows M2, not the mockup (builder check 3):** a hand-picked level starts a level hold (the mockup cleared it). While `manual_target` is on, re-picking the lit level is sent and drops the manual number. Otherwise a lit pill sends nothing. |
| Resume | | `button.resume_schedule` |
| Schedule | `switch.schedule_enabled`, `time.sched_*_time`, `select.sched_*_level`, `sensor.schedule_period/next_change/status` | the same entities |
| Comfort / Eco offset | `number.comfort_target`, `number.eco_offset` | the same |
| Timers | `number.heat_min_run`, `heat_min_off`, `cool_min_run`, `cool_min_off`, `changeover_lockout` | the same |
| Interlock / sensor | `binary_sensor.interlock_fault`, `binary_sensor.sensor_fault` | `button.clear_interlock_fault` |
| Humidity | `sensor.room_humidity` | |
| Simulation | the sim's current outdoor temperature (a new sim sensor, see below), `number.sim_outdoor_f` (the Fixed setting), `select.sim_weather`, `select.sim_fault`, `number.sim_tau_h`, `sim_heat_fph`, `sim_cool_fph`, `sim_humidity` | the same |
| Wall screen | `number.screen_brightness`, `number.dim_brightness`, `switch.dark_theme` | the same |
| Device | `sensor.ip_address`, the HA device registry (firmware), uptime and Wi-Fi signal (to add, below), clock state (to add, below) | |
| Last 12 hours | HA recorder history for the call sensors, checked temperature and effective target | |
| Event log | HA logbook for those entities | |

**Not shown (Dang: drop what a user doesn't need):** `room_temperature` (°C), `sim_room_f` (except as a fallback outdoor/room source in Simulation), the backlight light, screen idle time, the raw `effective_*`/`call_*`/`action_elapsed` values as numbers, `manual_target` as a raw flag, battery voltage/current.

**Small additions (PC-owned, not contract changes):**
- an ESPHome `uptime` sensor, Wi-Fi signal and a "Clock Valid" binary sensor on the Tab5 (`hardware/tab5-base.yaml`), for Device. The Wall-screen and IP entities already exist on the Tab5 (PC-owned `ui/` and hardware packages), not in M2. The host sim doesn't have them, which is fine: it isn't targeted;
- **asked of the Mac agent (sim package):** a sensor with the sim's current outdoor °F. Today `sim_outdoor_f` is only the Fixed setting, and the Winter/Summer curve is internal (builder check 4). Until it exists, the outdoor readout shows the Fixed value with "fixed" or "—";
- HA `input_boolean` helpers for the three alert switches.

## Room view behaviour

- A 64×40 grid of temperatures, stepped once per animation frame in the browser:
  - advection from the vent jets toward the return while air moves (any of W, Y, fan On), with a small time-varying swirl;
  - diffusion;
  - supply air injected at the vents while W (108°F) or Y (55°F) is on;
  - leakage toward outdoor at the walls, stronger at the windows;
  - then a uniform shift so the **field mean equals `checked_temperature`**.
- Drawn upscaled with smoothing and a soft blur, over a faint dot grid.
- **Honest readouts (builder check 8):** the readout row shows only measured or derived values: room average, target, humidity, airflow (on/still, from the calls). The modelled supply-air temperature is **not** shown as a reading. The mockup's "supply air 108°F" is dropped.
- While the sim package is loaded, the room and outdoor readouts carry a small "SIM" tag.
- **Outdoor source:** `sim_outdoor_f` while the sim exists. At M4: HA's weather entity (`weather.forecast_home`, already used by the console), or a fixed fallback with "outdoor —".
- Sensor fault: the field freezes at the last good value (no false heating) and the room view shows the fault. The heat map follows the calls, never the target.
- The constants (supply temperatures, rates, grid size) are display tuning, kept in one place.
- **M4 (Dang: live system view):** when the `sim_*` entities are gone from the registry or orphaned (no longer provided by the device), not merely `unavailable` (that also happens when the Tab5 is just offline), the Simulation tab and the BENCH controls disappear. The room view stays as the live view of the real house.

## Alerts

- HA automations notify Dang's phone (HA Companion app, `notify.mobile_app_<phone>`) when, and only while, the matching `input_boolean` is on:
  - `sensor_fault` turns on;
  - `interlock_fault` turns on;
  - the thermostat is `unavailable` for 10 minutes.
- Each also sends a recovery notice. Messages are short and plain ("Main Thermostat: temperature sensor problem. Heating and cooling paused.").
- Until the Companion app is set up, the automations also create a persistent notification in HA.

## Constraints

- Everything lives in the repo under `home-assistant/config/` (theme, dashboard YAML, custom card JS, fonts, automations, helpers), so the house VM gets it with `git pull` and `docker compose up`. No HACS, no build step, no CDN: plain ES modules served from `/local/`. **PC call:** keeps it reviewable and offline-safe.
- HA 2026.10.4 (pinned in compose). Entity ids follow the M2 contract; nothing is renamed.
- Public repo: no secrets, addresses or tokens in it. The phone's notify service name comes from HA, not the repo (or from a helper/secret).
- The dashboard must work with HA reached over plain local HTTP now, and remote later.
- Must not slow the Tab5. Everything is computed in the browser or HA; the Tab5 serves only its normal API.

## Left to the builder

- How to split the custom element into files and modules, the exact HA theme variable list, how to fetch history and logbook (websocket API), the tests (a headless-browser check against the dev HA is suggested), and the debounce on − / + (match the wall console: about 1.5 s).
- Anything the mockup shows that isn't covered here: follow the mockup.
