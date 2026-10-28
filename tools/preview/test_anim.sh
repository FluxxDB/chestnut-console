#!/usr/bin/env bash
# Motion (Dang, after trying fades on the wall: "remove the animation for the screen dimming and
# turning off. Make the buttons more responsive and snappier"). Dim, sleep and wake switch at once;
# a button presses in the moment it's touched and eases back briefly; a tap's result (a pill lit,
# the − / + number) shows right after it, not on the next 250 ms refresh.
# Preview timeouts: dim at 3 s, sleep at 6 s. The snapshot is sampled every 200 ms.
set -euo pipefail
cd "$(dirname "$0")/../.."
dc="docker compose --profile dev run --rm"
sh="tab5-thermostat/preview/shots"
fail=0
# seen <shot dir> <condition>: w maps each watched snapshot field to the values it took, in order.
seen() {
  python3 - "$sh/$1/heating-light-states.json" "$2" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
w = {k.split(".", 1)[1]: [int(x) for x in v] for k, v in d.items() if k.startswith("_watch.")}
ok = bool(eval(sys.argv[2], {"w": w}))
print(("  ok    " if ok else "  FAIL  ") + sys.argv[2] + "\n        seen " + json.dumps(w))
sys.exit(0 if ok else 1)
PY
}
$dc --entrypoint rm preview -rf /config/preview/shots/anim-dim /config/preview/shots/anim-sleep /config/preview/shots/anim-wake /config/preview/shots/anim-taps >/dev/null 2>&1
# Dim (from ~2 s to ~5.5 s after boot): the backlight goes straight from 10% to 4%, and the scrim
# is 70% black (178 of 255) from the moment it shows.
$dc preview preview/console-preview.yaml /config/preview/shots/anim-dim --dump "Heating" --watch scrim_opa,bl_now,wake_visible --watch-for 3.5 >/dev/null
seen anim-dim "w['bl_now'] == [10, 4] and w['wake_visible'] == [0, 1] and set(w['scrim_opa']) == {178}" || fail=1
# Sleep (from ~4.5 s to ~9 s): straight from dim to off.
$dc preview preview/console-preview.yaml /config/preview/shots/anim-sleep --dump "Heating" --pre-wait 3 --watch scrim_opa,bl_now --watch-for 4.5 >/dev/null
seen anim-sleep "w['bl_now'] == [4, 0] and set(w['scrim_opa']) == {178}" || fail=1
# Wake tap while dimmed: straight back to 10%.
$dc preview preview/console-preview.yaml /config/preview/shots/anim-wake --dump "Heating" --watch bl_now --watch-for 0.1 --pre-wait 4 --clicks "1183,251" >/dev/null
seen anim-wake "w['bl_now'] == [10, 4, 10]" || fail=1
# Buttons and pills press in by 3 px at once (no transition into pressed; LVGL's theme would take
# 80 ms) and ease back over 80 ms. Pill colors switch at once.
python3 tools/preview/check_snapshot.py $sh/anim-wake heating light btn_press=-3 pill_press=-3 \
  btn_press_trans=0 pill_press_trans=0 "btn_release_trans=80 press" "pill_release_trans=80 press" || fail=1
# Taps on Cool, Heat, Eco, Comfort and +: each result shows within 50 ms of the tap.
$dc preview preview/console-preview.yaml /config/preview/shots/anim-taps --dump "Heating" \
  --clicks "410,649;293,649;1177,649;1043,649;1183,251" --click-gap 0.6 >/dev/null
python3 tools/preview/check_snapshot.py $sh/anim-taps heating light tap_count=5 "tap_latency_max_ms=~^[0-4]?[0-9]$" || fail=1
[ $fail = 0 ] || { echo "FAIL: animations"; exit 1; }
echo "PASS: animations"
