#!/usr/bin/env bash
# Task 3 test: the static console layout renders with every element, and the Tab5 build compiles.
set -euo pipefail
cd "$(dirname "$0")/../.."
dc="docker compose --profile dev run --rm"
$dc --entrypoint rm preview -rf /config/preview/shots/layout >/dev/null 2>&1
$dc preview preview/console-preview.yaml /config/preview/shots/layout "Heating" >/dev/null
c="python3 tools/preview/check_snapshot.py tab5-thermostat/preview/shots/layout"
$c heating light title="Main Thermostat" inside="Inside now" hist_mid="Dashed line: target" \
  mode_pills="Off|Heat|Cool|Auto" fan_pills="Auto|On" lvl_pills="Comfort|Eco" hum_cap="Comfortable"
docker compose run --rm --no-deps esphome compile tab5-thermostat.yaml > tab5-thermostat/preview/shots/layout/device-compile.log 2>&1 \
  || { tail -30 tab5-thermostat/preview/shots/layout/device-compile.log; echo "FAIL: device compile"; exit 1; }
grep -E "Flash:" tab5-thermostat/preview/shots/layout/device-compile.log | tail -1
echo "PASS: layout"
