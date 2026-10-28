#!/usr/bin/env bash
# Final-review fixes: one independent check per finding, all reported, exit 1 if any fail.
set -uo pipefail
cd "$(dirname "$0")/../.."
dc="docker compose --profile dev run --rm"
sh="tab5-thermostat/preview/shots"
y="preview/console-preview.yaml"
fails=0
run() { $dc "$@" >/dev/null 2>&1; }
check() { local name=$1; shift; if "$@"; then echo "PASS $name"; else echo "FAIL $name"; fails=$((fails+1)); fi; }
$dc --entrypoint rm preview -rf /config/preview/shots/review >/dev/null 2>&1

# 1: the history line keeps moving once the ring is full (target unchanged between scenarios).
run preview $y /config/preview/shots/review/hist --dump --pre-wait 10 "Heating" "Waiting"
check "1 history keeps redrawing when full" python3 -c "
import json,sys; d='$sh/review/hist'
a=json.load(open(d+'/heating-light.json'))['hist_last_y']; b=json.load(open(d+'/waiting-light.json'))['hist_last_y']
print('  last y', a, '->', b); sys.exit(0 if a and b and a != b else 1)"

# 2: the status marker sits next to the word, whatever its length.
run preview $y /config/preview/shots/review/marker --dump "Waiting" "Off fan on"
check "2 marker next to Idle" python3 tools/preview/check_snapshot.py $sh/review/marker waiting light "marker_gap=~^1[0-4]$"
check "2 marker next to Fan" python3 tools/preview/check_snapshot.py $sh/review/marker off-fan-on light "marker_gap=~^1[0-4]$"

# 3: outside shows HA's value, and "—" once Home Assistant (the API client) is gone.
run preview $y /config/preview/shots/review/outside --dump "Heating" --disconnect 2 \
  --ha-state "weather.forecast_home:temperature=48" --ha-state "weather.forecast_home:=cloudy"
check "3 outside from HA" python3 tools/preview/check_snapshot.py $sh/review/outside heating light out_temp=48° out_cond=Cloudy
check "3 outside blank without HA" python3 -c "
import json,sys; d=json.load(open('$sh/review/outside/heating-light-reconnect.json'))
t,c=d.get('out_temp_offline'),d.get('out_cond_offline')
print('  while disconnected:', t, repr(c)); sys.exit(0 if t=='—' and c=='' else 1)"

# 4: minutes running are timed on the screen (preview: 1 s per 'minute'), not from the float epoch.
run preview $y /config/preview/shots/review/minutes --dump --pre-wait 3 "Heating"
check "4 minutes counted locally" python3 tools/preview/check_snapshot.py $sh/review/minutes heating light "sub=~^to 72° · [2-6] min so far$"

# 5: '+' then '−' inside the debounce writes nothing (no pointless hold).
run preview $y /config/preview/shots/review/noop --dump "Heating" --clicks "1183,251;803,251"
check "5 no-op burst writes nothing" python3 tools/preview/check_states.py $sh/review/noop heating _writes.set_target=0 schedule_hold=false

# 10: a backlight restored dim comes back to full brightness at boot.
run preview $y /config/preview/shots/review/boot --dump --settle 1.5 "Heating"
check "10 in-use brightness after boot" python3 tools/preview/check_states.py $sh/review/boot heating display_backlight.brightness=0.1

# 11: on boot the theme follows the sun (equator, longitude where it's now local midnight / noon).
night=$(python3 -c "import datetime as d; h=d.datetime.now(d.timezone.utc); u=h.hour+h.minute/60; print(round(((-u*15+180)%360)-180,1))")
day=$(python3 -c "print(round((($night+180+180)%360)-180,1))")
$dc -e SUBS="-s house_latitude 0 -s house_longitude $night" preview $y /config/preview/shots/review/night --dump --no-theme --pre-wait 3 "Heating" >/dev/null 2>&1
check "11 dark at local midnight ($night)" python3 tools/preview/check_states.py $sh/review/night heating dark_theme=true
$dc -e SUBS="-s house_latitude 0 -s house_longitude $day" preview $y /config/preview/shots/review/day --dump --no-theme --pre-wait 3 "Heating" >/dev/null 2>&1
check "11 light at local noon ($day)" python3 tools/preview/check_states.py $sh/review/day heating dark_theme=false

# 12 (Mac review 1): tapping the lit Heat, fan Auto and Comfort pills sends nothing (under M2 a
# re-sent option would start a hold); tapping unlit Cool and Eco still sends (the taps land).
run preview $y /config/preview/shots/review/lit --dump "Heating" --clicks "293,649;758,649;1043,649"
check "12 lit pills send nothing" python3 tools/preview/check_states.py $sh/review/lit heating _writes.main_thermostat=0 _writes.comfort_level=0
run preview $y /config/preview/shots/review/unlit --dump "Heating" --clicks "410,649;1177,649"
check "12 unlit pills still send" python3 tools/preview/check_states.py $sh/review/unlit heating main_thermostat.mode=COOL comfort_level=Eco

# 13 (Mac review 4): an unchanged status marker isn't redrawn on every 250 ms refresh.
run preview $y /config/preview/shots/review/marker-still --dump "Waiting" --watch marker_redraws --watch-for 2
check "13 unchanged marker not redrawn" python3 -c "
import json,sys; w=[int(x) for x in json.load(open('$sh/review/marker-still/waiting-light-states.json'))['_watch.marker_redraws']]
print('  marker redraw count over 2 s:', w); sys.exit(0 if w and w[-1] == w[0] else 1)"

[ $fails -eq 0 ] && echo "PASS: review fixes" || { echo "FAIL: $fails review checks"; exit 1; }
