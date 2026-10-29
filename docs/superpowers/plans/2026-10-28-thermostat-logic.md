# Milestone 2: Thermostat Logic and Virtual House Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Main Thermostat's on-device logic (climate `main_thermostat` with Comfort/Eco, holds, an on-device weekly schedule and all the safety rules) plus a virtual-house simulation. It runs on ESPHome's `host` platform with automated scenario tests, and the same packages run on the Tab5.

**Architecture:**
- **Pure C++, unit-tested with g++:** the decision logic that's easy to get subtly wrong lives in header-only C++: setpoint derivation, the schedule lookup, sensor sanity and the house physics.
- **Thin YAML glue:** `thermostat/logic.yaml` wires the headers to ESPHome's stock `thermostat` climate and the contract ids. `sim/virtual-house.yaml` provides the contract's sensor and relay ids from the physics model.
- **Scenario tests:** Python tests drive a host build of a test entry point over the native API. That build has short timers, sped-up physics and test-only hooks.

**Tech Stack:** ESPHome 2026.10.1 (`esphome/esphome:2026.10.1` image: g++ 14.2, aioesphomeapi 46.12), ESPHome `thermostat`, `template`, `datetime`, `interval`, `api` actions; C++17; pytest + pytest-asyncio; Docker.

**Spec:** `docs/superpowers/specs/2026-10-28-thermostat-logic-design.md` (approved by Dang, `mac/thermostat-logic`). Executors read the spec and this plan together.

## Global Constraints

- ESPHome 2026.10.1, pinned. Everything builds and runs in that image (Docker on the Mac and on the PC). Nothing gets installed on the host machines.
- Climate values are °C inside ESPHome. Everything the user sees or sets is °F, in whole degrees, 50–90°F. Conversion: `c = (f − 32) × 5/9`.
- Every `esphome: on_boot:` is a list item (`- priority: X`), never a mapping (package-merge rule).
- `relay_heat` / `relay_cool` / `relay_fan` / `relay_ob`: `restore_mode: ALWAYS_OFF`, `internal: true`. Only `thermostat/logic.yaml` turns them on. `relay_ob` is never turned on.
- Test-only hooks exist only in `tests/main-thermostat-test.yaml`, never in `thermostat/` or `sim/`.
- Contract ids are exactly the spec's "Entities the screen and HA can use" table. The PC's screen and stub use them; don't rename them.
- No `web_server` in any host entry (not supported on `host`). The host sim has `api: reboot_timeout: 0s`.
- Public repo: no secrets, addresses or Wi-Fi details. New secret: `sim_api_encryption_key`. No AI co-author or "Generated with" lines in commits.
- Branch `mac/thermostat-logic`. Files we own: `tab5-thermostat/thermostat/`, `tab5-thermostat/sim/`, `tab5-thermostat/tests/`, `tab5-thermostat/main-thermostat-sim.yaml`. `tab5-thermostat.yaml` changes go to the PC for review.

## Review Focus

