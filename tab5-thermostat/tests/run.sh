#!/usr/bin/env bash
# Run the thermostat-logic tests inside a pinned ESPHome image.
# Usage:
#   tests/run.sh unit                  C++ unit tests (tests/unit/*.cpp)
#   tests/run.sh build                 compile the scenario-test host build only
#   tests/run.sh scenarios [-k expr]   compile it once, then run tests/scenarios with pytest
#   tests/run.sh all                   unit, then scenarios
set -euo pipefail

mode="${1:-}"
[ $# -gt 0 ] && shift
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
config_dir="$(dirname "$here")"
image="chestnut-m2-tests"

usage() { echo "usage: $0 unit | build | scenarios [pytest args, e.g. -k expr] | all" >&2; }

case "$mode" in
  unit|build|all) [ $# -eq 0 ] || { usage; exit 2; } ;;
  scenarios) ;;
  "") usage; exit 2 ;;
  *) echo "unknown mode: $mode" >&2; usage; exit 2 ;;
esac

docker build -q -t "$image" "$here" >/dev/null

# run_in_container SCRIPT [ARGS...]: ARGS reach SCRIPT as "$@".
# ESPHome 2026.10.1 host builds with a datetime entity fail under its precompiled header
# (logger_host.cpp's unqualified time() finds namespace esphome::time), so build without it.
run_in_container() {
  local script="$1"; shift
  docker run --rm \
    --entrypoint bash \
    -e ESPHOME_PCH_ENABLE=0 \
    -v "$config_dir:/config" \
    -v chestnut-console_esphome-cache:/cache \
    -w /config \
    "$image" -c "$script" bash "$@"
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

# Compiles tests/main-thermostat-test.yaml; prints only the result, or the log tail on failure.
build_test_entry='
  build() {
    log="$(mktemp)"
    if esphome compile tests/main-thermostat-test.yaml >"$log" 2>&1; then
      grep -m1 "Successfully compiled" "$log" || true
    else
      tail -n 60 "$log"; echo "build failed" >&2; return 1
    fi
  }
'

run_build() {
  run_in_container "$build_test_entry"'
    set -euo pipefail
    build
  '
}

# The build and the tests run in one container: the tests start the program as a subprocess
# and talk to it on 127.0.0.1:6053. The -W hides pytest-asyncio 0.24's own Python 3.14
# deprecation warnings (hundreds per run), not ours.
run_scenarios() {
  run_in_container "$build_test_entry"'
    set -euo pipefail
    build
    PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider -o asyncio_mode=auto -o asyncio_default_fixture_loop_scope=function \
      -W "ignore::DeprecationWarning:pytest_asyncio.plugin" \
      tests/scenarios "$@"
  ' "$@"
}

case "$mode" in
  unit) run_unit ;;
  build) run_build ;;
  scenarios) run_scenarios "$@" ;;
  all) run_unit; run_scenarios ;;
esac
