# Home Assistant

## Start it

From the repo root:

```bash
docker compose up -d homeassistant
```

Then open http://localhost:8123. HA keeps running in the background and starts again with Docker; `docker compose stop homeassistant` stops it. The first time on a machine:

1. Go through onboarding. Set the location to the house so the time zone and weather are right.
2. Open **Settings → Dashboards → Chestnut** and choose **Set as default**. You only need to do this once per HA install (see [Applying it to a running HA](#applying-it-to-a-running-ha)).
3. Add the thermostat: Settings → Devices & services → Add integration → ESPHome, with the Tab5's IP ([details](../tab5-thermostat/README.md#connecting-to-home-assistant)), or the host sim on port 6053.

After pulling new changes, run `docker compose restart homeassistant`, then reload the dashboard's code in each browser and phone ([how](#applying-it-to-a-running-ha)).

## Notes

- `config/` is mounted at `/config`. Only hand-written YAML is committed. Users, integrations, devices and history live in `config/.storage` and the database, which are gitignored.
- **On WSL (dev PC):** HA runs inside WSL's NAT network. Device discovery (mDNS) doesn't reach the LAN, so add ESPHome devices by IP. Other devices on the LAN can't reach HA unless you go through Tailscale.

## The Chestnut dashboard

A custom dashboard that **replaces HA's Overview**, so opening HA (app or browser) lands on it. It is one panel that draws the whole page, with four tabs:

- **Home:** the room view (desktop only), current temperature, target, mode, fan and the schedule line.
- **Schedule:** the weekly schedule.
- **Simulation:** the virtual house controls (outdoor temperature, weather, faults, insulation). It exists only while the virtual house exists. Once the real sensors and relays replace it (milestone 4), the tab disappears and the room view stays as the live view of the house.
- **System:** safety timers and interlock, the alert switches, device info.

On a phone the room view and the Simulation tab are hidden. The theme is `axiom` (`config/themes/axiom.yaml`).

Layout: `config/dashboards/chestnut.yaml` (the dashboard), `config/www/chestnut/` (the custom element, one JS file per tab, self-hosted fonts), `config/themes/axiom.yaml`, `config/configuration.yaml` (dashboard registration and the alert helpers), `config/automations.yaml` (theme and alerts).

### Applying it to a running HA

On the dev PC now, and on the house VM later:

```bash
git pull
docker compose restart homeassistant
```

Then one manual step, which HA 2026.10 requires because the system default panel lives in `.storage`, not YAML: open **Settings → Dashboards → Chestnut** and choose **Set as default**. Do it once per HA install. The `axiom` theme is applied automatically at startup (an automation sets it for every user), so there is nothing to do for it.

**After an update, reload the dashboard's code.** HA serves `config/www` with a 31-day browser cache, so a browser or phone that has opened the dashboard keeps the old JavaScript (or a mix of old and new files). In a browser, hard-reload the page (Ctrl+Shift+R). In the Companion app: **Settings → Companion app → Debugging → Reset frontend cache**. (A version query on the URLs wouldn't help: the dashboard's own modules import each other by plain relative paths, which a query on the first file doesn't reach.)

### Alerts

Three switches on the System tab (`input_boolean.chestnut_alert_sensor_fault`, `..._interlock_fault`, `..._offline`) decide which alerts are sent. They start on (an automation turns them on at the first HA start and records that in `input_boolean.chestnut_alert_switches_set_up`). After that HA restores them, so a switch you turn off stays off across restarts. Turning a switch on while its fault is already active doesn't alert; the next fault, or the next HA start with the fault still on, does.

| Alert | Fires when |
|---|---|
| Sensor fault | the thermostat reports a temperature sensor problem (bad or missing reading). It has stopped calling for heat/cool. |
| Interlock fault | the heat/cool interlock tripped: the heat and cool relays were found on at the same time (a stuck relay or wiring fault), so both were cut. Clear it on the System tab once it's checked. The clear takes effect once both units have been off for their minimum off time since the trip (the longer of the two, 5 min by default; or the device reboots). An early press is remembered, so press once and wait; the System tab says the clear was requested. |
| Offline | HA has had no contact with the thermostat for 10 minutes. It keeps running on its own. |

Each alert also sends a "cleared" notice when the problem goes away, but only if that alert actually fired. A new alert takes down the last "cleared" notice of its kind. A fault that is first seen as the thermostat reconnects (it was unavailable, then reports the fault) still alerts; a fault that was already alerted and is still there after a reconnect doesn't alert again. A fault that is on, or a thermostat that is still offline, when HA starts alerts again (HA's notifications don't survive a restart); for offline that is 10 minutes after HA starts. An alert's notification is always removed when the problem clears, even if its switch was turned off meanwhile.

What each alert remembers between its alert and its "cleared" notice lives in three more helpers, `input_boolean.chestnut_sensor_fault_alerted`, `..._interlock_fault_alerted` and `input_boolean.chestnut_offline_alerted` (off at every HA start). They are internal: don't toggle them by hand. Because they reset at a start, a problem that clears while HA is restarting gets no "cleared" notice (the alert from before the restart stays on the phone), and a thermostat that stays offline alerts again 10 minutes after every HA start.

**The entity ids.** `config/automations.yaml` names the ids HA makes for a device called "Main Thermostat":

- `binary_sensor.main_thermostat_sensor_fault`
- `binary_sensor.main_thermostat_interlock_fault`
- `climate.main_thermostat_main_thermostat`

The dev HA has exactly these (checked 2026-10-29), and the e2e tests run the file as written. On a new install, HA can name them differently (ids left from an earlier device name, or a renamed device). So the "Chestnut: alert entity check" automation looks for them 30 s after every HA start, and if one is missing it posts a notification naming it. Then edit `automations.yaml` to match (Developer Tools → States, search for `main_thermostat`); otherwise that alert never fires.

Phone push needs the HA Companion app signed in to this HA (it provides `notify.notify`). It goes to **every** phone signed in to this HA with the app, not only Dang's. Until a phone is set up, alerts show as persistent notifications in HA (the bell in the sidebar).

### Running the tests

```bash
home-assistant/tests/run.sh unit   # JS unit tests, fast
home-assistant/tests/run.sh e2e    # browser tests against a throwaway HA + the host sim
home-assistant/tests/run.sh all    # both, about 7 minutes
```

Docker on Linux (WSL) only: run.sh uses `ss`, GNU `sed` and `stat`, `flock` and host networking, so it doesn't run on macOS. The unit tests alone run anywhere with Node 24 (`node --test 'home-assistant/tests/unit/*.test.mjs'`). The e2e HA runs on port **8124** with its own temporary config (the offline alert's 10 minutes shortened to 30 s; everything else as written, with the sim named "Main Thermostat" like the Tab5) and a fresh admin password each run, and never touches the dev HA on 8123; ports **8124** and **6053** (the sim's API) must be free, so stop any other host sim first. One run at a time.

### Fonts

The dashboard uses JetBrains Mono (SIL Open Font License, `config/www/chestnut/fonts/OFL.txt`), self-hosted as woff2 in `config/www/chestnut/fonts/`. Nothing loads from a CDN, so it works with no internet.
