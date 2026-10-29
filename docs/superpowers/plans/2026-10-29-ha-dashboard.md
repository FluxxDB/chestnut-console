# Chestnut HA Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Home Assistant's Overview with the Axiom-styled "Chestnut" dashboard (Home, Schedule, Simulation and System tabs, plus a live heat-flow room view), theme all of HA in Axiom, and add phone alerts for thermostat faults.

**Architecture:**
- **Pure logic:** dependency-free ES modules under `home-assistant/config/www/chestnut/lib/`, unit-tested with `node --test`.
- **One custom element:** `<chestnut-dashboard>` renders the whole page in a single panel view and talks to HA only through the `hass` object, via a thin adapter.
- **Integration tests:** a throwaway HA container on port 8124 and the M2 host sim, with Playwright driving the real page.

**Tech Stack:** HA 2026.10.4 (YAML dashboard + theme + automations), plain ES modules (no build step, no CDN), Node 24 `node:test`, Playwright (Python, Docker image), ESPHome 2026.10.1 host sim via the `esphome-host` compose service.

**Spec:** `docs/superpowers/specs/2026-10-29-ha-dashboard-design.md` (approved by Dang). Visual spec: `docs/design-mockups/ha-dashboard/*.dc.html`. The spec wins where they differ.

## Global Constraints

- **Repo layout:** everything under `home-assistant/config/` and committed (un-ignore the new paths in `.gitignore`). No HACS, no build step, no CDN; fonts self-hosted.
- **Overview replacement:** `lovelace: dashboards: lovelace: {mode: yaml, filename: dashboards/chestnut.yaml, title: Chestnut, show_in_sidebar: true}` replaces Overview. **Not** top-level `lovelace: mode: yaml` (deprecated in 2026.8).
- **Resources:** `lovelace: resource_mode: yaml` with `resources: [{url: /local/chestnut/chestnut-dashboard.js, type: module}]`.
- **Colours** (exact): page `#000000`; cards `#111111`; thermostat card/dialogs `#191919`; hairlines `#202020`; outlines `#3a3a3a`; text `#eeeeee` / `#b4b4b4` / labels `#7e7e7e`; Ember `#da5c2c` (heat data + one primary action per view); blue `#2a7fff` (cooling data); selected segment white fill + black text.
- **Type and shape:** JetBrains Mono everywhere (OFL licence file shipped beside the woff2). 2px corners. No shadows.
- **Heat scale:** two colours, `#2a7fff` at 60°F to `#da5c2c` at 80°F, clamped, OKLab blend, smoothstep, alpha 0.9.
- **Phone:** at ≤ 860px the Simulation tab and the room view are hidden.
- **Entities:** resolved through the entity registry by ESPHome object id within the target device (the card option `device_name`, default `"Main Thermostat"`). Never hard-coded entity ids. ESPHome `datetime` → HA `time.` (`time.set_value`); `text_sensor` → `sensor.`.
- **Units:** always show °F, converting from each entity's `unit_of_measurement`; write `set_target` in the entity's unit.
- **Status rules** (the wall console's, not the mockup's):
  - any fault → PAUSED, plus "Finishing up · stops soon" while a call is on;
  - a mode change mid-call → "Finishing up · stops soon";
  - idle and off target → "Waiting · <reason>".
- **No fake readings:** no supply-air readout; a "SIM" tag on the room and outdoor readouts while `sim_*` entities exist.
- **− / +:** debounced 1.5 s before writing `number.set_target`; a burst that nets zero writes nothing.
- **Public repo:** no secrets, tokens or addresses. The phone's notify service is chosen in HA (a `notify` target helper or the persistent notification), never hard-coded.
- **No AI co-author lines in commits.**

## Review Focus

1. **The Tab5 goes offline** (entities `unavailable`): show "—" and an "offline" status, never the last values as if live. The Simulation tab must **not** disappear. *Test:* Task 3 adapter `unavailable_is_dash`; Task 6 integration `offline_shows_dashes` (stop the sim).
2. **HA's websocket reconnects or the page is backgrounded on a phone:** the animation and subscriptions resume with no duplicate timers. History reloads. *Test:* Task 5 `reconnect_rebinds_once`.
3. **HA uses metric units:** values still show °F, and writes land in °C correctly. *Test:* Task 3 `units_metric_roundtrip`.
4. **A fresh HA with no history yet:** the runtime chart and event log show "no data yet" instead of throwing. *Test:* Task 5 `empty_history_renders`.
5. **Rapid − / + taps or a +/− burst:** exactly one write of the final value, or none if the burst nets zero. *Test:* Task 2 `debounce_nets_zero`; Task 5 `five_taps_one_write`.

