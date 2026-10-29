# Chestnut Console: context for agents

Read this first. Deep background is in [tab5-thermostat/docs/research.md](tab5-thermostat/docs/research.md).

## What this is

Dang is turning an **M5Stack Tab5** (ESP32-P4 + ESP32-C6 Wi-Fi, 5" 720×1280 touchscreen) into a smart thermostat for his family's house, integrated with **Home Assistant** through **ESPHome**.

- The house (Northern Virginia, built 1999) has **two HVAC zones and two thermostats**. Public records suggest gas forced-air heat with central AC, and possibly a heat pump on one zone. Unconfirmed until Dang's site survey.
- **Scope now: the Main Thermostat** (Dang named it, 2026-10-28; don't call it the middle-floor thermostat). It replaces the ~25-year-old thermostat on the middle floor. The top floor keeps its newer thermostat for now. Long term, one main Tab5 should control both floors, with the top floor running its own controller and the Tab5 acting as a remote through HA.
- Dang lives in an apartment away from the house. **Nothing can be wired yet.** All work is bench work and simulation until his next visit. The house is occupied and has Wi-Fi.

## Decisions (made with Dang)

- **Firmware is ESPHome**, with C++ only for custom bits. Rust was considered and rejected on 2026-10-28: P4 support in esp-hal is basic, early (v1.3) silicon support is shaky, and there are no Rust drivers for the ST7123 panel or the C6 hosted Wi-Fi. A rewrite would rebuild what ESPHome already provides.
- **The thermostat logic runs on the Tab5 itself** (ESPHome `thermostat` climate). HA is for the phone app, remote access, history, alerts and automations. HA or Wi-Fi going down must never stop heating or cooling.
- **The electrical interface is standard relays** with dry, normally-open contacts switching R→W/Y/G (24 VAC). No power-stealing, no triacs, no hacks. Relays default OFF on boot.
- **Phone control:** the Tab5 serves its own web page (ESPHome `web_server` v3, digest auth). HA's app is the nicer option when HA is up.
- **HA hosting:** for now, Docker Compose on Dang's dev PC (WSL). At the house: the same compose file on an Ubuntu server VM (his Proxmox box), with a low-power box (HA Green or Pi) as a likely future purchase.
- **Safety requirements:** compressor/furnace min run/off times, `startup_delay: true`, a heat/cool interlock (never both on), sensor sanity checks (bad reading → stop calling + alert), and a mechanical freeze backup thermostat at install time.
- **Temperature sensing:** the Tab5 has no temperature sensor and runs warm, so it uses an external SHT40 (M5Stack ENV IV) on a cable, away from the screen.
- **Bench hardware isn't bought yet** ([shopping list](tab5-thermostat/docs/shopping-list.md)). Dang will say when it arrives. Until then, use simulation.

## Anti-goals

- The house gets too hot or cold because something crashed or lost the network.
- Hacky wiring, or anything Dang couldn't swap back to the old thermostat in five minutes.
- Personal info in this repo. **It is public**: no addresses, Wi-Fi credentials, keys or passwords. `secrets.yaml` is gitignored.

## Repo layout

```
docker-compose.yml           HA 2026.10.4 + ESPHome 2026.10.1 (host networking); `esphome-host` and `preview` services (dev profile)
tools/preview/               desktop preview rig + console tests (test_all.sh, test_device.sh)
home-assistant/config/       HA config (runtime state gitignored)
tab5-thermostat/             ESPHome config dir (mounted at /config in the esphome container)
  tab5-thermostat.yaml       device entry point: Wi-Fi, API, OTA, web page, packages
  main-thermostat-sim.yaml   host entry point: the thermostat logic + virtual house, for HA (API on 6053)
  thermostat/                milestone 2 logic package: logic.yaml (climate, safety, schedule) + chestnut_logic.h
  sim/                       the virtual house: virtual-house.yaml + house_model.h (contract ids, knobs, faults)
  tests/                     run.sh (unit | build | scenarios | all, Docker only), test entry, unit + scenario tests
  hardware/                  board support; display-*.yaml = one per Tab5 screen revision
  ui/                        the console: fonts, theme, console (layout), console-logic (bindings)
    dev/contract-stub.yaml   DEV ONLY stand-in for milestone 2 (same entity ids, fake values); the preview's fixture
  preview/                   desktop preview entry point (host + SDL); shots/ is gitignored
  secrets.yaml.example       copy to secrets.yaml locally (never commit, never post on beacon)
  docs/                      research.md, shopping-list.md
```

Validate and compile:
```bash
docker compose run --rm --no-deps esphome config tab5-thermostat.yaml
docker compose run --rm --no-deps esphome compile tab5-thermostat.yaml
tab5-thermostat/tests/run.sh all     # milestone 2 tests
```

## Hardware facts that bite

- Three Tab5 screen revisions: original (ILI9881C + GT911 touch), ST7123, ST7121. Pick the matching `hardware/display-*.yaml` from the sticker on the back of the unit. A wrong model gives a blank screen with no error.
- For ST7123/ST7121, **don't set a touch reset pin**: the LCD reset enables touch, and toggling the touch reset line can knock the controller offline.
- Wi-Fi is 2.4 GHz only (ESP32-C6 via `esp32_hosted`).
- CPU at 360 MHz: ESPHome's 400 MHz default for the P4 is flagged as possibly unbootable.
- Port A (HY2.0-4P, I2C on G53/G54) is where the ENV IV and the Unit 4-Relay (I2C 0x26) will go, through a Grove hub.
- RS485 power input accepts 6–24 V DC, never raw rectified 24 VAC.

## Milestones

1. **Bring-up** (PC, needs the Tab5 on USB): hello screen, touch, Wi-Fi, HA connection, web page, identify the screen revision. *Done (merged).*
2. **Thermostat logic, simulated.** ESPHome `thermostat` climate driven by a simulated room (a "virtual house" whose temperature drifts toward outdoor and responds to virtual heat/cool/fan relays), plus all the safety requirements above. Develop it on ESPHome's **`host` platform**, which runs natively on Linux/macOS with no hardware, then run the same packages on the Tab5. *Done (merged 2026-10-29).*
3. **Thermostat UI** in LVGL. Dang's call (2026-10-28): **functional first, polish later**. First a clean, simple screen (big temperature, setpoint, mode, fan, humidity) built on the milestone 2 climate entity, then a proper design pass with mockups. The Tab5 can't show HA's own dashboard (it has no browser); phones and PCs get HA's built-in thermostat card meanwhile. The UI lives in `ui/` packages, separate from the logic, so restyling is cheap.
4. **Bench rig** (when Dang buys the parts): real ENV IV + Unit 4-Relay + 24 VAC lamps, then 24 VAC → DC power.
5. **House:** site survey, then install.

### Package contract (milestones 2–4)

Hardware and simulation packages provide the same ids, so the logic package doesn't care which one is loaded:

| id | type | provided by |
|---|---|---|
| `room_temperature` | sensor (°C) | `sim` package now, SHT40 later |
| `room_humidity` | sensor (%) | `sim` package now, SHT40 later |
| `relay_heat` (W), `relay_cool` (Y), `relay_fan` (G), `relay_ob` (O/B, unused unless heat pump) | switch, `restore_mode: ALWAYS_OFF`, `internal: true`; only the logic package drives them | `sim` template switches now, Unit 4-Relay later |
| `main_thermostat` | climate (thermostat) | logic package |

ESPHome climate works in °C internally. Show °F in the UI and HA (Dang is in the US).

## How we develop (Dang's rules)

- **Use `superpowers:brainstorming` before building any new feature or milestone.** Work out the design with Dang first and write it up in `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`. The other agent reads it as the builder check, and nothing gets built until Dang approves it. Then plan it with `superpowers:writing-plans`. The agent that owns the work leads its brainstorm, so Dang isn't asked the same questions twice.
- **Ask Dang design questions as surveys.** In design stages, use the multiple-choice question tool (AskUserQuestion) with the recommended option first, instead of open-ended text questions. On beacon, where that tool doesn't exist, give a short numbered list of options with your recommendation first.
- **No AI co-author trailers.** Never add `Co-Authored-By: Claude ...` (or any agent attribution) to commit messages.
- **Don't use the `graphify` skill on this project.** No knowledge graphs or `graphify-out/`; the repo is small enough to read directly.

## Working together (PC agent + Mac agent)

Co-workers and co-reviewers, not orchestrator and worker. Neither is in charge; Dang decides.

- **Talk on beacon** in channel **`#chestnut-console`**. Handles: `pc-chestnut-console`, `mac-chestnut-console`. Claim before starting a task (`--tag claim`), post milestones and `done` with commits.
- **Branches:** work on `pc/<topic>` or `mac/<topic>`. Before merging to `main`, post a review request with the branch and commit; the other agent reviews (`git diff main...<branch>`) and replies on beacon. The author merges after approval. Keep `main` compiling.
- **File ownership** to avoid collisions (change it by agreement on beacon):
  - PC: `docker-compose.yml`, `home-assistant/`, `tab5-thermostat/hardware/`, everything in `tab5-thermostat/ui/` (the thermostat screens; Dang moved UI ownership to the PC on 2026-10-28), and flashing. The Tab5 is plugged into the PC.
  - Mac: the thermostat logic and simulation packages and the host-sim entry point.
- **Third opinion:** the Mac agent can consult **astra** through its CLI when a design call is contested or worth a fresh pair of eyes.
- **Destructive or outward-facing actions** (force-push, deleting branches, spending money, changing Dang's network or system settings) go to Dang first.
- Never put secrets on beacon or in the repo.
