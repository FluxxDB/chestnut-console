#!/usr/bin/env bash
# Unit tests for the pure C++ hardware helpers (tab5-thermostat/hardware/*.h): every
# tools/bench/unit/*.cpp built with plain g++ (no ESPHome) and run, inside the pinned ESPHome image
# so nothing needs installing.
set -euo pipefail
cd "$(dirname "$0")/../.."
docker run --rm -v "$PWD:/w" -w /w --entrypoint bash esphome/esphome:2026.10.1 -c \
  'set -e; for src in tools/bench/unit/*.cpp; do
     g++ -std=c++17 -Wall -Werror -I tab5-thermostat/hardware "$src" -o /tmp/t && /tmp/t
   done'