---

## File Structure

| File | Responsibility |
|---|---|
| `home-assistant/config/www/chestnut/lib/heat.js` | `heatColor(f)`, `HeatField` (grid, step, draw-to-ImageData, mean pinning) |
| `home-assistant/config/www/chestnut/lib/rules.js` | status/label rules, hold kind, level-send rule, countdowns, schedule day bars, debounce, unit conversion |
| `home-assistant/config/www/chestnut/lib/adapter.js` | entity resolution, reads with unit and availability, service calls, history and logbook fetch |
| `home-assistant/config/www/chestnut/chestnut-dashboard.js` | the `<chestnut-dashboard>` element: frame, tabs, Home/Schedule/Simulation/System |
| `home-assistant/config/www/chestnut/room-view.js` | `<chestnut-room-view>`: canvas, equipment columns, readouts |
| `home-assistant/config/www/chestnut/style.js` | shared CSS (tokens, `@font-face`) as a constructable stylesheet |
| `home-assistant/config/www/chestnut/fonts/JetBrainsMono-{Regular,Bold}.woff2`, `OFL.txt` | font |
| `home-assistant/config/dashboards/chestnut.yaml` | the panel view with `custom:chestnut-dashboard` |
| `home-assistant/config/themes/axiom.yaml` | HA theme |
| `home-assistant/config/configuration.yaml` | frontend themes, lovelace, input_booleans, automations include |
| `home-assistant/config/automations.yaml` | the fault alerts |
| `home-assistant/tests/unit/*.test.mjs` | node:test unit tests |
| `home-assistant/tests/run.sh`, `tests/ha-test/` (config overlay), `tests/e2e/test_*.py`, `tests/Dockerfile` | integration harness |
| `tab5-thermostat/hardware/tab5-base.yaml` | + uptime, Wi-Fi signal, Clock Valid |

---

### Task 1: Heat colour and heat field

**Files:**
- Create: `home-assistant/config/www/chestnut/lib/heat.js`
- Test: `home-assistant/tests/unit/heat.test.mjs`

**Interfaces:**
- Produces:
  - `heatColor(tempF: number) → [r, g, b, a]`, with `a = 0.9`.
  - `class HeatField(w = 64, h = 40)`, with:
    - `.step(dt: number, inputs: {roomF, outdoorF, heat: bool, cool: bool, fanOn: bool, frozen: bool})`;
    - `.mean(): number`;
    - `.toImageData(data: Uint8ClampedArray)`.
- Values (from the spec): supply air 108°F (heat) / 55°F (cool); vents at grid (14,1)↓, (42,1)↓ and (62,28)←; return at (5,38); window rows 9–15 and 24–30 on the left wall. The mockup's `initField`/`stepField` is the reference algorithm.

- [ ] **Step 1: Write the failing tests**

```js
test('heat_scale_ends', () => { deepClose(heatColor(60).slice(0,3), [42,127,255], 1); deepClose(heatColor(80).slice(0,3), [218,92,44], 1); });
test('heat_scale_clamps', () => { deepClose(heatColor(40), heatColor(60), 0); deepClose(heatColor(108), heatColor(80), 0); });
test('heat_scale_monotonic_red', () => { for (let t=60;t<80;t++) assert(heatColor(t+1)[0] >= heatColor(t)[0]); });
test('field_mean_pinned', () => { const f=new HeatField(); for (let i=0;i<200;i++) f.step(1/30,{roomF:71.3,outdoorF:30,heat:true,cool:false,fanOn:false,frozen:false}); assert(Math.abs(f.mean()-71.3) < 1e-3); });
test('field_heat_warmer_at_vent', () => { /* after 120 steps heating, cell (14,3) > mean, and mean pinned */ });
test('field_frozen_holds', () => { /* frozen:true → field unchanged between steps */ });
```

