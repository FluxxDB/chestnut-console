# Main Thermostat Console UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the milestone 1 hello screen with the functional Main Thermostat console from the UI spec, running on the Tab5 and in a desktop preview, bound to the milestone 2 contract ids through a dev stand-in package.

**Architecture:**
- The console is a set of ESPHome packages under `tab5-thermostat/ui/`:
  - fonts
  - theme (LVGL `style_definitions`, re-coloured at runtime with `lvgl.style.update`)
  - layout (one LVGL page)
  - logic (bindings, scripts, timers)
- A dev-only `ui/dev/contract-stub.yaml` provides every milestone 2 id, with a `Scenario` select that drives all of them.
- A host + SDL entry point (`tab5-thermostat/preview/console-preview.yaml`) runs the same packages on Linux under Xvfb. A script drives the scenarios through the native API and saves screenshots.

**Tech Stack:** ESPHome 2026.10.1, LVGL 9.5, ESP-IDF on the ESP32-P4, the ESPHome `host` platform + `sdl` display, Docker, Xvfb, ImageMagick, xdotool, aioesphomeapi.

**Spec:** `docs/superpowers/specs/2026-10-28-main-thermostat-console-ui-design.md` (@ 855f779). Contract ids: `mac/thermostat-logic` @ cbeebb8, `docs/superpowers/specs/2026-10-28-thermostat-logic-design.md`.

## Global Constraints

- Screen 1280×720 landscape. LVGL `rotation: ${display_rotation}`: 270° on the Tab5, 0° in the preview.
- Fonts: Inter 400/500 for everything; Space Grotesk 500 only for the "Main Thermostat" title. Both from `gfonts://`, with glyph subsets for sizes ≥ 100 px.
- Colors: exactly the spec's token table, light and dark. Status colors: heating `#ff7b1b`, cooling `#4098ff`, fan `#00b595`, off/idle `#8b8d90`. Fault banner `#f8e645` with ink text.
- The screen writes only `set_target`, `comfort_level`, `main_thermostat` mode and fan mode, and `resume_schedule`. Never `relay_*`, the climate setpoints, or `clear_interlock_fault`.
- `set_target` writes are debounced 1.5 s and clamped to 50–90.
- Dim to 10% after 30 s idle. The first tap on a dimmed screen only wakes it.
- Theme: a top-bar toggle, plus auto dark at sunset and light at sunrise via `sun:`. Latitude/longitude come from `!secret`, never committed. The theme is restored after a reboot.
- Missing data shows "—", never "nan".
- No location or credentials in git. No AI co-author trailers.

## Review Focus

1. **A burst of − / + taps** must produce exactly one `set_target` write, with the value clamped to 50–90. Pinned in Task 4.
2. **Unknown values** (sensor `NaN`, entities not yet received, HA weather missing) must show "—", not "nan°" or "0°". Pinned in Task 4 (scenario `Unknowns`).
3. **The dark theme** must recolor every element, with no light-theme leftovers, in every scenario. Pinned in Task 5 (a full dark screenshot set).
4. **A tap on a dimmed screen** must not press the button under the finger. Pinned in Task 6 (an xdotool click test).
5. **Long `schedule_status` text** ("Schedule paused: clock not set", "Holding 69° until 10:30 pm" plus the pill) must not overlap the title or the clock. Pinned in Task 4 (scenarios `Clock not set` and `Hold`).

---

### Task 1: Desktop preview rig

**Files:**
- Create: `tools/preview/Dockerfile`, `tools/preview/shoot.sh`, `tools/preview/drive.py`
- Create: `tab5-thermostat/preview/console-preview.yaml`, `tab5-thermostat/preview/secrets.yaml` (committed, preview-only dummy values)
- Modify: `docker-compose.yml` (add a `preview` service under a `dev` profile), `.gitignore` (`tab5-thermostat/preview/shots/`)

