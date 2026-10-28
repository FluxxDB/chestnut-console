#!/usr/bin/env bash
# Task 4 test: every scenario shows exactly what the UI spec's binding table says,
# a burst of + taps is one debounced set_target write, and the target clamps at 90.
set -euo pipefail
cd "$(dirname "$0")/../.."
dc="docker compose --profile dev run --rm"
sh="tab5-thermostat/preview/shots"
$dc --entrypoint rm preview -rf /config/preview/shots/bind /config/preview/shots/debounce /config/preview/shots/clamp >/dev/null 2>&1
$dc preview preview/console-preview.yaml /config/preview/shots/bind --dump \
  "Heating" "Cooling" "Eco auto band" "Hold" "Schedule off" "Clock not set" "Waiting" \
  "Off fan on" "Sensor fault" "Interlock fault" "Unknowns" "Finishing" "Interlock while heating" "Sensor fault mid-run" >/dev/null
c="python3 tools/preview/check_snapshot.py $sh/bind"
$c heating light room=71 status=Heating "sub=~^to 72° · ([0-9]+ min so far|just started)$" target=72° "tgt_label=Comfort target" tgt_comfort= \
  "sched=Comfort until 10:30 pm" resume_visible=0 mode_sel=0100 fan_sel=10 lvl_sel=10 hum=42% hum_cap=Comfortable \
  banner_visible=0 hist_visible=1 out_temp=— pm_visible=1 marker=ff7b1b "clock=~^[0-9]{1,2}:[0-9]{2} (am|pm)$" "date=~^[A-Z][a-z]{2} [0-9]{1,2}$"
$c cooling light room=76 status=Cooling "sub=~^to 74° · ([0-9]+ min so far|just started)$" target=74° mode_sel=0010 marker=4098ff "sched=Comfort until 8:00 am"
$c eco-auto-band light target=68–76° "tgt_label=Eco target" "tgt_comfort=Comfort 72°" status=Idle "sub=holding 68–76°" lvl_sel=01 mode_sel=0001 marker=8b8d90 "sched=Eco until 5:30 pm" "room_deg_gap=~^[0-9]+$"
$c hold light target=69° status=Heating "sub=~^to 69° · ([0-9]+ min so far|just started)$" "sched=Holding 69° until 10:30 pm" resume_visible=1 "topbar_gap=~^[1-9][0-9]*$"
$c schedule-off light "sched=Schedule off" resume_visible=0
$c clock-not-set light "sched=Schedule paused: clock not set" resume_visible=0 "topbar_gap=~^[1-9][0-9]*$"
$c waiting light room=69 status=Idle "sub=Waiting · short-cycle protection"
$c off-fan-on light status=Fan "sub=System is off · fan on" target=Off pm_visible=0 mode_sel=1000 marker=00b595 tgt_label=Target
$c sensor-fault light room=— status=Paused banner_visible=1 hist_visible=0 "banner=Temperature sensor problem. Heating and cooling are paused." marker=8b8d90
$c interlock-fault light status=Paused banner_visible=1 hist_visible=0 "banner=Heating and cooling were both requested, so the system stopped. Clear it in Home Assistant once it's checked."
$c unknowns light room=— target=— hum=— hum_cap= out_temp=— sched=
# Switched to Cool mid-heat: under M2 the furnace finishes its minimum run first (up to 3 min).
$c finishing light status=Heating "sub=Finishing up · stops soon" marker=ff7b1b mode_sel=0010
# M2: while interlock_fault is latched the climate can still report HEATING with the relays off
# (mac-chestnut-console). A fault always wins: Paused, grey marker, no "to 72°" line.
$c interlock-while-heating light status=Paused sub= marker=8b8d90 banner_visible=1
# M2: a sensor fault lets a running call finish its minimum run (call_heat still on). Say so, so the
# furnace still running doesn't look like a stuck relay (mac-chestnut-console's suggestion).
$c sensor-fault-mid-run light status=Paused "sub=Finishing up · stops soon" marker=8b8d90 banner_visible=1
# Debounce: 5 quick taps on + from 72 -> one write of 77.
$dc preview preview/console-preview.yaml /config/preview/shots/debounce --dump "Heating" \
  --clicks "1183,251;1183,251;1183,251;1183,251;1183,251" >/dev/null
python3 tools/preview/check_states.py $sh/debounce heating set_target=77 _writes.set_target=1
python3 tools/preview/check_snapshot.py $sh/debounce heating light target=77°
# Clamp: from 89, three taps on + stop at 90.
$dc preview preview/console-preview.yaml /config/preview/shots/clamp --dump "Heating" --number set_target=89 \
  --clicks "1183,251;1183,251;1183,251" >/dev/null
python3 tools/preview/check_states.py $sh/clamp heating set_target=90
python3 tools/preview/check_snapshot.py $sh/clamp heating light target=90°
echo "PASS: bindings"