- [ ] **Step 2:** Run `node --test home-assistant/tests/unit/` → FAIL (module not found).
- [ ] **Step 3:** Implement `heat.js` (OKLab blend as in the mockup's `heatColor`, endpoints as in Global Constraints; the field ported from the mockup's `initField`/`stepField`/`drawField` data part).
- [ ] **Step 4:** Run `node --test home-assistant/tests/unit/` → PASS.
- [ ] **Step 5:** Commit `"dashboard: heat colour scale and heat field"`.

### Task 2: Display rules

**Files:**
- Create: `home-assistant/config/www/chestnut/lib/rules.js`
- Test: `home-assistant/tests/unit/rules.test.mjs`

**Interfaces:**
- Produces:
  - `statusFor(s) → {word, mark, color, sub}`. Here `s = {mode, action, sensorFault, interlockFault, callHeat, callCool, callFan, fanMode, waitReason, targetText, minutesSoFar}`. Words: `HEATING ▲ #da5c2c`, `COOLING ▼ #2a7fff`, `PAUSED ⊘`, `FAN`, `OFF`, `IDLE ·`.
  - `targetLabel({mode, level, hold, holdKind, manual}) → 'TARGET'|'COMFORT TARGET'|'ECO TARGET'|'HOLD'`.
  - `holdKind(scheduleStatus: string) → 'temperature'|'level'|null`.
  - `levelShouldSend({picked, current, manual}) → bool`.
  - `countdown({running, actionElapsedS, publishedAtMs, nowMs, minS}) → {leftS|null, frac}`.
  - `dayBar(periods: [{name, time:'HH:MM', level}]) → [{flex, level, label}]`.
  - `toF(value, unit)`, `fromF(f, unit)`.
  - `class Debouncer(ms, onFire)` with `.tap(value, base)`, firing once with the final value, or not at all if it equals `base`.