**Interfaces:**
- Produces:
  - Image `chestnut-preview` (FROM `esphome/esphome:2026.10.1`, plus `libsdl2-dev xvfb imagemagick xdotool`).
  - `tools/preview/shoot.sh <yaml> <outdir> [scenario...]`: compiles, starts the binary under `Xvfb :99 -screen 0 1280x720x24`, waits for API port 6053, runs `drive.py` per scenario and theme, and writes `<outdir>/<scenario>-<light|dark>.png`.
  - `drive.py --scenario NAME --theme light|dark --shot PATH`: aioesphomeapi; selects `Scenario`, sets switch `ui_dark_theme`, waits 1.5 s, then runs `import -window root PATH`.
  - The preview defines ids `tab5_display` (sdl, 1280×720), `touch` (sdl), `sntp_time` (`platform: host`) and `backlight` (a template monochromatic light on a template output), so the ui packages compile unchanged.

- [ ] **Step 1:** Write `console-preview.yaml` with `host:`, `api:` (no encryption), `logger:`, the ids above, and a minimal LVGL label "preview ok".
- [ ] **Step 2:** Run `tools/preview/shoot.sh tab5-thermostat/preview/console-preview.yaml /tmp/shots`. Expected: `/tmp/shots/default-light.png` exists, is 1280×720, and `identify -format %k` reports more than 1 unique color.
- [ ] **Step 3:** Commit: `Add host+SDL desktop preview rig for the console`.

### Task 2: Contract stand-in with scenarios

**Files:**
- Create: `tab5-thermostat/ui/dev/contract-stub.yaml`
- Modify: `tab5-thermostat/preview/console-preview.yaml` (include the stub)

**Interfaces:**
- Produces every id from the spec's binding table, with milestone 2's types:
  - `checked_temperature`, `effective_target`, `effective_low`, `effective_high`: template sensors, °F
  - `room_humidity`: template sensor, %
  - `set_target`, `comfort_target`: template numbers, 50–90 step 1, optimistic. A write to `set_target` sets `schedule_hold` on.
  - `eco_offset`: template number
  - `comfort_level`: template select, Comfort / Eco
  - `schedule_enabled`: template switch
  - `schedule_hold`, `sensor_fault`, `interlock_fault`, `call_heat`, `call_cool`, `call_fan`: template binary sensors
  - `schedule_period`, `schedule_next_change`, `schedule_status`, `call_wait_reason`: template text sensors
  - `action_since`: template sensor, epoch seconds
  - `resume_schedule`, `clear_interlock_fault`: template buttons
  - `main_thermostat`: a `thermostat` climate on template switches, with modes OFF/HEAT/COOL/HEAT_COOL and fan AUTO/ON
- Also produces select `Scenario`. Its options and the values each one sets are fixed below. Every scenario also sets the climate mode.

| Scenario | Values |
|---|---|
| Heating | heat, 71° room, target 72, `call_heat`, schedule "Comfort until 10:30 pm" |
| Cooling | cool, 76° room, target 74, `call_cool` |
| Eco auto band | heat_cool, Eco, low 68, high 76, idle, "Eco until 5:30 pm" |
| Hold | heat, target 69, `schedule_hold`, "Holding 69° until 10:30 pm" |
| Schedule off | `schedule_enabled` off, `schedule_period` "" |
| Clock not set | status "Schedule paused: clock not set" |
| Waiting | idle, 69° room, target 72, `call_wait_reason` "Short-cycle protection" |
| Off fan on | off, `call_fan` |
| Sensor fault | `sensor_fault`, `checked_temperature` NaN |
| Interlock fault | `interlock_fault` |
| Unknowns | all sensors NaN, texts empty |

- [ ] **Step 1:** Write the stub. Include it in the preview.
- [ ] **Step 2:** `shoot.sh ... Heating Sensor\ fault`. Expected: the log shows `Scenario` changes and the sensor publishes for each one.
- [ ] **Step 3:** Commit: `Add dev contract stand-in with UI scenarios`.

