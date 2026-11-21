#!/usr/bin/env bash
# Milestone 4 bench test: the Tab5 runs the real ENV III and Unit 4-Relay on Port A. Builds and
# flashes over Wi-Fi, reads 60 s of logs, then reads states from the Tab5's own web page: the relay
# unit answers (no relay fault), the room temperature is sane, heat and cool are off after boot and
# the fan relay matches the fan mode.
#   TAB5_IP=<tab5-ip> tools/bench/test_bench.sh   (the Tab5 shows its IP on screen)
# Needs tab5-thermostat/secrets.yaml (the web page login is read from it, never put on a command line).
set -euo pipefail
cd "$(dirname "$0")/../.."
ip=${TAB5_IP:?set TAB5_IP to the IP address shown on the Tab5 screen}
out=tab5-thermostat/preview/shots/bench
mkdir -p "$out"
fail() { echo "FAIL: $*"; exit 1; }

docker compose run --rm esphome run tab5-thermostat.yaml --device "$ip" --no-logs > "$out/ota.log" 2>&1 \
  || { tail -20 "$out/ota.log"; fail "build/OTA"; }
grep -q "OTA successful" "$out/ota.log" || fail "no OTA success line"
sleep 15
# The timeout runs inside the container (see test_device.sh: a host-side one leaves the log stream attached).
docker compose run --rm --entrypoint timeout esphome 60 /entrypoint.sh logs tab5-thermostat.yaml --device "$ip" 2>&1 \
  | sed 's/\x1b\[[0-9;]*m//g' > "$out/logs.txt" || true
grep -q "Room Temperature" "$out/logs.txt" || fail "Room Temperature missing from the config dump"
if grep -E "\[E\]" "$out/logs.txt"; then fail "errors in the device log"; fi
if grep -q -i "Communication with SHT3xD failed" "$out/logs.txt"; then fail "the ENV III didn't answer at boot"; fi

# States from the web page (digest auth; the login goes into a private curl config file).
cfg=$(mktemp); trap 'rm -f "$cfg"' EXIT; chmod 600 "$cfg"
python3 - "$cfg" <<'EOF'
import sys, yaml
d = yaml.safe_load(open("tab5-thermostat/secrets.yaml"))
open(sys.argv[1], "w").write('user = "%s:%s"\ndigest\n' % (d["web_username"], d["web_password"]))
EOF
state() {  # state <domain> <entity name> -> the JSON "state" (binary) or "value" (sensor)
  curl -s -m 10 --config "$cfg" "http://$ip/$1/$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1]))' "$2")" \
    | python3 -c 'import sys,json
try: j=json.load(sys.stdin)
except Exception: print("MISSING"); sys.exit()
print(j.get("value") if "value" in j and not isinstance(j.get("value"), bool) else j.get("state"))'
}
rf=$(state binary_sensor "Relay Fault"); [ "$rf" = "OFF" ] || fail "Relay Fault is $rf (want OFF)"
t=$(state sensor "Room Temperature")
python3 -c "import sys; v=float(sys.argv[1]); sys.exit(0 if 5 <= v <= 40 else 1)" "$t" 2>/dev/null \
  || fail "Room Temperature is $t (want 5-40 °C)"
# Heat and cool stay off through the startup delay. The fan follows the restored fan mode (Fan On
# runs G in any mode, so it's on again after a reboot if it was on before).
for c in "Call Heat" "Call Cool"; do
  s=$(state binary_sensor "$c"); [ "$s" = "OFF" ] || fail "$c is $s after boot (want OFF)"
done
fan_mode=$(curl -s -m 10 --config "$cfg" "http://$ip/climate/Main%20Thermostat" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("fan_mode"))')
want_fan=OFF; [ "$fan_mode" = "ON" ] && want_fan=ON
s=$(state binary_sensor "Call Fan"); [ "$s" = "$want_fan" ] || fail "Call Fan is $s with fan mode $fan_mode (want $want_fan)"
echo "PASS: bench (room ${t} °C, relay unit answering, heat/cool off, fan ${want_fan} for fan mode ${fan_mode}, $(grep -cE "\[W\]" "$out/logs.txt") warnings)"
