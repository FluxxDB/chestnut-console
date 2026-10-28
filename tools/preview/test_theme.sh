#!/usr/bin/env bash
# Task 5 test: dark theme recolors every element (style colors + no light-palette pixels left
# in any scenario), light stays as specified, and the top-bar button toggles the theme.
set -euo pipefail
cd "$(dirname "$0")/../.."
dc="docker compose --profile dev run --rm"
sh="tab5-thermostat/preview/shots"
scen=("Heating" "Cooling" "Eco auto band" "Hold" "Schedule off" "Clock not set" "Waiting" "Off fan on" "Sensor fault" "Interlock fault" "Unknowns")
$dc --entrypoint rm preview -rf /config/preview/shots/theme /config/preview/shots/toggle >/dev/null 2>&1
$dc preview preview/console-preview.yaml /config/preview/shots/theme --themes light,dark --dump "${scen[@]}" >/dev/null
c="python3 tools/preview/check_snapshot.py $sh/theme"
$c heating light c_page=e9ecf0 c_card=ffffff c_emph=1f232d c_hum=dff9ff c_pill=eef0f3 c_pill_sel=dbffe7 c_pill_sel_text=181b22 c_ink=181b22 c_sub=585c64 icon=moon
$c heating dark c_page=181b22 c_card=1f232d c_emph=2b303c c_pill_sel=1e3b33 c_pill_sel_text=dbffe7 c_ink=ffffff c_sub=9a9ca1 icon=sun
for s in "${scen[@]}"; do
  slug=$(echo "$s" | tr 'A-Z' 'a-z' | sed 's/[^a-z0-9]\+/-/g')
  hist=$($dc --entrypoint convert preview "/config/preview/shots/theme/$slug-dark.png" -format %c histogram:info:- 2>/dev/null)
  for light in e9ecf0 dbffe7 dff9ff eef0f3; do
    if echo "$hist" | grep -qi "#$light"; then echo "FAIL: $slug-dark has light color #$light"; exit 1; fi
  done
done
echo "PASS: no light-palette pixels in ${#scen[@]} dark screenshots"
# The top-bar button toggles the theme.
$dc preview preview/console-preview.yaml /config/preview/shots/toggle --dump "Heating" --clicks "1221,51" >/dev/null
python3 tools/preview/check_states.py $sh/toggle heating dark_theme=true
echo "PASS: theme"
