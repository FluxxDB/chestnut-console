# Milestone 4 bench rig: implementation plan (Mac side)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The virtual house provides the two new contract ids (`relay_fault`, `temperature_offset`), and the logic pauses heating and cooling at once on a relay fault and resumes safely after it clears.

**Architecture:** M1 adds both ids to `sim/virtual-house.yaml`, with a Sim Fault option that raises the relay fault, so the PC's wall-screen, dashboard and HA-alert tasks can build against the sim. M2 adds a relay hold to `thermostat/logic.yaml`, modelled on the interlock latch: cut W and Y at once, guard the heat and cool actions, hold for the larger minimum off time counted from the fault, then reset the thermostat's stale action. M3 updates the contract table. M1 ships on its own branch first; M2 and M3 follow on a second branch. M2 must not merge before M1.

**Tech Stack:** ESPHome 2026.10.1 (host platform for the tests), C++17 lambdas, pytest + aioesphomeapi scenario tests (`tab5-thermostat/tests/run.sh`).

**Spec:** `docs/superpowers/specs/2026-11-18-bench-rig-design.md` (on `pc/bench-rig-design`; approved by Dang 2026-11-18). Its exact schemas are in the PC plan's Global Constraints, `docs/superpowers/plans/2026-11-18-bench-rig.md`.

## Global Constraints

