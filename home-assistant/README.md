# Home Assistant

Runs from the repo root's `docker-compose.yml`, with `config/` mounted at `/config`.

- Only hand-written YAML is committed. Users, integrations, devices and history live in `config/.storage` and the database, which are gitignored.
- **First run on a new machine:** open http://localhost:8123 and go through onboarding. Set the location to the house so time zone and weather are right.
- **Add the Tab5:** Settings → Devices & services → Add integration → ESPHome. See [tab5-thermostat/README.md](../tab5-thermostat/README.md#connecting-to-home-assistant).
- **On WSL (dev PC):** HA runs inside WSL's NAT network. Device discovery (mDNS) doesn't reach the LAN, so add ESPHome devices by IP. Other devices on the LAN can't reach HA unless you go through Tailscale.
