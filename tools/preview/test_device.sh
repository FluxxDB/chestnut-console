#!/usr/bin/env bash
# Task 7 test: the console runs on the real Tab5. Builds, flashes over Wi-Fi, then reads 60 s
# of logs: no errors, the console's entities exist, and LVGL never blocks for long.
#   TAB5_IP=10.0.0.193 tools/preview/test_device.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
ip=${TAB5_IP:-10.0.0.193}
out=tab5-thermostat/preview/shots/device
mkdir -p "$out"
[ ! -e tab5-thermostat/ui/hello.yaml ] || { echo "FAIL: ui/hello.yaml still exists"; exit 1; }
grep -q "Desktop preview" tab5-thermostat/README.md || { echo "FAIL: README lacks the desktop preview section"; exit 1; }
docker compose run --rm --no-deps esphome run tab5-thermostat.yaml --device "$ip" --no-logs > "$out/ota.log" 2>&1 \
  || { tail -20 "$out/ota.log"; echo "FAIL: build/OTA"; exit 1; }
grep -q "OTA successful" "$out/ota.log" || { echo "FAIL: no OTA success line"; exit 1; }
sleep 15
timeout 60 docker compose run --rm --no-deps esphome logs tab5-thermostat.yaml --device "$ip" 2>&1 \
  | sed 's/\x1b\[[0-9;]*m//g' > "$out/logs.txt" || true
grep -q "Template Switch 'Dark Theme'" "$out/logs.txt" || { echo "FAIL: console entities missing from the config dump"; exit 1; }
grep -q "IP Address" "$out/logs.txt" || { echo "FAIL: IP Address sensor missing"; exit 1; }
if grep -E "\[E\]" "$out/logs.txt"; then echo "FAIL: errors in the device log"; exit 1; fi
if grep -E "lvgl took a long time" "$out/logs.txt"; then echo "FAIL: LVGL blocked the loop"; exit 1; fi
echo "PASS: device ($(grep -c "" "$out/logs.txt") log lines, $(grep -cE "\[W\]" "$out/logs.txt") warnings)"
