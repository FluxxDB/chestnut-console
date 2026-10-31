# Chestnut Console

Home Assistant setup and a DIY smart thermostat built on an **M5Stack Tab5**, running ESPHome.

- [`home-assistant/`](home-assistant/): Home Assistant and the Chestnut dashboard.
- [`tab5-thermostat/`](tab5-thermostat/): ESPHome firmware for the Tab5 thermostat, plus [research notes](tab5-thermostat/docs/research.md) and the [shopping list](tab5-thermostat/docs/shopping-list.md).
- [`AGENTS.md`](AGENTS.md): full project context and decisions.

## Start here

Each part starts with one `docker compose` command, run from the repo root. You need only git and Docker, on Linux or WSL. Go in this order; each step links the README to read the first time.

**0. Get the code**

```bash
git clone git@github.com:FluxxDB/chestnut-console.git && cd chestnut-console
```

**1. Set up Home Assistant** ([home-assistant/README.md](home-assistant/README.md#start-it))

```bash
docker compose up -d homeassistant
```

Open http://localhost:8123. It keeps running in the background. The first time on a machine, go through HA's onboarding, then set the Chestnut dashboard as the default (Settings → Dashboards → Chestnut → Set as default).

**2. Then set up the Tab5** ([tab5-thermostat/README.md](tab5-thermostat/README.md#start-it))

```bash
docker compose run --rm esphome run tab5-thermostat.yaml --device <tab5-ip>
```

This builds the firmware and installs it over Wi-Fi. The Tab5 shows its IP on screen. The first time, read the README before you run it: you pick the screen revision, fill in `tab5-thermostat/secrets.yaml`, and do the first flash over USB. Then add the Tab5 to HA (Settings → Devices & services → Add integration → ESPHome).

**2b. No Tab5? Run the host sim instead** ([tab5-thermostat/README.md](tab5-thermostat/README.md#host-sim-for-home-assistant))

```bash
docker compose run --rm esphome-host run main-thermostat-sim.yaml
```

It runs the same thermostat logic and virtual house on your computer, as a device HA adds the same way (port 6053). It stays in the foreground until Ctrl-C, and needs `sim_api_encryption_key` in `secrets.yaml`.

The same steps work on the Ubuntu server VM at the house. HA's users, integrations and history aren't in git, so a fresh machine always starts with onboarding.

### Tests

```bash
home-assistant/tests/run.sh all     # the dashboard: unit + browser tests, about 7 minutes
tab5-thermostat/tests/run.sh all    # the thermostat logic: unit + scenario tests, about 10 minutes
tools/preview/test_all.sh           # the wall screen, in the desktop preview (needs secrets.yaml)
```

The test runners are scripts rather than compose services because each one starts its own throwaway containers. They still need nothing but Docker.

## Status

Milestones 1–3 are done: bring-up, the thermostat logic with its safety features, and the wall screen. The Home Assistant dashboard is done too. The Tab5 runs the real thermostat logic against a simulated house. Next is milestone 4, a bench rig with a real sensor and relays, once the parts are bought (not soon). After that comes milestone 5, the house itself. Its site survey has started: the middle-floor thermostat's wiring is confirmed ([site-survey.md](tab5-thermostat/docs/site-survey.md)). See [AGENTS.md](AGENTS.md#milestones).
