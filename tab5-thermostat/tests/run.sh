#!/usr/bin/env bash
# Run the thermostat-logic tests inside a pinned ESPHome image.
# Usage: tests/run.sh unit
set -euo pipefail

mode="${1:-}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
config_dir="$(dirname "$here")"
image="chestnut-m2-tests"

usage() { echo "usage: $0 unit" >&2; }

case "$mode" in
  unit) ;;
  "") usage; exit 2 ;;
  *) echo "unknown mode: $mode" >&2; usage; exit 2 ;;
esac

docker build -q -t "$image" "$here" >/dev/null

run_in_container() {
  docker run --rm \
    --entrypoint bash \
    -v "$config_dir:/config" \
    -v chestnut-console_esphome-cache:/cache \
    -w /config \
    "$image" -c "$1"
}

run_unit() {
  run_in_container '
    set -euo pipefail
    out="$(mktemp -d)"
    shopt -s nullglob
    tests=(tests/unit/*.cpp)
    if [ ${#tests[@]} -eq 0 ]; then echo "no unit tests found" >&2; exit 1; fi
    for src in "${tests[@]}"; do
      name="$(basename "$src" .cpp)"
      g++ -std=c++17 -Wall -Werror -I thermostat -I sim "$src" -o "$out/$name"
      "$out/$name"
    done
  '
}

case "$mode" in
  unit) run_unit ;;
esac
