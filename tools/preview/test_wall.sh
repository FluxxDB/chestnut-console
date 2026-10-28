#!/usr/bin/env bash
# Wall readability (Dang, on the Tab5): text is anti-aliased (4-bit glyphs) and larger,
# and the bigger text still fits: no top-bar overlap, the subline clear of the big number,
# the long fault banner inside its box, all pills inside the strip.
set -euo pipefail
cd "$(dirname "$0")/../.."
dc="docker compose --profile dev run --rm"
sh="tab5-thermostat/preview/shots"
$dc --entrypoint rm preview -rf /config/preview/shots/wall >/dev/null 2>&1
$dc preview preview/console-preview.yaml /config/preview/shots/wall "Heating" "Hold" "Waiting" "Interlock fault" >/dev/null
c="python3 tools/preview/check_snapshot.py $sh/wall"
# Grey text (schedule line, history labels): 4-bit glyphs, line height >= 32 px (was 26 at 1-bit).
$c heating light f_sched_bpp=4 f_hist_bpp=4 f_status_bpp=4 f_title_bpp=4 "f_sched_h=~^(3[2-9]|4[0-9])$" "f_hist_h=~^(3[2-9]|4[0-9])$" "f_status_h=~^(3[6-9]|4[0-9])$" "strip_slack=~^[1-9][0-9]*$"
$c hold light "topbar_gap=~^[1-9][0-9]*$" resume_visible=1
$c waiting light sub_room_overlap=0
$c interlock-fault light banner_visible=1 banner_fits=1
echo "PASS: wall readability"
