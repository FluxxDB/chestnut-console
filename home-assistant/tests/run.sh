#!/usr/bin/env bash
# Tests for the Chestnut HA dashboard.
# Usage:
#   home-assistant/tests/run.sh unit             node unit tests (home-assistant/tests/unit)
#   home-assistant/tests/run.sh e2e [pytest...]  end-to-end: throwaway HA + host sim + Playwright
#                                                (extra args go to pytest, e.g. -k theme, or
#                                                 e2e/test_frame.py to run one file)
#   home-assistant/tests/run.sh all              unit, then e2e
#
# e2e never touches the dev HA (container `homeassistant`, port 8123, config/.storage) or the
# Tab5. It runs:
#   1. a temp copy of the hand-written HA config (configuration/automations/scripts/scenes.yaml,
#      dashboards/, themes/, www/) plus the ha-test/ overlay (port 8124 via ha.env, and the
#      dashboard's device_name switched to the sim);
#   2. a temp copy of the host sim's config with a fresh random API key in its own secrets.yaml
#      (tab5-thermostat/secrets.yaml is never read or written);
#   3. containers chestnut-e2e-sim (the sim, API on 6053) and chestnut-e2e-ha (HA on 8124), host
#      networking; then the chestnut-ha-e2e image onboards HA, adds the sim through ESPHome's
#      config flow (e2e/ha_setup.py) and runs pytest + Playwright;
#   4. on exit (pass, fail or Ctrl-C) it removes both containers and the temp dir.
# Logs and failure screenshots land in home-assistant/tests/.e2e-out/ (gitignored).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"

usage() { echo "usage: $0 unit | e2e [pytest args] | all" >&2; }
mode="${1:-}"
[ $# -gt 0 ] && shift
case "$mode" in
  unit|all) [ $# -eq 0 ] || { usage; exit 2; } ;;
  e2e) ;;
  "") usage; exit 2 ;;
  *) echo "unknown mode: $mode" >&2; usage; exit 2 ;;
esac

die() { echo "run.sh: $*" >&2; exit 1; }

run_unit() {
  command -v node >/dev/null || die "node not found (Node 24 is needed for the unit tests)"
  (cd "$repo" && node --test 'home-assistant/tests/unit/*.test.mjs')
}

if [ "$mode" = unit ]; then run_unit; exit 0; fi

# --- e2e ---------------------------------------------------------------------------------
# Docker may need the docker group in this shell (sg), as on the dev PC's agent shells.
if ! docker info >/dev/null 2>&1; then
  if [ -z "${CHESTNUT_E2E_SG:-}" ] && command -v sg >/dev/null; then
    export CHESTNUT_E2E_SG=1
    exec sg docker -c "$(printf '%q ' "$0" "$mode" "$@")"
  fi
  die "cannot talk to docker"
fi

if [ "$mode" = all ]; then run_unit; fi

compose_image() {  # the image docker-compose.yml pins for a repository, e.g. homeassistant/home-assistant
  grep -m1 -E "^\s*image:\s*$1:" "$repo/docker-compose.yml" | awk '{print $2}'
}
HA_IMAGE="$(compose_image homeassistant/home-assistant)"
ESPHOME_IMAGE="$(compose_image esphome/esphome)"
[ -n "$HA_IMAGE" ] && [ -n "$ESPHOME_IMAGE" ] || die "can't read the pinned images from docker-compose.yml"

TEST_IMAGE=chestnut-ha-e2e
HA_CT=chestnut-e2e-ha
SIM_CT=chestnut-e2e-sim
BUILD_CT=chestnut-e2e-build
RUNNER_CT=chestnut-e2e-runner
HA_PORT="$(sed -n 's/^SETUP_PORT=//p' "$here/ha-test/ha.env")"
SIM_PORT=6053
SIM_DEVICE_NAME="Main Thermostat (Sim)"   # friendly_name in tab5-thermostat/main-thermostat-sim.yaml
CACHE_VOL=chestnut-console_esphome-cache  # shared toolchain cache (as the compose services use)
BUILD_VOL=chestnut-ha-e2e-esphome-build   # the sim's build dir, kept between runs (fast rebuilds)
SIM_PROGRAM=/build/build/main-thermostat-sim/.pioenvs/main-thermostat-sim/program
OUT="$here/.e2e-out"

ha_config="$repo/home-assistant/config"
sim_src="$repo/tab5-thermostat"

port_busy() { ss -Hltn "sport = :$1" 2>/dev/null | grep -q .; }

# Another run in progress? Its runner container is up for the whole run.
if [ "$(docker inspect -f '{{.State.Running}}' "$RUNNER_CT" 2>/dev/null)" = true ]; then
  die "another e2e run is in progress (if it's stale: docker rm -f $RUNNER_CT $HA_CT $SIM_CT)"
fi
# Leftovers from a run that was killed hard (SIGKILL skips the trap): only our own names.
for ct in "$HA_CT" "$SIM_CT" "$BUILD_CT" "$RUNNER_CT"; do
  docker rm -f "$ct" >/dev/null 2>&1 || true
done
port_busy "$HA_PORT" && die "port $HA_PORT is in use (another HA?); the test HA needs it"
port_busy "$SIM_PORT" && die "port $SIM_PORT is in use (a host sim already running?); the test sim needs it"

t0=$SECONDS
stamp() { echo "[e2e +$((SECONDS - t0))s] $*"; }