- Public repo: no IPs, Wi-Fi details, keys, passwords or photos.
- Pinned: ESPHome 2026.10.1. The logic package stays shared by the virtual house, the host sim, the tests and the real hardware (no hardware-specific copy).
- `relay_fault`: binary sensor, `device_class: problem`, name **"Relay Fault"** (object id `relay_fault`).
- `temperature_offset`: number, name **"Temperature Offset"**, unit `°F`, **no `device_class`**, min −5.0, max 5.0, step 0.1, initial 0, restored, `entity_category: config`. Applied to the reading in °C as `offset_f * 5 / 9`.
- Sim Fault option, exactly: `Relay unit unplugged`.
- `call_wait_reason` text, exactly: `Relay fault`. Priority: `Interlock fault`, then `Relay fault`, then `Sensor fault`.
- Relay fault in the logic (spec): cut every call **at once** (no min-run finish), no call until it clears, the minimum off time counted **from the fault**.
- **Mac calls** (posted on beacon 2026-11-18, GZGVTKQ5):
  - the hold lasts the larger of `heat_min_off` / `cool_min_off` × `timer_unit_s` from the fault's latest start, or until the fault clears, whichever is later;
  - G during the hold follows the interlock rule: cut unless fan mode is On (so with Fan On, G is commanded on and comes back on the PC driver's resync; agreed with the PC on beacon 2026-11-18, 9H2GQH0W);
  - after the fault clears while the hold still counts, the wait reason is the existing `Short-cycle protection`;
  - the sim's relay fault does **not** copy the hardware's Port A cut, so no sensor fault comes with it;
  - the offset is added to the sim's base reading before the fault branches (Frozen repeats the last value including its offset; Out of range stays 60.0 °C). `sim_room_f` stays the true temperature, with no offset.

## Review Focus

1. **A relay fault while a call is inside its minimum run:** W (or Y and G) drops within a tick, not when the min run ends. Pinned by `test_relay_fault_cuts_heat_at_once` (Task 2).
2. **A fault shorter than the minimum off:** the call restarts no sooner than the larger min off after the fault began, measured on the device. Pinned by `test_short_fault_holds_min_off_from_fault` (Task 2).
3. **The thermostat still believes it is HEATING after the hold** (its action never ran again): the call resumes by itself. Pinned by `test_call_resumes_after_fault_clears` (Task 2).
4. **Relay and sensor faults together** (every lasting hardware fault, from the Port A cut): the reason is `Relay fault`, and calls stay off until both clear. Pinned by `test_relay_beats_sensor_in_wait_reason` and `test_relay_clears_while_sensor_faulted` (Task 2).
5. **The offset across a reboot, and not on the true room:** restored after a restart, and `sim_room_f` unchanged. Pinned by `test_offset_restored_and_true_room_unchanged` (Task 1).

---

### Task 1 (M1): the virtual house provides `relay_fault` and `temperature_offset`

Branch `mac/bench-rig-sim` off main. This plan file goes in its first commit.

**Files:**
- Modify: `tab5-thermostat/sim/virtual-house.yaml` (header comment, `sim_fault` options, the publish lambda; new `binary_sensor:` and a number)
- Modify: `tab5-thermostat/README.md:94` (the "Playing with the virtual house" paragraph: the new fault option and the offset)
- Test: `tab5-thermostat/tests/scenarios/test_sim.py`

**Interfaces:**
- Produces: `relay_fault` (template binary sensor with **no lambda**, `publish_initial_state: true`, published from `sim_fault`'s `on_value` as `x == "Relay unit unplugged"`, so the test entry can also publish it on its own), `temperature_offset` (template number, `optimistic: true`, `restore_value: true`, `mode: box`), and `sim_fault` options `["None", "Unplugged", "Frozen", "Out of range", "Spike", "Relay unit unplugged"]`.

- [ ] **Step 1: Write the failing tests** in `test_sim.py`:
  - `test_relay_fault_follows_sim_fault`: `relay_fault` is `False` once known; select `Relay unit unplugged` → `True` within 1 s; select `None` → `False` within 1 s; `room_temperature` keeps publishing throughout (its update count rises while the fault is on).
  - `test_relay_fault_schema`: `device.info("relay_fault").device_class == "problem"`, name `"Relay Fault"`.
  - `test_temperature_offset_schema`: `info("temperature_offset")` has unit `°F`, `device_class` empty, min −5.0, max 5.0, step 0.1, `entity_category` config; the state is 0 at first boot.
  - `test_offset_moves_reading`: fixed weather at 68, offset 0: the mean of 8 `room_temperature` readings minus `f_to_c(sim_room_f)` is within 0.06 °C of 0. Set the offset to 1.8 → the same difference is within 0.06 °C of 1.0. Set it to −1.8 → within 0.06 of −1.0.
  - `test_offset_restored_and_true_room_unchanged` (`device_keep_prefs`): set the offset to 2.5, restart → the offset is 2.5, and `sim_room_f` starts near 68 (no offset in the true room).
  - Extend `test_knobs_survive_restart_fault_does_not`: select `Relay unit unplugged` before the restart → `relay_fault` is `False` after it.
- [ ] **Step 2: Run** `tab5-thermostat/tests/run.sh scenarios tests/scenarios/test_sim.py`. Expected: the new tests FAIL (unknown entity / option).
- [ ] **Step 3: Implement** in `virtual-house.yaml`, to the Interfaces above and the Global Constraints. In the publish lambda, `true_c` becomes `(g_sim_room_f − 32) × 5/9 + offset × 5/9` before the fault branches. Update the header comment (the two new ids, and that `Relay unit unplugged` raises only `relay_fault`) and the `sim_fault` comment. README line 94: add `Relay unit unplugged` (raises **Relay Fault**) and **Temperature Offset** (°F, added to the reading, as on the real sensor). What the thermostat does on a relay fault is written in Task 2, once the logic does it.
- [ ] **Step 4: Run** `tab5-thermostat/tests/run.sh all`, then `docker compose run --rm esphome config tab5-thermostat.yaml` and `… config main-thermostat-sim.yaml`. Expected: every test passes; both configs are valid.
- [ ] **Step 5: Commit** `git add docs/superpowers/plans/2026-11-18-bench-rig-mac.md tab5-thermostat/sim/virtual-house.yaml tab5-thermostat/README.md tab5-thermostat/tests/scenarios/test_sim.py && git commit -m "Virtual house: relay_fault (Sim Fault: Relay unit unplugged) and temperature_offset"`, push, post a review request on beacon. Merge after the PC approves.

### Task 2 (M2): the logic pauses on a relay fault

Branch `mac/bench-rig-logic`, off main once Task 1 is merged (or off `mac/bench-rig-sim` until then).

**Files:**
- Modify: `tab5-thermostat/thermostat/logic.yaml` (globals, `heat_action` / `cool_action` guards, the 100 ms interval, the `call_wait_reason` lambda, `clear_interlock`, a new script, the header comment)
- Modify: `tab5-thermostat/tests/main-thermostat-test.yaml` (a test-only sensor and action)
- Modify: `tab5-thermostat/README.md:94` (the relay-fault sentence: Relay Fault pauses heating and cooling at once, and they resume after the minimum off time)
- Create: `tab5-thermostat/tests/scenarios/test_relay_fault.py`

**Interfaces:**
- Consumes: `relay_fault` and the `Relay unit unplugged` option (Task 1).
- Produces:
  - globals `g_relay_hold` (bool, not restored, false) and `g_relay_fault_ms` (uint32_t, not restored, 0);
  - script `resume_after_cut` (mode `single`): the stale-action reset now inside `clear_interlock` (if the thermostat's action is HEATING with W off, or COOLING with Y off, set it to IDLE and `refresh()`), moved out so `clear_interlock` and the relay hold both call it;
  - test sensor `test_relay_fault_ms`: the logic's own `g_relay_fault_ms` as ms since boot, published by a 20 ms test interval whenever it changes (like `test_trip_ms`), so timings count from when the logic saw the fault;
  - test action `test_set_relay_fault(on: bool)`: publishes `relay_fault` directly, so a relay fault and a sensor fault can be on together, as the hardware's Port A cut makes them.

- [ ] **Step 1: Write the failing tests** in `test_relay_fault.py`, using `test_core`'s helpers and `HOLD_S = max(HEAT_OFF_S, COOL_OFF_S)`. `fault_on(dev)` selects `Relay unit unplugged` and returns `wait_device_time("test_relay_fault_ms")`; `fault_off(dev)` selects `None`.
  - `test_relay_fault_cuts_heat_at_once`: heat running (`heat_to` 80, outdoor 0, W on). Fault on → `call_heat` off within 0.5 s of the fault (device edge `w_off − fault_ms < 300`); `call_wait_reason == "Relay fault"`; the mode is still HEAT.
  - `test_relay_fault_cuts_cool_and_fan`: cooling (outdoor 100, `cool_to` 60, fan Auto). Fault on → `call_cool` and `call_fan` off within 0.5 s.
  - `test_relay_fault_keeps_g_with_fan_on`: cooling with fan mode ON. Fault on → `call_cool` off, `call_fan` stays on (no False in its history after the fault).
  - `test_no_call_during_fault`: fault on before the startup delay ends, `heat_to` 80, sleep `HOLD_S + 3` → no True in `call_heat`'s history; the reason stays `Relay fault`.
  - `test_short_fault_holds_min_off_from_fault`: heat running; fault on, off after 1 s → the next W-on edge is `assert_near(w_on − fault_ms, HOLD_S, late_ms=250)` (the hold ends on a 100 ms tick); after `fault_off`, the reason reads `Short-cycle protection` until W comes back.
  - `test_long_fault_resumes_when_it_clears`: heat running; fault on for `HOLD_S + 2` s, then off → W comes back within 1.5 s of the clear.
  - `test_call_resumes_after_fault_clears`: as the long fault, asserting the thermostat's action was HEATING while W was off (the stale-action path ran), and the mode is still HEAT.
  - `test_relay_beats_sensor_in_wait_reason`: Sim Fault `Unplugged` until `sensor_fault` is on (reason `Sensor fault`), then `test_set_relay_fault(on=True)` → `Relay fault`.
  - `test_relay_clears_while_sensor_faulted`: continuing, `test_set_relay_fault(on=False)` and wait `HOLD_S + 1` → the reason is `Sensor fault` and no W edge; Sim Fault `None` → after the sensor recovers (5 s of good readings), W comes on.
  - `test_interlock_beats_relay_in_wait_reason`: fault on, then `test_force_relays(heat=True, cool=True)` → the reason is `Interlock fault`.
- [ ] **Step 2: Add the test hooks** in `main-thermostat-test.yaml`: the template sensor `test_relay_fault_ms` ("Test Relay Fault Ms") fed by a 20 ms interval from `g_relay_fault_ms`, and the API action `test_set_relay_fault`. Run `tests/run.sh scenarios tests/scenarios/test_relay_fault.py`. Expected: FAIL (calls not cut, no `Relay fault` reason).
- [ ] **Step 3: Implement** in `logic.yaml`:
  - **The 100 ms interval**, after the interlock part. On `relay_fault` turning on, record `g_relay_fault_ms = millis()`, set `g_relay_hold`, and log `ESP_LOGW("relay", "relay unit fault: heating and cooling paused")`. While held, cut W and Y, and G unless fan mode is On (one condition shared with the interlock: `latched || hold`). End the hold when `relay_fault` is off and `millis() − g_relay_fault_ms ≥` the larger min off × `timer_unit_s` × 1000 (the same expression as `clear_interlock`'s). Then log `relay hold ended` and run `resume_after_cut`.
  - **The guards:** `heat_action` and `cool_action` turn their relays on only when `!g_interlock_latched && !g_relay_hold`.
  - **The wait reason:** `Relay fault` while `relay_fault` is on, between the interlock and sensor branches.
  - **Comments:** the header comment and the actions' comment name the relay hold as a third reason the relays stay off.
- [ ] **Step 4: Run** `tab5-thermostat/tests/run.sh all`. Expected: all pass, including `test_interlock.py` unchanged after the `resume_after_cut` refactor.
- [ ] **Step 5: Commit** `git add tab5-thermostat/thermostat/logic.yaml tab5-thermostat/tests tab5-thermostat/README.md && git commit -m "Logic: a relay fault pauses heating and cooling at once; resume after the min off from the fault"`.

### Task 3 (M3): the contract table

**Files:**
- Modify: `AGENTS.md` (the "Package contract" table and the line above it)

- [ ] **Step 1: Edit the table.** The provider column for `room_temperature` / `room_humidity` reads `sim package, or the ENV III via hardware/bench-io.yaml`; for the relays, `sim template switches, or the Unit 4-Relay via hardware/bench-io.yaml`. Two new rows:
  - `relay_fault` | binary sensor (problem), "Relay Fault" | `bench-io.yaml`: on while the relay unit isn't answering; sim: Sim Fault `Relay unit unplugged`. The logic pauses heating and cooling at once.
  - `temperature_offset` | number, °F, −5..5 step 0.1, restored, no device_class | whichever package provides `room_temperature`, applied before the logic's sanity checks.
  - The heading becomes "Package contract (milestones 2–5)".
- [ ] **Step 2: Verify** `docker compose run --rm esphome config tab5-thermostat.yaml` is valid, and `tools/preview/test_contract.sh` passes (the stub may lack the new ids until the PC's Task 4; the check allows that).
- [ ] **Step 3: Commit** `git commit -am "AGENTS: the package contract gains relay_fault and temperature_offset"`, push `mac/bench-rig-logic`, and post the review request on beacon.
