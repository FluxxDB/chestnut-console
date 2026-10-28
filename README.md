# Chestnut Console

Home Assistant setup and a DIY smart thermostat built on an **M5Stack Tab5**, running ESPHome.

- [`home-assistant/`](home-assistant/): Home Assistant config, run with Docker Compose.
- [`tab5-thermostat/`](tab5-thermostat/): ESPHome firmware for the Tab5 thermostat, plus [research notes](tab5-thermostat/docs/research.md) and the [shopping list](tab5-thermostat/docs/shopping-list.md).
- [`AGENTS.md`](AGENTS.md): full project context and decisions.

## Quick start

```bash
git clone git@github.com:FluxxDB/chestnut-console.git
cd chestnut-console
cp tab5-thermostat/secrets.yaml.example tab5-thermostat/secrets.yaml   # then fill it in
docker compose up -d
```

- Home Assistant: http://localhost:8123
- ESPHome Device Builder: http://localhost:6052

The same steps run on the Ubuntu server VM at the house. Home Assistant's users, integrations and history are not in git, so a fresh machine starts with HA's onboarding.

## Status

Milestone 1 (Tab5 bring-up) is in progress. See [AGENTS.md](AGENTS.md#milestones).
