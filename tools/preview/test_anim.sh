#!/usr/bin/env bash
# Polish animations (Dang): the dim fades in instead of snapping (scrim and backlight), sleep
# fades to black before the backlight goes off, a wake tap fades the backlight back up, and
# buttons shrink a little while pressed and ease between pill colors.
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
$dc --entrypoint rm preview -rf /config/preview/shots/anim-dim /config/preview/shots/anim-sleep /config/preview/shots/anim-wake >/dev/null 2>&1
# Dim (from ~2 s to ~5.5 s after boot): the 70% scrim (178 of 255) and the backlight (10% -> 4%)
# both pass through in-between values.
$dc preview preview/console-preview.yaml /config/preview/shots/anim-dim --dump "Heating" --watch scrim_opa,bl_now --watch-for 3.5 >/dev/null
seen anim-dim "any(0 < x < 178 for x in w['scrim_opa']) and w['scrim_opa'][-1] == 178" || fail=1
seen anim-dim "any(4 < x < 10 for x in w['bl_now']) and w['bl_now'][-1] == 4" || fail=1
# Sleep (from ~4.5 s to ~9 s): the scrim darkens to black while the backlight fades out.
$dc preview preview/console-preview.yaml /config/preview/shots/anim-sleep --dump "Heating" --pre-wait 3 --watch scrim_opa,bl_now --watch-for 4.5 >/dev/null
seen anim-sleep "any(178 < x < 255 for x in w['scrim_opa']) and w['scrim_opa'][-1] == 255" || fail=1
seen anim-sleep "any(0 < x < 4 for x in w['bl_now']) and w['bl_now'][-1] == 0" || fail=1
# Wake tap while dimmed: after the dim settles at 4, the backlight passes between 4 and 10.
$dc preview preview/console-preview.yaml /config/preview/shots/anim-wake --dump "Heating" --watch bl_now --watch-for 0.1 --pre-wait 4 --clicks "1183,251" >/dev/null
seen anim-wake "any(4 < x < 10 for x in w['bl_now'][w['bl_now'].index(4):]) and w['bl_now'][-1] == 10" || fail=1
# Buttons and pills press in by 3 px (LVGL's default theme grows them) and ease over 150 ms,
# text color included, so a pill's selected colors change together.
python3 tools/preview/check_snapshot.py $sh/anim-wake heating light btn_ease_ms=150 pill_ease_ms=150 btn_press=-3 pill_press=-3 || fail=1
[ $fail = 0 ] || { echo "FAIL: animations"; exit 1; }
echo "PASS: animations"
