#!/usr/bin/env bash
# Task 1 test: the preview rig renders the console preview to a 1280x720, non-blank PNG.
set -euo pipefail
cd "$(dirname "$0")/../.."
out=tab5-thermostat/preview/shots/rig
docker compose --profile dev run --rm --entrypoint rm preview -rf /config/preview/shots/rig >/dev/null 2>&1
docker compose --profile dev run --rm preview preview/console-preview.yaml "/config/preview/shots/rig"
png="$out/default-light.png"
[ -f "$png" ] || { echo "FAIL: $png missing"; exit 1; }
size=$(docker compose --profile dev run --rm --entrypoint identify preview -format '%wx%h' "/config/preview/shots/rig/default-light.png")
colors=$(docker compose --profile dev run --rm --entrypoint identify preview -format '%k' "/config/preview/shots/rig/default-light.png")
[ "$size" = "1280x720" ] || { echo "FAIL: size $size"; exit 1; }
[ "$colors" -gt 1 ] || { echo "FAIL: blank image ($colors colors)"; exit 1; }
echo "PASS: $png $size, $colors colors"
