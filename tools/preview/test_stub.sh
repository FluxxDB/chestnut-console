#!/usr/bin/env bash
# Task 2 test: the contract stand-in's Scenario select drives the milestone 2 ids.
set -euo pipefail
cd "$(dirname "$0")/../.."
dc="docker compose --profile dev run --rm"
$dc --entrypoint rm preview -rf /config/preview/shots/stub >/dev/null 2>&1
$dc preview preview/console-preview.yaml /config/preview/shots/stub "Heating" "Sensor fault" "Eco auto band" --dump >/dev/null
out=tab5-thermostat/preview/shots/stub
c="python3 tools/preview/check_states.py $out"
$c heating checked_temperature=71 call_heat=true call_cool=false main_thermostat.mode=HEAT main_thermostat.action=HEATING schedule_status="Comfort until 10:30 pm" effective_target=72
$c sensor-fault sensor_fault=true checked_temperature=nan
$c eco-auto-band comfort_level=Eco main_thermostat.mode=HEAT_COOL effective_low=68 effective_high=76 call_heat=false
# A mode change moves the stand-in's action at once (Dang: "Heating" stayed after tapping Cool).
# Heating at 71 toward 72: Cool -> idle with the heat call off; back to Heat -> heating again.
$dc preview preview/console-preview.yaml /config/preview/shots/stub/to-cool --dump "Heating" --clicks "410,649" >/dev/null
python3 tools/preview/check_states.py $out/to-cool heating main_thermostat.mode=COOL main_thermostat.action=IDLE call_heat=false call_cool=false
python3 tools/preview/check_snapshot.py $out/to-cool heating light status=Idle
$dc preview preview/console-preview.yaml /config/preview/shots/stub/to-heat --dump "Heating" --clicks "410,649;293,649" >/dev/null
python3 tools/preview/check_states.py $out/to-heat heating main_thermostat.mode=HEAT main_thermostat.action=HEATING call_heat=true
echo "PASS: stub scenarios"
