#!/usr/bin/env bash
# Relay unit unit test: tab5-thermostat/hardware/relay_unit.h built with plain g++ (no ESPHome) and
# run, inside the pinned ESPHome image so nothing needs installing.
set -euo pipefail
cd "$(dirname "$0")/../.."
docker run --rm -v "$PWD:/w" -w /w --entrypoint bash esphome/esphome:2026.10.1 -c \
  'g++ -std=c++17 -Wall -Werror -I tab5-thermostat/hardware tools/bench/unit/test_relay_unit.cpp -o /tmp/t && /tmp/t'
