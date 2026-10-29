# Home Assistant

Runs from the repo root's `docker-compose.yml`, with `config/` mounted at `/config`.

- Only hand-written YAML is committed. Users, integrations, devices and history live in `config/.storage` and the database, which are gitignored.
- **First run on a new machine:** open http://localhost:8123 and go through onboarding. Set the location to the house so time zone and weather are right.
- **Add the Tab5:** Settings → Devices & services → Add integration → ESPHome. See [tab5-thermostat/README.md](../tab5-thermostat/README.md#connecting-to-home-assistant).
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

### Alerts

Three switches on the System tab (`input_boolean.chestnut_alert_sensor_fault`, `..._interlock_fault`, `..._offline`) decide which alerts are sent. All default to on.

| Alert | Fires when |
|---|---|
| Sensor fault | the thermostat reports a temperature sensor problem (bad or missing reading). It has stopped calling for heat/cool. |
| Interlock fault | the heat/cool interlock tripped: the heat and cool relays were found on at the same time (a stuck relay or wiring fault), so both were cut. Clear it on the System tab once it's checked; it won't clear until the minimum off time has passed (or the device reboots). |
| Offline | HA has had no contact with the thermostat for 10 minutes. It keeps running on its own. |

Each alert also sends a "cleared" notice when the problem goes away, but only if that alert actually fired. A fault that is first seen as the thermostat reconnects (it was unavailable, then reports the fault) still alerts; a fault that was already alerted and is still there after a reconnect doesn't alert again. A fault that is on, or a thermostat that is still offline, when HA starts alerts again (HA's notifications don't survive a restart); for offline that is 10 minutes after HA starts. An alert's notification is always removed when the problem clears, even if its switch was turned off meanwhile.

What each alert remembers between its alert and its "cleared" notice lives in three more helpers, `input_boolean.chestnut_sensor_fault_alerted`, `..._interlock_fault_alerted` and `input_boolean.chestnut_offline_alerted` (off at every HA start). They are internal: don't toggle them by hand.

**Check the entity ids once on the real install.** `config/automations.yaml` hard-codes the real Tab5's ids:

- `binary_sensor.main_thermostat_sensor_fault`
- `binary_sensor.main_thermostat_interlock_fault`
- `climate.main_thermostat_main_thermostat`

Open Developer Tools → States and search for `main_thermostat`. If the ids differ (HA keeps old ids from earlier setups), edit `automations.yaml` to match, or the alerts will never fire.

Phone push needs the HA Companion app signed in to this HA (it provides `notify.notify`). Until then, alerts show as persistent notifications in HA (the bell in the sidebar).

### Running the tests

```bash
home-assistant/tests/run.sh unit   # JS unit tests, fast
home-assistant/tests/run.sh e2e    # browser tests against a throwaway HA + the host sim
home-assistant/tests/run.sh all    # both, about 7 minutes
```

Docker only. The e2e HA runs on port **8124** with its own temporary config (the alerts pointed at the sim, the offline alert's 10 minutes shortened to 30 s) and never touches the dev HA on 8123; ports **8124** and **6053** (the sim's API) must be free, so stop any other host sim first.

### Fonts

The dashboard uses JetBrains Mono (SIL Open Font License, `config/www/chestnut/fonts/OFL.txt`), self-hosted as woff2 in `config/www/chestnut/fonts/`. Nothing loads from a CDN, so it works with no internet.