1. **A setpoint change from HA's card** (temperature in Heat, low/high in Auto) must become a hold at the matching °F through `set_target`. It must not end up as raw climate setpoints that the next derivation overwrites. Pinned in Task 9 (`test_ha_setpoint_write_becomes_hold`).
2. **A Sleep period that crosses midnight** must stay the same period, and a hold started at 23:00 must still be on at 02:00, until Wake. Pinned in Task 2 (`schedule_midnight_carryover`) and Task 10 (`test_hold_survives_midnight`).
3. **Schedule times entered out of order** (e.g. Leave set before Wake) must not crash or skip periods. The periods are evaluated in time order. Pinned in Task 2 (`schedule_out_of_order_times`).
4. **The sensor recovers in the middle of a short-cycle wait.** The AC must still wait out its minimum off before it starts again. Pinned in Task 8 (`test_recovery_respects_cool_min_off`).
5. **Re-sending an unchanged level or target** (the screen's re-tap guard can miss, and HA can send duplicates) must not start a hold. Pinned in Task 9 (`test_same_value_no_hold`).

---

## File Structure

| File | Responsibility |
|---|---|
| `tab5-thermostat/thermostat/chestnut_logic.h` | Pure C++, namespace `chestnut`. `derive_setpoints`, `schedule_at`, `format_12h`, `SanityChecker`, `f_to_c`/`c_to_f`. No ESPHome includes. |
| `tab5-thermostat/thermostat/logic.yaml` | The climate, relay actions, interlock watchdog, checked temperature, the settings and schedule entities, holds, and the status sensors. |
| `tab5-thermostat/sim/house_model.h` | Pure C++: `house_step`, `weather_outdoor_f`. |
| `tab5-thermostat/sim/virtual-house.yaml` | Contract sensors and relays from the model; the sim knobs; fault injection. |
| `tab5-thermostat/main-thermostat-sim.yaml` | Host entry for the play/HA sim (real timers, real-time physics). |
| `tab5-thermostat/tests/main-thermostat-test.yaml` | Host entry for the tests (short timers, fast physics, hooks). |
| `tab5-thermostat/tests/unit/test_logic.cpp`, `test_house.cpp`, `check.h` | Unit tests; `check.h` is a ~20-line `CHECK(expr)` / `CHECK_NEAR(a,b,eps)` runner. |
| `tab5-thermostat/tests/scenarios/conftest.py` + `test_*.py` | Scenario tests over aioesphomeapi. |
| `tab5-thermostat/tests/Dockerfile`, `tests/run.sh` | Test image (the esphome image + pytest, pytest-asyncio) and the single entry for running the tests: `run.sh unit`, `run.sh scenarios [-k expr]`, `run.sh all`. |

**Substitutions** (defaults in `logic.yaml` / `virtual-house.yaml`, overridden by entry points):

| name | prod | test | meaning |
|---|---|---|---|
| `timer_unit_s` | `60` | `1` | seconds per "minute" for every user-facing timer and sanity window |
| `heat_run_s`, `heat_off_s`, `cool_run_s`, `cool_off_s` | `180`, `180`, `300`, `300` | `3`, `3`, `5`, `5` | the thermostat's compile-time minimum timers (= the defaults × unit) |
| `min_idle_s` | `30` | `1` | thermostat `min_idle_time` |
| `clock_id` | `sntp_time` (Tab5), `host_time` (host) | `host_time` | time component the schedule reads |
| `schedule_tick` | `15s` | `24h` | how often the real clock drives the schedule |
| `sim_speed` | `1` | `600` | physics time multiplier |
| `sim_publish_interval` | `10s` | `250ms` | how often the sim publishes `room_temperature` |

---

### Task 1: Setpoint derivation and the unit-test harness

**Files:**
- Create: `tab5-thermostat/thermostat/chestnut_logic.h`, `tab5-thermostat/tests/unit/check.h`, `tab5-thermostat/tests/unit/test_logic.cpp`, `tab5-thermostat/tests/Dockerfile`, `tab5-thermostat/tests/run.sh`, `tab5-thermostat/tests/.gitignore` (`/.esphome/`, `/secrets.yaml`, `/.prefs/`)

**Interfaces:**
- Produces:
  - `enum class Mode { Off, Heat, Cool, Auto };`
  - `struct Setpoints { int effective_f; int low_f; int high_f; };`
  - `Setpoints derive_setpoints(Mode mode, int comfort_f, int eco_offset_f, bool eco, bool hold, int hold_f);`
  - `float f_to_c(float f); float c_to_f(float c);`
  - `run.sh unit` compiles `tests/unit/*.cpp` with `g++ -std=c++17 -Wall -Werror -I thermostat -I sim` inside the test image and runs each one; exit 0 means pass.

Rules (spec, "Single target, Comfort, Eco and holds"):
- `centre = hold ? hold_f : comfort_f`.
- Heat: `low = hold ? hold_f : comfort_f − (eco ? N : 0)`, `high = low + 2`, `effective = low`.
- Cool: `high = hold ? hold_f : comfort_f + (eco ? N : 0)`, `low = high − 2`, `effective = high`.
- Auto: `widen = (!hold && eco) ? N : 0`, `low = centre − 1 − widen`, `high = centre + 1 + widen`, `effective = centre`.
- Off: same as Heat (the values are unused, but stay valid for the climate).
- Inputs are clamped first: comfort and hold to 50–90, N to 2–10.

- [ ] **Step 1: Write the failing tests** in `test_logic.cpp`. Each test is a function called from `main`:

```cpp
// derive_heat_comfort / derive_heat_eco / derive_cool_eco / derive_auto / derive_auto_eco /
// derive_hold_overrides_eco_heat / derive_hold_auto_no_widen / derive_clamps
auto s = derive_setpoints(Mode::Heat, 72, 4, false, false, 0); CHECK(s.effective_f==72 && s.low_f==72 && s.high_f==74);
s = derive_setpoints(Mode::Heat, 72, 4, true,  false, 0);      CHECK(s.effective_f==68 && s.low_f==68);
s = derive_setpoints(Mode::Cool, 72, 4, true,  false, 0);      CHECK(s.effective_f==76 && s.high_f==76 && s.low_f==74);
s = derive_setpoints(Mode::Auto, 72, 4, false, false, 0);      CHECK(s.low_f==71 && s.high_f==73 && s.effective_f==72);
s = derive_setpoints(Mode::Auto, 72, 4, true,  false, 0);      CHECK(s.low_f==67 && s.high_f==77 && s.effective_f==72);
s = derive_setpoints(Mode::Heat, 72, 4, true,  true, 69);      CHECK(s.effective_f==69 && s.low_f==69);
s = derive_setpoints(Mode::Auto, 72, 4, true,  true, 69);      CHECK(s.low_f==68 && s.high_f==70 && s.effective_f==69);
s = derive_setpoints(Mode::Heat, 95, 20, false, false, 0);     CHECK(s.effective_f==90);
CHECK_NEAR(f_to_c(72), 22.2222f, 1e-3); CHECK_NEAR(c_to_f(20), 68.0f, 1e-3);
```

- [ ] **Step 2: Run the tests and watch them fail**: `tab5-thermostat/tests/run.sh unit`. Expected: a compile error, `derive_setpoints` not declared.
- [ ] **Step 3: Implement** `derive_setpoints`, `f_to_c` and `c_to_f` in `chestnut_logic.h` (header-only, `inline`). Write the Dockerfile (`FROM esphome/esphome:2026.10.1`, `RUN pip install pytest==8.3.* pytest-asyncio==0.24.*`) and `run.sh` (builds the image `chestnut-m2-tests`, mounts `tab5-thermostat` at `/config`, reuses the `chestnut-console_esphome-cache` volume at `/cache`).
- [ ] **Step 4: Run the tests and watch them pass**: `run.sh unit`. Expected: `test_logic: 9 checks passed`, exit 0.
- [ ] **Step 5: Commit**: `git add tab5-thermostat/thermostat tab5-thermostat/tests && git commit -m "M2: setpoint derivation and unit-test harness"`

### Task 2: The schedule lookup

**Files:** Modify `thermostat/chestnut_logic.h`; Modify `tests/unit/test_logic.cpp`

**Interfaces:**
- Consumes: Task 1's header and harness.
- Produces:
  - `struct Period { int start_min; bool eco; };` (minute of day, 0–1439)
  - `struct Week { Period weekday[4]; Period weekend[4]; };` (index 0..3 = Wake, Leave, Return, Sleep)
  - `struct ScheduleState { int period; bool eco; int key; int next_dow; int next_min; };`
    - `key` identifies the active period *instance*: `start_dow*1440 + start_min` of the occurrence that's in force. It changes exactly when a new period starts.
    - `next_dow` / `next_min` give the next start.
  - `ScheduleState schedule_at(const Week&, int dow /*0=Mon..6=Sun*/, int minute);`
  - `const char *period_name(int period);` → "Wake" / "Leave" / "Return" / "Sleep"
  - `std::string format_12h(int minute);` → "6:30 am", "12:00 pm", "12:05 am", "10:30 pm"

Rules:
- Mon–Fri use `weekday`, Sat–Sun use `weekend`. Within a day, periods apply in **start-time order** (not index order).
- Before the day's first start, the previous day's last-starting period is still in force: its `key` uses the previous day, and its `eco` is that period's level.
- The next change is the next start strictly after `minute`, searching up to 7 days ahead.

- [ ] **Step 1: Write the failing tests.** Use the spec's default week: weekday 6:30 C, 8:30 E, 17:30 C, 22:30 E; weekend 8:00 C, 10:00 C, 17:00 C, 23:00 E.
  - `schedule_basic`: Mon 9:00 → period 1 (Leave), eco, next Mon 17:30.
  - `schedule_midnight_carryover`: the key at Mon 23:00 equals the key at Tue 02:00, both Sleep and eco. Tue 06:30 → Wake, with a different key.
  - `schedule_weekend_boundary`: Fri 23:00 → Sleep (weekday), next = Sat 8:00. Mon 05:00 → Sun's Sleep (23:00, eco), next Mon 6:30.
  - `schedule_out_of_order_times`: weekday Leave start 5:00 (before Wake 6:30). At 5:30 → Leave; at 7:00 → Wake; at 9:00 → still Wake (Leave is past); at 17:30 → Return. No crash, and every key is distinct.
  - `format_12h_cases`: 0 → "12:00 am", 390 → "6:30 am", 720 → "12:00 pm", 1350 → "10:30 pm".
- [ ] **Step 2: Run `run.sh unit`.** Expected: a compile error, `schedule_at` not declared.
- [ ] **Step 3: Implement** `schedule_at`, `period_name` and `format_12h`.
- [ ] **Step 4: Run `run.sh unit`.** Expected: all pass.
- [ ] **Step 5: Commit** `"M2: schedule lookup"`.

### Task 3: Sensor sanity checker

**Files:** Modify `thermostat/chestnut_logic.h`, `tests/unit/test_logic.cpp`

**Interfaces:**
- Produces:

```cpp
struct SanityConfig { uint32_t stale_ms, frozen_ms, recover_ms; float min_c, max_c, spike_c; };
class SanityChecker {
 public:
  explicit SanityChecker(SanityConfig);
  void on_reading(uint32_t now_ms, float c);  // NaN allowed
  void tick(uint32_t now_ms);                 // call at least every second
  bool fault() const;
  float value() const;                        // last accepted reading; NaN while fault() or before the first reading
};
```

- Production values (spec, safety item 4): `stale 2×unit`, `frozen 30×unit`, `recover 5×unit` (unit = `timer_unit_s`×1000 ms), `min 2.0`, `max 40.0`, `spike 2.0`. All `uint32_t` time arithmetic is difference-based, so it's wrap-safe.

Rules:
- **Bad:** NaN; outside [min, max]; no reading for `stale_ms`; the identical value (`==`) for `frozen_ms`.
- **Spike:** a reading more than `spike_c` from the last accepted one is held back. If the next reading is within `spike_c` of the held one, both are accepted (a real change). Otherwise the held one is dropped.
- **Fault starts** at the first bad condition. **It clears** after `recover_ms` of continuous good readings; any bad reading restarts that window.
- **Startup:** `value()` is NaN before the first good reading, but `fault()` is false until `stale_ms` has passed without one.

- [ ] **Step 1: Write the failing tests** (unit = 1000 ms):
  - `sanity_nan_faults_immediately`
  - `sanity_out_of_range` (45.0 → fault)
  - `sanity_stale` (no reading for 2001 ms → fault)
  - `sanity_frozen` (21.5 for 30001 ms → fault; 21.5 then 21.51 alternating → no fault)
  - `sanity_spike_filtered` (21 → 31 → 21.1: no fault, value stays ~21)
  - `sanity_real_jump_accepted` (21 → 24 → 24.1: value 24.1)
  - `sanity_recovery_after_5_units` (fault at t; good readings every 250 ms; `fault()` still true at t+4999, false at t+5001)
  - `sanity_recovery_restarts_on_bad`
  - `sanity_millis_wrap` (start at 0xFFFFF000)
- [ ] **Step 2: Run `run.sh unit`.** Expected: a compile failure.
- [ ] **Step 3: Implement `SanityChecker`.**
- [ ] **Step 4: Run `run.sh unit`.** Expected: all pass.
- [ ] **Step 5: Commit** `"M2: sensor sanity checker"`.

### Task 4: House physics

**Files:** Create `sim/house_model.h`, `tests/unit/test_house.cpp`

**Interfaces:**
- Produces:
  - `struct HouseParams { float tau_h = 8, heat_fph = 10, cool_fph = 5; };`
  - `float house_step(float room_f, float outdoor_f, bool w, bool y, float dt_s, const HouseParams&);`
    - Euler step of `dT/dt = (Tout − T)/τ + heat·W − cool·Y`, in hours.
    - G has no effect.
  - `enum class Weather { Fixed, Winter, Summer };`
  - `float weather_outdoor_f(Weather, float fixed_f, int minute_of_day);`
    - Fixed returns `fixed_f`.
    - Winter is a cosine with its minimum, 25°F, at 5:00 and its maximum, 45°F, at 15:00.
    - Summer is the same shape with 70°F and 95°F.

- [ ] **Step 1: Write the failing tests:**
  - `house_drifts_toward_outdoor`: 68°F, outdoor 30, one hour in 1 s steps → between 63 and 64.5.
  - `house_heats`: 68°F, outdoor 68, W on for one hour → 78 ± 0.2.
  - `house_cools`: 78°F, outdoor 78, Y on for one hour → 73 ± 0.2.
  - `house_fan_only_no_effect`
  - `weather_winter_extremes`: 25 at 300 and 45 at 900, ±0.01.
  - `weather_summer_extremes`
- [ ] **Step 2: Run `run.sh unit`.** Expected: fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run `run.sh unit`.** Expected: all pass.
- [ ] **Step 5: Commit** `"M2: house physics"`.

### Task 5: Virtual house package, host entries and the scenario harness

**Files:**
- Create:
  - `sim/virtual-house.yaml`
  - `main-thermostat-sim.yaml`
  - `tests/main-thermostat-test.yaml`
  - `tests/scenarios/conftest.py`
  - `tests/scenarios/test_sim.py`
- Modify: `tests/run.sh` (add `scenarios`), `tab5-thermostat/secrets.yaml.example` (add `sim_api_encryption_key: "paste-output-of-openssl-rand-base64-32"`)

**Interfaces:**
- Consumes: Task 4 (`house_model.h` via `esphome: includes:`).
- Produces (`virtual-house.yaml`):
  - The contract ids `room_temperature` (template sensor, **°C**, published every `${sim_publish_interval}` with ±0.05°C uniform noise) and `room_humidity` (%, from `sim_humidity` ± 0.3 noise).
  - `relay_heat` / `relay_cool` / `relay_fan` / `relay_ob` (template switches, optimistic, ALWAYS_OFF, internal).
  - Knobs, restored:
    - `sim_outdoor_f` (number, °F, −10..110, default 35)
    - `sim_weather` (select Fixed / Winter day / Summer day)
    - `sim_tau_h` (number, 1–24, default 8)
    - `sim_heat_fph` (number, default 10)
    - `sim_cool_fph` (number, default 5)
    - `sim_humidity` (number, 20–80, default 45)
    - `sim_fault` (select None / Unplugged / Frozen / Out of range / Spike)
    - `sim_room_f` (sensor, the true room temperature, for tests and the browser)
  - Physics: an `interval: 1s` step with `dt = 1 × ${sim_speed}`. The room starts at 68°F.
  - Faults:
    - **Unplugged** stops publishing.
    - **Frozen** republishes the last value with no noise.
    - **Out of range** publishes 60.0.
    - **Spike** publishes one +10°C reading, then sets itself back to None.
- Produces (host entries):
  - Both entries: `host:`, `time: - platform: host id: host_time timezone: America/New_York`, and `packages: {sim: !include sim/virtual-house.yaml}` (the logic package gets added in Task 6).
  - `main-thermostat-sim.yaml`: name `main-thermostat-sim`, friendly "Main Thermostat (Sim)", `api: {encryption: {key: !secret sim_api_encryption_key}, reboot_timeout: 0s}`.
  - `tests/main-thermostat-test.yaml`: name `main-thermostat-test`, API with no encryption on port 6053, the test substitutions from the table above, and an API action `test_force_relays(heat: bool, cool: bool)` that turns `relay_heat`/`relay_cool` on or off directly.
- Produces (`conftest.py`):
  - Fixture `device` (function scope):
    - starts the compiled host binary as a subprocess with a fresh preferences dir;
    - waits until the API answers;
    - yields a `Dev` helper; stops the process on teardown.
  - Fixture `device_keep_prefs` for restart tests.
  - `Dev` methods:
    - `await dev.state(object_id)` → the latest value, or None while unknown;
    - `await dev.wait_for(object_id, pred, timeout_s)`;
    - `await dev.set_number(object_id, v)`, `select(object_id, option)`, `switch(object_id, on)`, `press(object_id)`;
    - `climate(mode=None, fan_mode=None, target_temperature=None, target_temperature_low=None, target_temperature_high=None)`;
    - `await dev.action(name, **kwargs)`;
    - `await dev.restart()` (same prefs dir).
  - Entities are looked up by object_id.

- [ ] **Step 1: Find where host builds put the binary and the preferences file.** Compile the test entry with no tests: `run.sh build`, i.e. `esphome compile tests/main-thermostat-test.yaml` in the test image. Record the program path (expected under `tests/.esphome/build/main-thermostat-test/`) and the preferences location from `esphome/components/host/preferences.cpp` in `conftest.py` constants. Expected: the build succeeds.
- [ ] **Step 2: Write the failing scenario tests** in `test_sim.py`:
  - `test_room_drifts_toward_outdoor`: Fixed weather, outdoor 30°F. Within 20 s, `sim_room_f` < 67.
  - `test_forced_heat_warms`: `test_force_relays(heat=True, cool=False)`, outdoor 68. Within 20 s, `sim_room_f` > 69.
  - `test_room_temperature_is_celsius_with_noise`: two consecutive `room_temperature` values differ, and both are within 0.2 of `f_to_c(sim_room_f)`.
  - `test_fault_unplugged_stops_publishing`: no new `room_temperature` for 2 s.
  - `test_fault_out_of_range`: `room_temperature` == 60.0.
- [ ] **Step 3: Run `run.sh scenarios -k sim`.** Expected: fail (the package doesn't exist yet).
- [ ] **Step 4: Implement** `virtual-house.yaml`, both entries, `conftest.py` and `run.sh scenarios`.
- [ ] **Step 5: Run `run.sh scenarios -k sim`.** Expected: 5 passed. Also run `esphome config main-thermostat-sim.yaml`. Expected: `Configuration is valid!`
- [ ] **Step 6: Commit** `"M2: virtual house, host entries, scenario harness"`.

### Task 6: Thermostat core: climate, equipment calls and timers

**Files:**
- Create: `thermostat/logic.yaml`, `tests/scenarios/test_core.py`
- Modify: both host entries (add `logic: !include thermostat/logic.yaml`)

**Interfaces:**
- Consumes: the contract ids from Task 5; `chestnut_logic.h` via `esphome: includes:`.
- Produces:
  - **`main_thermostat`** (platform `thermostat`):
    - `sensor: checked_temperature_c`, an internal °C template sensor. In this task it just mirrors `room_temperature`; Task 8 puts the sanity checker in front.
    - `humidity_sensor: room_humidity`.
    - Modes OFF / HEAT / COOL / HEAT_COOL. `fan_mode_auto_action` and `fan_mode_on_action`.
    - `startup_delay: true`, `min_idle_time: ${min_idle_s}s`, and the four min run/off times from the substitutions.
    - `visual: {min_temperature: 10, max_temperature: 32.2, temperature_step: 0.5}`.
    - Default preset with `mode: "OFF"`, `default_target_temperature_low: 22.2`, `default_target_temperature_high: 23.3`.
  - **Actions** (spec, "Equipment calls"):
    - `heat_action`: relay_cool off, relay_heat on, relay_fan off unless fan mode is ON.
    - `cool_action`: relay_heat off, relay_cool on, relay_fan on.
    - `idle_action`: relay_heat off, relay_cool off, relay_fan on iff fan mode is ON.
    - `fan_mode_on_action`: relay_fan on.
    - `fan_mode_auto_action`: relay_fan off unless action is COOLING.
  - `call_heat` / `call_cool` / `call_fan`: template binary sensors mirroring the relays (100 ms lambda, or published from the relay switches' `on_turn_on`/`on_turn_off` in the sim and hardware packages; pick the lambda, so it works the same with any relay package).
  - **Timer numbers** `heat_min_run`, `heat_min_off`, `cool_min_run`, `cool_min_off`, `changeover_lockout`:
    - minutes, entity_category config, restored;
    - ranges and defaults from the spec's table;
    - `on_value` calls `id(main_thermostat).set_heating_minimum_run_time_in_sec(x * ${timer_unit_s})` (and friends; `changeover_lockout` goes to a global used in Task 9).
  - `checked_temperature` (°F sensor, contract) mirrors `checked_temperature_c`.

- [ ] **Step 1: Write the failing tests** in `test_core.py`. All use the test entry; the room is set via `sim_outdoor_f` and Fixed weather; targets via the climate's low/high in °C for now (Task 9 moves them to `set_target`).
  - `test_boot_no_calls_during_startup_delay`: right after start, Heat with the room below target. `call_heat` stays off for ≥ 2.5 s, then turns on within 6 s.
  - `test_heat_calls_w_only`: during heating, call_heat on, call_cool off, call_fan off.
  - `test_cool_calls_y_and_g`
  - `test_fan_on_calls_g_alone_in_off`
  - `test_ob_never_on`: no switch named relay_ob is exposed, and the sim's `test_force_relays` has no ob argument (structural).
  - `test_min_run_holds_call`: heating starts; set the target far below at once; call_heat stays on until ≥ 3 s after it started.
  - `test_min_off_blocks_restart`: cooling stops; drop the target; call_cool stays off until ≥ 5 s after the stop.
  - `test_timer_number_clamps`: setting `cool_min_off` to 2 is refused or clamped (the state stays ≥ 5).
- [ ] **Step 2: Run `run.sh scenarios -k core`.** Expected: fail (no climate).
- [ ] **Step 3: Implement `thermostat/logic.yaml` as above.**
- [ ] **Step 4: Run `run.sh scenarios -k core`.** Expected: 8 passed.
- [ ] **Step 5: Commit** `"M2: thermostat core, equipment calls, timers"`.

### Task 7: Interlock watchdog

**Files:** Modify `thermostat/logic.yaml`; Create `tests/scenarios/test_interlock.py`

**Interfaces:**
- Produces:
  - `interlock_fault` (binary_sensor, device_class problem). Latched in global `g_interlock_latched` (bool, not restored; a reboot clears it).
  - `clear_interlock_fault` (button).
  - An `interval: 100ms` watchdog: if relay_heat and relay_cool are both on, turn both off, set the latch and log an ERROR.
  - While latched, `heat_action` and `cool_action` don't turn their relay on (each action body is wrapped in `if: not g_interlock_latched`).
  - Global `g_interlock_latched`, for Task 8's `call_wait_reason`.

- [ ] **Step 1: Write the failing tests:**
  - `test_both_relays_trip_watchdog`: `test_force_relays(heat=True, cool=True)`. Within 1 s: call_heat off, call_cool off, interlock_fault on.
  - `test_latched_blocks_calls`: after the trip, Heat with the room 5°F below target; call_heat stays off for 8 s.
  - `test_clear_restores`: press `clear_interlock_fault`; within 8 s heating resumes and interlock_fault is off.
- [ ] **Step 2: Run `run.sh scenarios -k interlock`.** Expected: fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run `run.sh scenarios -k interlock`.** Expected: 3 passed.
- [ ] **Step 5: Commit** `"M2: interlock watchdog"`.

### Task 8: Sensor sanity in the loop, sensor_fault and call_wait_reason

**Files:** Modify `thermostat/logic.yaml`; Create `tests/scenarios/test_sensor.py`

**Interfaces:**
- Consumes: `SanityChecker` (Task 3); `g_interlock_latched` (Task 7).
- Produces:
  - A global `chestnut::SanityChecker` built with the spec's production values scaled by `${timer_unit_s}`.
  - `room_temperature` `on_value` feeds `on_reading`; an `interval: 1s` calls `tick`. Both publish `checked_temperature_c` = `value()` (NaN on a fault) and `sensor_fault` = `fault()`.
  - `call_wait_reason` (text_sensor), recomputed every second, first match wins:
    1. "Interlock fault" if latched;
    2. "Sensor fault";
    3. "Starting up" while uptime is under the startup delay (`max(heat_off, cool_off)`);
    4. "Changeover wait" while the Task 9 lockout is active and the room is past the other side's threshold;
    5. "Short-cycle protection" when the room is past the threshold for the selected mode but the action is IDLE;
    6. otherwise "".
  - `action_elapsed` (sensor, s): reset on each `main_thermostat` action change (`on_state` compares with the last action) and published every 30 s.

- [ ] **Step 1: Write the failing tests:**
  - `test_unplugged_faults_and_stops_new_calls`: idle in Heat with the room at target. Set `sim_fault` Unplugged, then drop the outdoor temperature. Within 3 s `sensor_fault` is on, and call_heat stays off for 6 s.
  - `test_fault_mid_run_finishes_min_run`: heating just started; Out of range. call_heat stays on until ≥ 3 s after its start, then turns off within 2 s. `sensor_fault` turns on within 1 s.
  - `test_frozen_faults`: Frozen. Fault within 32 s.
  - `test_spike_does_not_fault`
  - `test_recovery_after_5_units`: fault, then None. `sensor_fault` is still on at +4 s and off by +7 s.
  - `test_recovery_respects_cool_min_off`: cooling stops because of a fault at t0; recovery comes at about t0 + 5 s. call_cool doesn't come on before t0 + 5 s (the AC's minimum off), and does come on within 10 s.
  - `test_wait_reason_values`: "Sensor fault" during a fault, "Starting up" right after boot, "" while heating.
  - `test_action_elapsed_resets`
- [ ] **Step 2: Run `run.sh scenarios -k sensor`.** Expected: fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run `run.sh scenarios -k sensor`.** Expected: 8 passed.
- [ ] **Step 5: Commit** `"M2: sensor sanity, sensor_fault, call_wait_reason, action_elapsed"`.

### Task 9: Comfort, Eco, set_target holds, Auto and HA writes

**Files:** Modify `thermostat/logic.yaml`; Create `tests/scenarios/test_targets.py`

**Interfaces:**
- Consumes: `derive_setpoints`, `f_to_c` (Task 1).
- Produces:
  - **Entities:**
    - `comfort_target` (number °F 50–90 step 1, default 72, restored);
    - `eco_offset` (2–10, default 4, restored);
    - `comfort_level` (select Comfort / Eco, restored);
    - `set_target` (number °F 50–90 step 1, not restored);
    - `effective_target`, `effective_low`, `effective_high` (°F sensors);
    - `schedule_hold` (binary_sensor).
  - **Globals:** `g_hold` (bool), `g_hold_f` (int), `g_applying` (bool), `g_sched_setting` (bool: set while the Task 10 schedule changes `comfort_level`, so it isn't a hold), `g_lockout_until_ms` (uint32), `g_last_call` (enum heat/cool/none).
  - **Script `apply_setpoints`:**
    1. Run `derive_setpoints` with the climate's mode, comfort_target, eco_offset, comfort_level == Eco, g_hold and g_hold_f.
    2. Publish the three effective sensors.
    3. Set `g_applying`, then make a climate call with `target_temperature_low` / `high` in °C, then clear `g_applying`.
  - It runs on boot, on any of those entities changing, and on mode changes.
  - **Holds:**
    - `set_target` `on_value`: if the value equals the current effective target, do nothing (Review Focus 5). Otherwise `g_hold = true; g_hold_f = x`, then apply.
    - `comfort_level` `on_value`, coming from a user (not from the Task 10 schedule, which sets a flag `g_sched_setting`): if it's the same as the previous option, do nothing. Otherwise `g_hold = true; g_hold_f = effective in the new level`, then apply.
    - With `schedule_enabled` off (Task 10), a `set_target` change sets `comfort_target` instead of starting a hold. Add that branch in Task 10.
  - **`main_thermostat` `on_control`**, when `!g_applying` and the call carries a target temperature (target, low or high):
    - Read the user's °F: Heat uses the low or target; Cool uses the high or target; Auto uses the midpoint of low and high if both are given, else whichever one is given.
    - Strip the temperatures from the call (re-set them to the current derived values).
    - Then `number.set set_target` to the rounded °F.
  - **Auto changeover lockout:** when a HEATING or COOLING action ends in HEAT_COOL mode, record `g_last_call` and `g_lockout_until_ms = now + changeover_lockout×unit×1000`. Before the other call starts, `heat_action`/`cool_action` check the lockout. If it's active, they stay idle and leave the work to `call_wait_reason`. *Builder note:* ESPHome's thermostat already decided the action, so implement the block by keeping the relay off and re-running `refresh()` when the lockout expires (an `interval: 1s` check), and test that the reported action matches the relays.

- [ ] **Step 1: Write the failing tests:**
  - `test_eco_heat_band`: Heat, comfort 72, Eco 4 → `effective_target` 68, and heating starts only below about 67.
  - `test_eco_cool_band`: effective 76.
  - `test_auto_single_target`: Auto 72 → effective_low 71, high 73; heats below and cools above.
  - `test_auto_eco_band`: 67 / 77.
  - `test_set_target_starts_hold_comfort_untouched`: in Eco, set_target 69 → schedule_hold on, effective 69, comfort_target still 72.
  - `test_same_value_no_hold`: set_target to the current effective value, and select the current level again → schedule_hold stays off.
  - `test_ha_setpoint_write_becomes_hold`: Heat, a climate call with `target_temperature_low = f_to_c(70)` → set_target 70, hold on, effective 70, and the climate low reads back as `f_to_c(70)` ± 0.1.
  - `test_auto_changeover_lockout`: heating ends in Auto, then the room rises above high. call_cool stays off until ≥ 30 s after the heat ended, while call_wait_reason == "Changeover wait".
  - `test_manual_heat_to_cool_no_lockout`: heating ends; the mode switches to Cool with the room above target. Cooling starts after only the AC's minimum off.
  - `test_mode_change_mid_run_finishes`: the spec's "mode change mid-run", which the screen's "Finishing up" relies on. During heating that started under 3 s ago, switch to Cool. The climate reports mode COOL at once, its action stays HEATING with call_heat on until ≥ 3 s after the start, then IDLE.
- [ ] **Step 2: Run `run.sh scenarios -k targets`.** Expected: fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run `run.sh scenarios -k "targets or core"`** (core targets now go through set_target, so update the core tests' helpers). Expected: all pass.
- [ ] **Step 5: Commit** `"M2: comfort/eco, holds, auto lockout, HA writes"`.

### Task 10: On-device schedule

**Files:** Modify `thermostat/logic.yaml`, `tests/main-thermostat-test.yaml`; Create `tests/scenarios/test_schedule.py`

**Interfaces:**
- Consumes: `schedule_at`, `period_name`, `format_12h` (Task 2); the Task 9 globals and `apply_setpoints`.
- Produces:
  - **Entities:**
    - 16 restored settings: `sched_{weekday,weekend}_{wake,leave,return,sleep}_time` (datetime, `type: time`, `optimistic`, `restore_value: true`, the spec's default times) and `sched_..._level` (select Comfort / Eco, the spec's defaults);
    - `schedule_enabled` (switch, restored, default on);
    - `schedule_period`, `schedule_next_change`, `schedule_status` (text sensors);
    - `resume_schedule` (button).
  - **Globals:** `g_hold_key` (int), `g_last_dow` / `g_last_min` / `g_clock_valid`.
  - **Script `schedule_evaluate(valid: bool, dow: int, minute: int)`:**
    1. Store the inputs.
    2. If the schedule is disabled: clear the hold, set the period and next change to "", status "Schedule off".
    3. Else if `!valid`: status "Schedule paused: clock not set", and nothing changes.
    4. Else build the `Week` from the entities and run `schedule_at`:
       - If `g_hold` and the key differs from `g_hold_key`, end the hold.
       - If not holding, set `comfort_level` to the period's level (with `g_sched_setting` set) when it differs.
       - Publish the period name, `format_12h(next)` and the status: "Comfort until 5:30 pm", "Eco until 5:30 pm", or "Holding 69° until 10:30 pm".
       - Then apply.
  - When a hold starts (Task 9), store `g_hold_key = current key`.
  - An `interval: ${schedule_tick}` calls `schedule_evaluate` with `id(${clock_id}).now()`:
    - `is_valid()`;
    - `day_of_week` mapped from ESPHome's 1=Sun..7=Sat to 0=Mon..6=Sun;
    - `hour*60+minute`.
  - Any schedule entity change, or `resume_schedule`, re-runs it with the stored last inputs (Resume clears the hold first).
  - `on_boot` (priority −100) runs it once from the real clock. A hold doesn't survive a reboot.
  - Test entry: API action `test_clock(dow: int, minute: int, valid: bool)` → `schedule_evaluate`.
  - The Task 9 branch: with the schedule off, `set_target` sets `comfort_target`.

- [ ] **Step 1: Write the failing tests** (via `test_clock`):
  - `test_period_switches_level`: Mon 8:29 → Comfort, "Comfort until 8:30 am". 8:30 → Eco, period "Leave", next "5:30 pm".
  - `test_hold_until_next_period`: Mon 9:00 Eco; set_target 70 → hold, status "Holding 70° until 5:30 pm". 17:29 → still held. 17:30 → hold off, Comfort, effective = comfort.
  - `test_hold_survives_midnight`: Mon 23:00 hold; Tue 02:00 still held; Tue 6:30 released.
  - `test_resume_clears_hold`
  - `test_schedule_off`: no switching, status "Schedule off", and set_target changes comfort_target with no hold.
  - `test_clock_invalid_pauses`: status "Schedule paused: clock not set", and the level is unchanged.
  - `test_edit_period_reevaluates`: change weekday Leave to 9:00 while at Mon 8:45 → back to Comfort (Wake) at once.
  - `test_weekend_uses_weekend_set`
- [ ] **Step 2: Run `run.sh scenarios -k schedule`.** Expected: fail.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run `run.sh scenarios -k schedule`, then `run.sh all`.** Expected: all pass.
- [ ] **Step 5: Commit** `"M2: on-device schedule"`.

### Task 11: Persistence across restart

**Files:** Create `tests/scenarios/test_persistence.py` (logic fixes only if the test finds gaps)

- [ ] **Step 1: Write the failing test:**
  - `test_settings_survive_restart` (uses `device_keep_prefs`): set mode Cool, fan On, comfort 70, eco 6, cool_min_off 8, weekday Sleep 23:15 Eco, and schedule_enabled off.
  - Wait 2 s (preference flush; set `preferences: flash_write_interval: 0s` in the test entry if needed).
  - `dev.restart()`, then read all of them back.
  - Also check that `schedule_hold` is off after the restart, and that no relay is on before the startup delay.
- [ ] **Step 2: Run `run.sh scenarios -k persistence`.** Expected: a fail or a pass. If it passes first time, note it in the commit message; the test still locks the behaviour in.
- [ ] **Step 3: Fix any setting that doesn't restore** (`restore_value` / `restore_mode` on its entity). The climate restores its own mode and fan mode.
- [ ] **Step 4: Run `run.sh all`.** Expected: all pass.
- [ ] **Step 5: Commit** `"M2: persistence test"`.

### Task 12: Run the logic on the Tab5, docs and review request

**Files:**
- Modify:
  - `tab5-thermostat/tab5-thermostat.yaml`: replace `contract: !include ui/dev/contract-stub.yaml` with `logic: !include thermostat/logic.yaml` and `sim: !include sim/virtual-house.yaml`; add substitution `clock_id: sntp_time`.
  - `AGENTS.md`: the repo layout gets `thermostat/`, `sim/`, `tests/`; milestone 2 status; the contract table gets "relays are internal".
  - `tab5-thermostat/README.md`: how to run the tests and the host sim, and how to add the sim to HA.
- Leave `preview/console-preview.yaml` on the stub (spec: the PC owns that side).

- [ ] **Step 1: Validate the device config:** `docker compose run --rm --no-deps esphome config tab5-thermostat.yaml`. Expected: `Configuration is valid!`, with no id clashes. The console's packages must resolve every contract id from the logic package.
- [ ] **Step 2: Compile for the Tab5** in the background (the first ESP-IDF toolchain download is large): `docker compose run --rm --no-deps esphome compile tab5-thermostat.yaml`. Expected: `SUCCESS`.
- [ ] **Step 3: Run the full test suite once more:** `tab5-thermostat/tests/run.sh all`. Expected: all pass.
- [ ] **Step 4: Run the play sim:** build and run `main-thermostat-sim.yaml` with API port 6053 published. Confirm with a one-off `aioesphomeapi` listing that every contract id appears.
- [ ] **Step 5: Commit** `"M2: run the logic on the Tab5 against the virtual house; docs"`, then push.
- [ ] **Step 6: Post a review request** on beacon `#chestnut-console` to `@pc-chestnut-console`. Include the branch, the commit, `git diff main...mac/thermostat-logic`, the test counts, and the asks: flash the Tab5 after approval, and add the sim to HA and the HA notification automation for `sensor_fault` / `interlock_fault` (`home-assistant/`, PC-owned).
