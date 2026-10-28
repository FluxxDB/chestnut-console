#!/usr/bin/env bash
# Compile a host-platform ESPHome config, run it under Xvfb and capture screenshots.
#   shoot.sh <yaml relative to /config> <output dir> [scenario ...] [-- drive.py options]
# Writes <output dir>/<scenario>-<theme>.png (and .json when the config has a ui_snapshot sensor).
set -euo pipefail
yaml=$1; out=$2; shift 2
cd /config
mkdir -p "$out"

# Same toolchain cache layout as the esphome image's entrypoint (we replace that entrypoint).
export PLATFORMIO_PLATFORMS_DIR=/cache/platformio/platforms
export PLATFORMIO_PACKAGES_DIR=/cache/platformio/packages
export PLATFORMIO_CACHE_DIR=/cache/platformio/cache
export ESPHOME_HOST_PREFIX=/cache/host

if ! esphome compile "$yaml" > "$out/compile.log" 2>&1; then
  tail -40 "$out/compile.log"; exit 1
fi
bin=$(sed -n "s/.*Successfully compiled program to path '\(.*\)'.*/\1/p" "$out/compile.log" | tail -1)
[ -x "$bin" ] || { echo "no program binary in compile log"; exit 1; }

Xvfb :99 -screen 0 1280x720x24 -nolisten tcp > /dev/null 2>&1 &
xvfb=$!
export DISPLAY=:99
sleep 1
"$bin" > "$out/run.log" 2>&1 &
prog=$!
trap 'kill $prog $xvfb 2>/dev/null || true; chown -R "${HOST_UID:-1000}:${HOST_GID:-1000}" "$out" "$(dirname "$out")" 2>/dev/null || true' EXIT

for _ in $(seq 1 100); do
  python3 -c 'import socket,sys; s=socket.socket(); s.settimeout(0.2); sys.exit(s.connect_ex(("127.0.0.1",6053)))' && break
  sleep 0.2
done

python3 /tools/drive.py --out "$out" "$@"
