#!/usr/bin/env bash
# Idle stages (Dang): in use 10%; after idle_timeout dim to ~a tenth of that; after sleep_timeout the
# backlight is off and LVGL paused (the thermostat keeps running). The first tap on a dimmed
# or sleeping screen only wakes it, back to 10%. Preview timeouts: 3 s / 6 s (Tab5: 30 s / 60 s).
set -euo pipefail
cd "$(dirname "$0")/../.."
dc="docker compose --profile dev run --rm"
sh="tab5-thermostat/preview/shots"
$dc --entrypoint rm preview -rf /config/preview/shots/idle-dim /config/preview/shots/idle-wake /config/preview/shots/idle-second /config/preview/shots/idle-sleep /config/preview/shots/sleep-wake >/dev/null 2>&1
# Left alone 4 s: dims. Levels are adjustable entities: in use 10, dim 4 (light brightness, which
# ESPHome gamma-corrects by 2.8: 4% is about a tenth of the in-use light output; a literal 1% is dark).
$dc preview preview/console-preview.yaml /config/preview/shots/idle-dim --dump "Heating" --pre-wait 4 >/dev/null
python3 tools/preview/check_states.py $sh/idle-dim heating display_backlight=true display_backlight.brightness=0.04 screen_brightness=10 dim_brightness=4
# The Tab5's backlight bottoms out above the in-use level, so the dim stage also darkens the
# picture: the wake catcher becomes a 70% black scrim (bg_opa 178 of 255).
python3 tools/preview/check_snapshot.py $sh/idle-dim heating light wake_visible=1 scrim_opa=178
# Left alone 7 s: backlight off and LVGL paused.
$dc preview preview/console-preview.yaml /config/preview/shots/idle-sleep --dump "Heating" --pre-wait 7 >/dev/null
python3 tools/preview/check_states.py $sh/idle-sleep heating display_backlight=false
python3 tools/preview/check_snapshot.py $sh/idle-sleep heating light paused=1
# One tap on + while dimmed: wakes to 10%, does not change the target.
$dc preview preview/console-preview.yaml /config/preview/shots/idle-wake --dump "Heating" --pre-wait 4 --clicks "1183,251" >/dev/null
python3 tools/preview/check_states.py $sh/idle-wake heating display_backlight.brightness=0.1 set_target=72 _writes.set_target=0
# One tap on + while asleep: wakes to 10% and resumes, does not change the target.
$dc preview preview/console-preview.yaml /config/preview/shots/sleep-wake --dump "Heating" --pre-wait 7 --clicks "1183,251" >/dev/null
python3 tools/preview/check_states.py $sh/sleep-wake heating display_backlight=true display_backlight.brightness=0.1 set_target=72 _writes.set_target=0
python3 tools/preview/check_snapshot.py $sh/sleep-wake heating light paused=0
python3 tools/preview/check_snapshot.py $sh/idle-wake heating light target=72°
# Wake tap, then a real tap: the second one counts.
$dc preview preview/console-preview.yaml /config/preview/shots/idle-second --dump "Heating" --pre-wait 4 --clicks "1183,251;1183,251" --click-gap 0.6 >/dev/null
python3 tools/preview/check_states.py $sh/idle-second heating set_target=73
echo "PASS: idle"