### Task 3: Fonts, theme styles and static layout

**Files:**
- Create: `tab5-thermostat/ui/fonts.yaml`, `tab5-thermostat/ui/theme.yaml`, `tab5-thermostat/ui/console.yaml`
- Modify: `tab5-thermostat/preview/console-preview.yaml` (include them)

**Interfaces:**
- Produces:
  - Font ids: `f_title` (Space Grotesk 500, 39), `f_label` (Inter 400, 22), `f_small` (Inter 400, 20), `f_pill` (Inter 400, 23), `f_mid` (Inter 400, 50), `f_target` (Inter 400, 105), `f_room` (Inter 400, 164, glyphs `0123456789°—-`), `f_deg` (Inter 400, 100, glyphs `°`).
  - Style ids (in `style_definitions`): `st_page`, `st_card`, `st_emph`, `st_ebtn`, `st_pill`, `st_pill_sel`, `st_hum`, `st_ink`, `st_sub`, `st_on_emph`, `st_on_emph_sub`, `st_rule`, `st_banner`.
  - Widget ids used by Task 4: `lbl_date`, `lbl_clock`, `lbl_sched`, `btn_resume`, `btn_theme`, `lbl_theme_icon`, `lbl_room`, `obj_marker`, `lbl_status`, `lbl_sub`, `line_hist`, `line_target`, `lbl_hist_start`, `obj_banner`, `lbl_banner`, `lbl_tgt_label`, `lbl_tgt_comfort`, `lbl_target`, `btn_minus`, `btn_plus`, `lbl_out_temp`, `lbl_out_cond`, `lbl_hum`, `lbl_hum_cap`, `btn_mode_off|heat|cool|auto`, `btn_fan_auto|on`, `btn_lvl_comfort|eco`.
- The layout follows the spec's sizes: padding 26, gaps 18, card radius 24, top bar 50, strip 90, a 1.32 : 1 column split, and the target card at ~57% of the right column.

- [ ] **Step 1:** Write the three packages with light colors and placeholder text matching mockup v7.
- [ ] **Step 2:** `shoot.sh ... Heating`, then compare `Heating-light.png` against mockup v7. Expected: every card, label and pill is present and readable, with no overlap or clipping.
- [ ] **Step 3:** Device check: `docker compose run --rm --no-deps esphome compile tab5-thermostat.yaml`, with `ui:` switched to the new packages + stub. Expected: success, flash < 80%.
- [ ] **Step 4:** Commit: `Console layout, fonts and light theme styles`.

### Task 4: Bindings and behavior

**Files:**
- Create: `tab5-thermostat/ui/console-logic.yaml`

**Interfaces:**
- Consumes: the Task 2 ids and the Task 3 widget ids.
- Produces: globals `ui_pending_target` (int, -1 = none), `ui_hist[72]` (float ring buffer) and `ui_hist_n`. Script `push_target` (`mode: restart`, `delay: 1.5s`, then `number.set set_target`).
- Behaviour, exactly as in the spec's binding table:
  - formatting helpers return "—" for NaN;
  - the status word and subline follow the table's rules;
  - the big target is `effective_target`, or "low–high" in Auto + Eco + no hold;
  - pills reflect their entities and write them;
  - the top bar shows `schedule_status`, Resume is visible iff `schedule_hold`, and "Schedule off" shows when `schedule_enabled` is off;
  - the banner shows on `sensor_fault` (with sensor text) or `interlock_fault` (with interlock text) and replaces the history lines;
  - the history samples `checked_temperature` every 10 min into a 72-point ring, redraws `line_hist`, and draws `line_target` at `effective_target`;
  - the clock updates each minute;
  - the outside card imports HA's `weather.forecast_home` (it exists, from the met.no integration, with HA in US units): its `temperature` attribute via a `homeassistant` sensor `out_temp`, and its state via a `homeassistant` text sensor `out_cond`, shown capitalized ("partlycloudy" → "Partly cloudy"). Both show "—" while HA is unreachable, and in the preview.

