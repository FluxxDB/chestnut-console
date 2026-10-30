# Tab5 thermostat firmware

ESPHome config for the Main Thermostat. This folder is mounted as `/config` in the ESPHome containers.

## Start it

From the repo root, with the Tab5 on Wi-Fi:

```bash
docker compose run --rm esphome run tab5-thermostat.yaml --device <tab5-ip>
```

This builds the firmware, installs it over Wi-Fi, then shows the Tab5's log until you press Ctrl-C. The Tab5 shows its IP on screen. The first time, do the [first-time setup](#first-time-setup) and the [first flash over USB](#flashing) instead. After that, this one command is all an update needs. Then [add the Tab5 to Home Assistant](#connecting-to-home-assistant).

**No Tab5?** The [host sim](#host-sim-for-home-assistant) runs the same logic and virtual house on your computer:

```bash
docker compose run --rm esphome-host run main-thermostat-sim.yaml
```

**Optional:** ESPHome's own web UI, the Device Builder, runs at http://localhost:6052 after `docker compose up -d esphome`. Nothing needs it; the commands above do everything.

## First-time setup

1. **Find your screen revision.** The sticker on the back of the Tab5, just above the Espressif logo, names the display driver chip. In [`tab5-thermostat.yaml`](tab5-thermostat.yaml), leave exactly one `display:` line active:
   - ILI9881C → `hardware/display-ili9881c.yaml` (original, made before Oct 2025)
   - ST7123 → `hardware/display-st7123.yaml`
   - ST7121 → `hardware/display-st7121.yaml` (also try this one if ST7123 leaves the screen blank while touch works)
2. **Secrets.** `cp secrets.yaml.example secrets.yaml` and fill it in. The Tab5 only joins **2.4 GHz** Wi-Fi.
3. **Compile** (from the repo root):
   ```bash
   docker compose run --rm esphome compile tab5-thermostat.yaml
   ```
   The first build downloads the ESP-IDF toolchain and takes a while. Later builds are quick.

## Flashing

**First flash over USB-C.** The factory image is `.esphome/build/tab5-thermostat/build/firmware.factory.bin`. Any of these work:

- **Linux with the Tab5 attached:** `docker compose run --rm --device /dev/ttyACM0 esphome run tab5-thermostat.yaml --device /dev/ttyACM0`
- **WSL (what the PC uses, no admin needed):** run the official Windows build of esptool ([releases](https://github.com/espressif/esptool/releases), `esptool-vX-windows-amd64.zip`) against the Tab5's COM port (it shows up as `303a:1001 USB JTAG/serial debug unit`):
  ```bash
  cp tab5-thermostat/.esphome/build/tab5-thermostat/build/firmware.factory.bin /mnt/c/Users/<you>/AppData/Local/Temp/
  esptool.exe --chip esp32p4 --port COM6 --baud 921600 write-flash 0x0 C:\\Users\\<you>\\AppData\\Local\\Temp\\firmware.factory.bin
  ```
  `esptool.exe --port COM6 chip-id` reads the chip revision. Or attach the Tab5 to WSL with usbipd-win (`usbipd bind` once as admin, then `usbipd attach --wsl --busid <id>`) and do the Linux step.
- **Browser:** https://web.esphome.io in Chrome or Edge → Connect → Install → choose the factory `.bin`.

**After that, updates go over Wi-Fi:**
```bash
docker compose run --rm esphome run tab5-thermostat.yaml --device <tab5-ip>
```
The Tab5 shows its IP address on screen. mDNS (`tab5-thermostat.local`) won't resolve from inside WSL's NAT, so use the IP.

**Logs over Wi-Fi:**
```bash
docker compose run --rm esphome logs tab5-thermostat.yaml --device <tab5-ip>
```
The I2C scan in the boot log tells you the revision: touch at `0x14` is the original, `0x55` is ST7123/ST7121.

## Connecting to Home Assistant

In HA: Settings → Devices & services → Add integration → ESPHome → host = the Tab5's IP, with the `api_encryption_key` from `secrets.yaml`. Then, in the device's options, enable **"Allow the device to perform Home Assistant actions"** (needed later for controlling the top floor from the Tab5).

## Phone page

Browse to `http://<tab5-ip>/` and log in with `web_username` / `web_password` from `secrets.yaml`. It only works on the home network; never port-forward it to the internet.

## The console screen

The screen is the Main Thermostat console from `docs/superpowers/specs/2026-10-28-main-thermostat-console-ui-design.md`, split into packages under `ui/`:

| File | What it is |
|---|---|
| `ui/fonts.yaml` | Inter + Space Grotesk (Google Fonts) and the Material Design Icons used on screen |
| `ui/theme.yaml` | color styles, the light/dark switch (also flips at sunset/sunrise), and the house location from `secrets.yaml` |
| `ui/console.yaml` | the layout: one LVGL page, 1280×720 |
| `ui/console-logic.yaml` | the bindings: what each element reads and writes, the − / + debounce, idle dimming |
| `ui/dev/contract-stub.yaml` | **dev only:** a stand-in for the milestone 2 thermostat logic, with the same entity ids and fake values (it switches nothing). The Tab5 now runs the real logic; the stub stays as the desktop preview's fixture. |

Add `house_latitude` / `house_longitude` (city-level) to `secrets.yaml` for the sunset/sunrise theme switch.

## Thermostat logic (milestone 2)

The Tab5 runs the thermostat itself (ESPHome `thermostat` climate `main_thermostat`, with the safety timers, sensor checks, heat/cool interlock, Comfort/Eco and the weekly schedule), so heating and cooling keep working when HA or Wi-Fi is down.

| File | What it is |
|---|---|
| `thermostat/logic.yaml` + `chestnut_logic.h` | the logic package: the only thing that switches a relay |
| `sim/virtual-house.yaml` + `house_model.h` | the virtual house: stands in for the ENV III sensor and the Unit 4-Relay until the bench parts arrive (milestone 4). Its room warms or cools toward outdoor and responds to the virtual relays. |
| `main-thermostat-sim.yaml` | the same two packages on ESPHome's host platform, for Home Assistant and the tests |
| `tests/` | `run.sh` plus the unit and scenario tests |

**Playing with the virtual house:** use the Simulation tab of the Chestnut dashboard in HA (on a computer), or the Tab5's own web page (see *Phone page*). Next to the thermostat it lists the sim's knobs: **Sim Outdoor F**, **Sim Weather** (Fixed, or a Winter / Summer day curve), **Sim Tau H** (how leaky the house is), **Sim Heat FPH** / **Sim Cool FPH** (how fast the equipment changes the room), **Sim Humidity**, and **Sim Room F** (the true room temperature). **Sim Fault** breaks the temperature sensor on purpose (Unplugged, Frozen, Out of range, Spike) so you can watch the sensor checks react: a lasting fault raises **Sensor Fault** and the thermostat stops calling (Unplugged also makes the humidity unknown after two minutes). A fault never survives a reboot. The relays are internal: nothing but the logic can switch them.

### Tests

Docker only, nothing to install, and no secrets needed (run from the repo root):
```bash
tab5-thermostat/tests/run.sh unit         # the C++ unit tests: seconds
tab5-thermostat/tests/run.sh all          # unit tests, then the scenario tests on a host build: about 10 minutes
tab5-thermostat/tests/run.sh scenarios -k fault                              # a subset
tab5-thermostat/tests/run.sh scenarios tests/scenarios/test_core.py         # one file
```
The first run also builds the test image and compiles the host build, which takes a few minutes more. Each scenario test starts its own device program; durations (minimum run and off times, the changeover lockout, the interlock wait) are measured on the device, from test-only timestamps in `tests/main-thermostat-test.yaml`.

### Host sim for Home Assistant

The host sim runs the same logic and virtual house as a separate device, **Main Thermostat (Sim)**, with real timers and real-time physics. It's for HA (the tests build their own entry, `tests/main-thermostat-test.yaml`). It has no web page (ESPHome's host platform has none), so play with the knobs on the Tab5's page, or from HA.

Add `sim_api_encryption_key` to `secrets.yaml` (a different key from the Tab5's; see `secrets.yaml.example` for how to generate one). Then, from the repo root:
```bash
docker compose run --rm esphome-host run main-thermostat-sim.yaml
```
`run` builds the sim first if needed, then stays in the foreground, showing the sim's log, until you press Ctrl-C.
It uses host networking, with the API on port 6053 (Linux; Docker Desktop on a Mac doesn't expose host-network ports to the Mac). The `esphome-host` service builds without ESPHome's precompiled header, which breaks host builds in 2026.10.1.

To add it to HA: Settings → Devices & services → Add integration → ESPHome → host = the machine running the sim, port 6053, with the `sim_api_encryption_key`.

## Desktop preview

Runs the console on your computer (ESPHome's host platform in an SDL window under Xvfb) and saves screenshots, with no Tab5 needed. It uses the dev stand-in, whose `Scenario` select drives every state.

```bash
docker compose build preview
docker compose run --rm preview preview/console-preview.yaml /config/preview/shots/mine "Heating" "Eco auto band" --themes light,dark
```

Screenshots land in `tab5-thermostat/preview/shots/mine/` (gitignored).

**Tests:**
- `tools/preview/test_all.sh` runs every preview test: layout, all 11 scenarios in both themes, the − / + debounce, the theme toggle, and idle/wake.
- `TAB5_IP=<tab5-ip> tools/preview/test_device.sh` flashes the real Tab5 and checks its logs.
- Both need `secrets.yaml`, because they build the Tab5 firmware.
