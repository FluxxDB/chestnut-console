#!/usr/bin/env bash
# Task 6 test: idle dims the backlight; the first tap on a dimmed screen only wakes it.
# The preview's idle timeout is 3 s (the Tab5 uses 30 s).
set -euo pipefail
cd "$(dirname "$0")/../.."
dc="docker compose --profile dev run --rm"
sh="tab5-thermostat/preview/shots"
$dc --entrypoint rm preview -rf /config/preview/shots/idle-dim /config/preview/shots/idle-wake /config/preview/shots/idle-second >/dev/null 2>&1
# Left alone: dims to 10%.
$dc preview preview/console-preview.yaml /config/preview/shots/idle-dim --dump "Heating" --pre-wait 4 >/dev/null
python3 tools/preview/check_states.py $sh/idle-dim heating display_backlight.brightness=0.1
# One tap on + while dimmed: wakes to 100%, does not change the target.
$dc preview preview/console-preview.yaml /config/preview/shots/idle-wake --dump "Heating" --pre-wait 4 --clicks "1183,251" >/dev/null
python3 tools/preview/check_states.py $sh/idle-wake heating display_backlight.brightness=1 set_target=72 _writes.set_target=0
python3 tools/preview/check_snapshot.py $sh/idle-wake heating light target=72°
# Wake tap, then a real tap: the second one counts.
$dc preview preview/console-preview.yaml /config/preview/shots/idle-second --dump "Heating" --pre-wait 4 --clicks "1183,251;1183,251" --click-gap 0.6 >/dev/null
python3 tools/preview/check_states.py $sh/idle-second heating set_target=73
echo "PASS: idle"