- [ ] **Step 1:** Write the logic.
- [ ] **Step 2:** `shoot.sh` across all 11 scenarios (light). Expected:
  - each PNG shows the scenario's values exactly as listed in Task 2's table;
  - `Unknowns` shows "—" in the room temperature, humidity, outside and target, with no "nan";
  - `Clock not set` and `Hold` keep the top-bar text clear of the title and the clock.
- [ ] **Step 3:** Debounce test: `drive.py` presses `btn_plus` 5 times in 1 s via xdotool on the Heating scenario. Expected: exactly one `set_target` state change to 77 in the log (72 + 5), and the label shows 77 immediately. At target 90, a further press leaves it at 90.
- [ ] **Step 4:** Commit: `Console bindings: status, target with debounced writes, pills, schedule line, faults, history`.

### Task 5: Light/dark themes

**Files:**
- Modify: `tab5-thermostat/ui/theme.yaml` (dark palette, the `apply_theme` script, switch `ui_dark_theme` with `restore_mode: RESTORE_DEFAULT_OFF`, and `sun:` with `on_sunset` / `on_sunrise`)
- Modify: `tab5-thermostat/secrets.yaml.example` (`house_latitude`, `house_longitude`). Local `secrets.yaml` gets city-level values. The preview secrets get 0/0.

**Interfaces:**
- Produces:
  - switch `ui_dark_theme` (also exposed to HA)
  - script `apply_theme`, which runs `lvgl.style.update` on every `st_*` style with the active palette and swaps the theme icon text between moon and sun
- `btn_theme` toggles the switch.

- [ ] **Step 1:** Implement.
- [ ] **Step 2:** `shoot.sh` across all scenarios in dark. Expected: no light-palette color anywhere (spot-check with `convert x.png -format %c histogram:info:` for `#ffffff` card fills: none outside text), the selected pill is `#1e3b33`, and all text is readable.
- [ ] **Step 3:** Commit: `Console light/dark themes with sunset/sunrise switching`.

### Task 6: Idle dim and wake-only first tap

**Files:**
- Modify: `tab5-thermostat/ui/console-logic.yaml`

**Interfaces:**
- Produces:
  - global `ui_dimmed` (bool)
  - a full-screen transparent `obj_wake` on the LVGL top layer, hidden by default
- `lvgl.on_idle` (30 s) dims the backlight to 10%, sets `ui_dimmed` and shows `obj_wake`. A press on `obj_wake` restores 100%, hides it and clears `ui_dimmed`.

- [ ] **Step 1:** Implement. The preview's on_idle timeout comes from a substitution (`idle_timeout`, 30 s on the device, 3 s in the preview).
- [ ] **Step 2:** Test: Heating scenario, wait 4 s, click `btn_plus` once with xdotool. Expected: the target stays 72 and the backlight goes to 100% (from the log). A second click makes it 73.
- [ ] **Step 3:** Commit: `Idle dimming with a wake-only first tap`.

### Task 7: Tab5 integration

**Files:**
- Modify: `tab5-thermostat/tab5-thermostat.yaml` (`ui:` packages = fonts, theme, console, console-logic, dev/contract-stub)
- Delete: `tab5-thermostat/ui/hello.yaml`
- Modify: `tab5-thermostat/README.md` (preview usage), `AGENTS.md` (repo layout)

- [ ] **Step 1:** Compile for the device. Expected: success.
- [ ] **Step 2:** OTA to `10.0.0.193`, then read logs for 60 s. Expected: no errors, LVGL started, the stub publishes, and free PSRAM is reported.
- [ ] **Step 3:** Commit, push `pc/m3-console-ui`, and post a review request on beacon with the screenshot set attached.