rm -rf "$OUT"
mkdir -p "$OUT"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/chestnut-e2e.XXXXXX")"

cleanup() {
  local rc=$?
  trap - EXIT INT TERM
  docker logs "$HA_CT" >"$OUT/ha.log" 2>&1 || true
  docker logs "$SIM_CT" >"$OUT/sim.log" 2>&1 || true
  docker rm -f "$RUNNER_CT" "$HA_CT" "$SIM_CT" "$BUILD_CT" >/dev/null 2>&1 || true
  # HA and ESPHome write as root inside the temp dir; remove those files from a container.
  if [ -d "$tmp" ]; then
    docker run --rm -v "$tmp:/t" --entrypoint rm "$HA_IMAGE" -rf /t/ha /t/esphome /t/work >/dev/null 2>&1 || true
    rm -rf "$tmp"
  fi
  stamp "cleaned up (exit $rc); logs in ${OUT#"$repo/"}/"
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

# 1. The test HA config: the hand-written files only (working tree, no runtime state), plus the overlay.
stamp "copying HA config to $tmp/ha"
mkdir -p "$tmp/ha" "$tmp/work"
for f in configuration.yaml automations.yaml scripts.yaml scenes.yaml; do
  cp "$ha_config/$f" "$tmp/ha/"
done
for d in dashboards themes www; do
  if [ -d "$ha_config/$d" ]; then cp -r "$ha_config/$d" "$tmp/ha/"; fi
done
dash="$tmp/ha/dashboards/chestnut.yaml"
if [ -f "$dash" ]; then
  sed -i -E "s/^(\s*device_name:\s*)\"Main Thermostat\"\s*$/\1\"$SIM_DEVICE_NAME\"/" "$dash"
  grep -qF "device_name: \"$SIM_DEVICE_NAME\"" "$dash" || die "overlay: no device_name: \"Main Thermostat\" in dashboards/chestnut.yaml"
fi

# 2. The sim's config, with its own secrets.yaml holding a fresh key (never the real one).
mkdir -p "$tmp/esphome"
cp -r "$sim_src/main-thermostat-sim.yaml" "$sim_src/sim" "$sim_src/thermostat" "$tmp/esphome/"
SIM_KEY="$(openssl rand -base64 32)"
(umask 077; printf 'sim_api_encryption_key: "%s"\n' "$SIM_KEY" >"$tmp/esphome/secrets.yaml")

# 3a. The test image (cached after the first build).
stamp "building the test image"
docker build -q -t "$TEST_IMAGE" "$here" >/dev/null

# 3b. Compile the sim. As the esphome-host compose service: no precompiled header (ESPHome
#     2026.10.1's breaks host builds with a datetime entity), the shared toolchain cache.
stamp "compiling the host sim"
if ! docker run --rm --name "$BUILD_CT" \
    -e ESPHOME_PCH_ENABLE=0 \
    -v "$tmp/esphome:/config" \
    -v "$BUILD_VOL:/config/.esphome" \
    -v "$CACHE_VOL:/cache" \
    -w /config "$ESPHOME_IMAGE" compile main-thermostat-sim.yaml >"$OUT/sim-build.log" 2>&1; then
  tail -n 40 "$OUT/sim-build.log"
  die "sim build failed (log: $OUT/sim-build.log)"
fi

# 3c. Start the sim and HA.
stamp "starting the sim ($SIM_CT, API on $SIM_PORT)"
docker run -d --name "$SIM_CT" --network host -e TZ=America/New_York \
  -v "$BUILD_VOL:/build:ro" --entrypoint "$SIM_PROGRAM" "$ESPHOME_IMAGE" >/dev/null
stamp "starting the test HA ($HA_CT, $HA_IMAGE on $HA_PORT)"
docker run -d --name "$HA_CT" --network host --env-file "$here/ha-test/ha.env" \
  -v "$tmp/ha:/config" "$HA_IMAGE" >/dev/null
sleep 1
[ "$(docker inspect -f '{{.State.Running}}' "$SIM_CT")" = true ] || { docker logs "$SIM_CT" | tail -n 20; die "the sim exited"; }

# 3d. Onboard, add the sim, run the tests. The runner runs as this user (its output files stay
#     yours) with the docker socket's group, so the `sim` fixture can stop/start the sim.
stamp "onboarding HA, adding the sim, running pytest"
sock_gid="$(stat -c %g /var/run/docker.sock)"
docker run --rm --name "$RUNNER_CT" --network host \
  --user "$(id -u):$(id -g)" --group-add "$sock_gid" \
  -e HOME=/tmp \
  -e HA_URL="http://localhost:$HA_PORT" \
  -e SIM_KEY="$SIM_KEY" \
  -e SIM_PORT="$SIM_PORT" \
  -e SIM_CONTAINER="$SIM_CT" \
  -e SIM_DEVICE_NAME="$SIM_DEVICE_NAME" \
  -e E2E_WORK=/work \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$here/e2e:/e2e:ro" \
  -v "$tmp/work:/work" \
  -v "$OUT:/out" \
  "$TEST_IMAGE" bash -c '
    set -euo pipefail
    python ha_setup.py
    python -m pytest -p no:cacheprovider --screenshot=only-on-failure --output=/out/test-results "$@"
  ' bash "$@"
stamp "e2e passed"