- [ ] **Step 1: Write the failing tests** (the console's rules, as values):

```js
test('paused_wins_over_heating', () => eq(statusFor({...base, action:'heating', interlockFault:true, callHeat:false}).word, 'PAUSED'));
test('paused_finishing_while_call_on', () => eq(statusFor({...base, sensorFault:true, callHeat:true}).sub, 'Finishing up · stops soon'));
test('mode_switch_mid_heat_finishing', () => eq(statusFor({...base, mode:'cool', action:'heating', callHeat:true}).sub, 'Finishing up · stops soon'));
test('idle_waiting_reason', () => eq(statusFor({...base, action:'idle', waitReason:'Short-cycle protection'}).sub, 'Waiting · short-cycle protection'));
test('hold_kind', () => { eq(holdKind('Holding 69° until 10:30 pm'),'temperature'); eq(holdKind('Holding Eco until 10:30 pm'),'level'); eq(holdKind('Comfort until 5:30 pm'),null); });
test('level_send', () => { eq(levelShouldSend({picked:'Comfort',current:'Comfort',manual:false}), false); eq(levelShouldSend({picked:'Comfort',current:'Comfort',manual:true}), true); });
test('units_metric_roundtrip', () => { closeTo(toF(22.2222,'°C'),72,1e-3); closeTo(fromF(72,'°C'),22.2222,1e-3); eq(toF(72,'°F'),72); });
test('debounce_nets_zero', async () => { /* taps 73,72 with base 72 → onFire never called after 1.5 s */ });
test('debounce_one_write', async () => { /* 5 taps → onFire called once with 77 */ });
test('day_bar_wraps_midnight', () => { /* first segment carries the last period's level */ });
test('countdown_from_action_elapsed', () => { /* running, elapsed 60 s published 10 s ago, min 180 → leftS 110 */ });
```

- [ ] **Step 2:** `node --test home-assistant/tests/unit/` → FAIL.
- [ ] **Step 3:** Implement `rules.js`, matching `tab5-thermostat/ui/console-logic.yaml` `ui_refresh`'s status block.
- [ ] **Step 4:** `node --test home-assistant/tests/unit/` → PASS.
- [ ] **Step 5:** Commit `"dashboard: display rules shared with the wall console"`.

### Task 3: HA adapter

**Files:**
- Create: `home-assistant/config/www/chestnut/lib/adapter.js`
- Test: `home-assistant/tests/unit/adapter.test.mjs` (with a fake `hass`: `{states, entities, devices, callService, callWS, connection}`)

**Interfaces:**
- Consumes: `toF`/`fromF` (Task 2).
- Produces: `class Adapter(hass, {deviceName})`, with:
  - `.resolve()` → a map `objectId → entity_id`, found by device name (exact match), then the registry entry's `unique_id` ending `-<domain>-<object_id>` or its `original_name`;
  - `.num(objId) → number|null`, in °F where it's a temperature, `null` if `unavailable`/`unknown`;
  - `.str(objId)`, `.on(objId) → bool|null`, `.online() → bool`;
  - `.simPresent() → bool` (registry entries for `sim_*` exist and aren't orphaned);
  - `.call(domain, service, objId, data)`;
  - `.history(objIds, hours) → Promise<{[objId]: [{t, v}]}>` (websocket `history/history_during_period`);
  - `.logbook(objIds, hours) → Promise<[{t, msg}]>`.

- [ ] **Step 1: Failing tests:**
  - `resolves_by_device`: picks the Tab5 device's entities, ignores a stale M3-stub entity with the same object id on another device;
  - `unavailable_is_dash`;
  - `units_metric_read` (a °C sensor reads as °F);
  - `sim_absent_after_m4` (no `sim_*` → false);
  - `sim_unavailable_still_present` (unavailable → true);
  - `set_target_writes_entity_unit` (°C entity → `number.set_value` with °C).
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS.
- [ ] **Step 5:** Commit `"dashboard: HA adapter (registry lookup, units, availability)"`.

### Task 4: HA wiring, theme, font, integration harness

**Files:**
- Modify: `home-assistant/config/configuration.yaml`, `.gitignore`
- Create:
  - `home-assistant/config/dashboards/chestnut.yaml`, `themes/axiom.yaml`, `www/chestnut/style.js`, `www/chestnut/fonts/*`;
  - `www/chestnut/chestnut-dashboard.js` (a stub that renders the frame and title only);
  - `home-assistant/tests/{run.sh, Dockerfile, ha-test/, e2e/conftest.py, e2e/test_frame.py}`.

**Interfaces:**
- Produces:
  - `run.sh unit|e2e|all`. `e2e`:
    - copies `home-assistant/config` into a temp dir with the `ha-test/` overlay (`http: server_port: 8124`, and the dashboard `device_name: "Main Thermostat (Sim)"`);
    - starts HA 2026.10.4 with host networking;
    - onboards via `/api/onboarding/users` (user `test`/`test-pass-123`);
    - starts `main-thermostat-sim.yaml` through `docker compose --profile dev run esphome-host run` with a test key;
    - adds the ESPHome integration through the config-flow REST API (`127.0.0.1:6053` + key);
    - runs pytest + Playwright (`mcr.microsoft.com/playwright/python`, pinned) against `http://localhost:8124`;
    - tears everything down.
  - The `conftest.py` fixtures: `page` (logged in and on `/lovelace/0`), `ha` (REST helper: `get_state(entity_id)`, `call(domain, service, data)`), `sim` (`stop()`, `start()`).
- Theme `axiom`: HA theme variables set from the Global Constraints colours. Set as the default theme (`frontend: themes: !include_dir_merge_named themes` + an automation `frontend.set_theme name: axiom` at startup).

- [ ] **Step 1: Failing e2e test `test_frame.py`:**
  - `test_overview_is_chestnut`: GET `/lovelace/0` shows `chestnut-dashboard` with the text "Main Thermostat";
  - `test_theme_is_axiom`: the computed `--primary-background-color` is `rgb(0, 0, 0)`;
  - `test_font_self_hosted`: `/local/chestnut/fonts/JetBrainsMono-Regular.woff2` returns 200, and no request goes to fonts.googleapis.com.
- [ ] **Step 2:** `home-assistant/tests/run.sh e2e` → FAIL.
- [ ] **Step 3:** Implement the config, theme, font, stub and harness.
- [ ] **Step 4:** `run.sh all` → PASS.
- [ ] **Step 5:** Commit `"dashboard: HA wiring, Axiom theme, font, e2e harness"`.

### Task 5: Dashboard frame and Home tab

**Files:**
- Modify: `www/chestnut/chestnut-dashboard.js`
- Test: `tests/e2e/test_home.py`

**Interfaces:**
- Consumes: Adapter (Task 3), rules (Task 2).
- Produces:
  - `<chestnut-dashboard>` with `setConfig({device_name})` and `set hass(h)`;
  - the tabs `HOME`, `SCHEDULE`, `SIMULATION`, `SYSTEM` (`data-tab` attributes for tests);
  - `data-testid` hooks: `target`, `status-word`, `status-sub`, `mode-<off|heat|cool|auto>`, `fan-<auto|on>`, `level-<comfort|eco>`, `resume`, `runtime`, `today`, `status-card`.
- Layout and copy: follow `Main.dc.html`'s Home tab, minus the supply-air readout. Subscriptions are re-bound on every `hass` set without duplicating timers. The room view is a placeholder until Task 6.

- [ ] **Step 1: Failing tests:**
  - `five_taps_one_write`: five taps on +, then `set_target` = start+5 after 2 s, with exactly one state change;
  - `mode_heat_sets_climate`;
  - `resume_only_when_hold`;
  - `phone_hides_sim_tab_and_room` (viewport 390×844: no SIMULATION tab, no room element);
  - `empty_history_renders` (a fresh HA: the runtime card says "no data yet");
  - `reconnect_rebinds_once` (reload the hass connection: one animation loop, one set of intervals);
  - `status_paused_on_sensor_fault` (set `select.sim_fault` to Unplugged, then the status word reads PAUSED within 10 s).
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** `run.sh all` → PASS.
- [ ] **Step 5:** Commit `"dashboard: frame, tabs and Home"`.

### Task 6: Room view

**Files:**
- Create: `www/chestnut/room-view.js`
- Modify: `chestnut-dashboard.js` (mount it on Home and Simulation)
- Test: `tests/e2e/test_room.py`

**Interfaces:**
- Consumes: `HeatField`/`heatColor` (Task 1), Adapter.
- Produces: `<chestnut-room-view>` with properties `adapter` and `active: bool`. `active` pauses the animation loop when the tab is hidden or the page is backgrounded (`visibilitychange`).
- Data:
  - the room readout is `checked_temperature`;
  - equipment comes from `call_heat`/`call_cool`/`call_fan` and the fan mode;
  - outdoor is the sim's current outdoor sensor if present, else `sim_outdoor_f` + "fixed", else the HA weather entity, else "—";
  - "SIM" tag while `simPresent()`;
  - the field is frozen while `sensor_fault` is on.
- AC and blower fans spin about their centre (`transform-box: view-box`; origin 32,32 and 12,12).

- [ ] **Step 1: Failing tests:**
  - `room_mean_matches_sensor`: read the room element's `data-mean` and compare with `checked_temperature`, within 0.05;
  - `furnace_lit_when_call_heat`: force heat (Heat mode with the sim outdoor at 20, wait for `call_heat`), then the furnace box has `data-on="1"` and the readouts have no "supply" text;
  - `sim_tag_present`;
  - `offline_shows_dashes`: `sim.stop()`, then within 70 s the room shows "—" and the SIMULATION tab still exists;
  - `paused_when_tab_hidden`: switch to SCHEDULE, then the requestAnimationFrame callback count stops increasing.
- [ ] **Steps 2–5:** run → FAIL, implement, run → PASS, commit `"dashboard: room view"`.

### Task 7: Schedule and Simulation tabs

**Files:**
- Modify: `chestnut-dashboard.js`
- Test: `tests/e2e/test_schedule_sim.py`

**Interfaces:**
- Consumes: Adapter, `dayBar`, `levelShouldSend`.
- Behaviour: follow the mockup's Schedule and Simulation tabs, with no Holds card. The SIMULATION tab and the BENCH controls render only while `adapter.simPresent()` (gone or orphaned → hidden; unavailable → still shown; the logic is unit-tested in Task 3). Writes go through `time.set_value`, `select.select_option`, `switch.toggle` and `number.set_value`.

- [ ] **Step 1: Failing tests:**
  - `edit_weekday_leave_time`: set the weekday leave time to 09:15 → `time.…sched_weekday_leave_time` = 09:15:00;
  - `level_select_sched`;
  - `week_bar_updates`;
  - `schedule_off_dims_rows`;
  - `comfort_stepper_writes`;
  - `sim_outdoor_slider_writes`;
  - `sim_fault_select_writes`;
  - `lit_level_sends_when_manual`: schedule off, − once (`manual_target` on), tap the lit level, then `manual_target` goes off;
  - `lit_level_noop_otherwise`.
- [ ] **Steps 2–5:** FAIL → implement → PASS → commit `"dashboard: Schedule and Simulation tabs"`.

### Task 8: System tab and Tab5 device sensors

**Files:**
- Modify: `chestnut-dashboard.js`, `tab5-thermostat/hardware/tab5-base.yaml`
- Test: `tests/e2e/test_system.py`

**Interfaces:**
- Safety bars come from `countdown` (Task 2) with `action_elapsed`. Startup and lockout show as `call_wait_reason` text.
- Timers write their `number` entities, clamped to each entity's min/max.
- Clear interlock is enabled only while `interlock_fault` is on.
- Alerts toggles: `input_boolean.chestnut_alert_sensor_fault`, `…_interlock_fault`, `…_offline` (created in Task 9; the System tab reads and toggles them).
- Wall screen: `screen_brightness`, `dim_brightness`, `dark_theme`.
- Device: IP, firmware (device registry `sw_version`), uptime, Wi-Fi signal, Clock Valid. On the host sim these show "—".
- Event log: `adapter.logbook` for the call sensors, the faults, `schedule_hold` and `schedule_period`, newest first, at most 40.
- `tab5-base.yaml` additions:
  - `sensor: - platform: uptime, name: "Uptime"`;
  - `- platform: wifi_signal, name: "Wi-Fi Signal", update_interval: 60s`;
  - `binary_sensor: - platform: template, id: clock_valid, name: "Clock Valid", lambda: return id(sntp_time).now().is_valid();`.

- [ ] **Step 1: Failing tests:**
  - `timer_edit_writes_and_clamps`;
  - `clear_interlock_disabled_normally`;
  - `alert_toggle_flips_boolean`;
  - `event_log_shows_heat_on`;
  - `device_dash_on_sim`.

  Also the Tab5 config: `docker compose run --rm --no-deps esphome config tab5-thermostat.yaml` → "Configuration is valid!".
- [ ] **Steps 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Flash the Tab5 (`tools/preview/test_device.sh` → PASS), then commit `"dashboard: System tab; Tab5 uptime, Wi-Fi signal, Clock Valid"`.

### Task 9: Fault alerts

**Files:**
- Modify: `home-assistant/config/configuration.yaml` (the `input_boolean` helpers, default on), `automations.yaml`
- Test: `tests/e2e/test_alerts.py`

**Interfaces:**
- Automations, gated by their `input_boolean`. Each sends `persistent_notification.create`, plus `notify.notify` if that service exists (never a hard-coded phone service), and a recovery notice on clear:
  - `chestnut_sensor_fault` on `binary_sensor.<resolved>.sensor_fault` → on;
  - `chestnut_interlock_fault`;
  - `chestnut_offline`: the climate `unavailable` for 10 min.
- Entity ids in the automations: the test overlay templates them for the sim device. On the real install, the README documents checking them once. **PC call:** automations can't do registry lookup by object id, so they use the real install's entity ids, and the e2e overlay rewrites them.
- Exact copy:
  - sensor fault: "Main Thermostat: temperature sensor problem. Heating and cooling paused.";
  - interlock fault: "Main Thermostat: heat and cool were both requested, so the system stopped. Clear it once it's checked.";
  - offline: "Main Thermostat is offline (no contact for 10 minutes). It keeps running on its own.";
  - recovery: "Main Thermostat: <thing> cleared."

- [ ] **Step 1: Failing tests:**
  - `sensor_fault_notifies`: set `sim_fault` to Unplugged → a persistent notification with the exact text within 15 s;
  - `alert_off_silences`;
  - `recovery_notifies`.
- [ ] **Steps 2–5:** FAIL → implement → PASS → commit `"dashboard: fault alerts"`.

### Task 10: Docs and the real install

**Files:**
- Modify: `AGENTS.md` (repo layout; how to run the HA tests), `home-assistant/README.md` (create if missing: setting the dashboard and theme on the house VM, the Companion app's `notify`, checking the automation entity ids)

- [ ] **Step 1:** Run `home-assistant/tests/run.sh all` → all PASS.
- [ ] **Step 2:** Apply to the dev HA on `localhost:8123`: `docker compose restart homeassistant`, then open `/lovelace/0` and check it renders against the real Tab5. This is a manual look, reported to Dang with a screenshot from the e2e run.
- [ ] **Step 3:** Commit `"dashboard: docs"`, push, and post the review request on beacon to `@mac-chestnut-console`.
