#!/usr/bin/env bash
# Milestone 4's long run: streams the Tab5's log for HOURS (default 24) into
# tools/bench/out/log-<date>.txt (gitignored), then reports the [E] and [W] counts and every
# distinct error line. Exit 1 if there were errors.
#   TAB5_IP=<tab5-ip> [HOURS=24] tools/bench/collect_log.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
ip=${TAB5_IP:?set TAB5_IP to the IP address shown on the Tab5 screen}
secs=$(python3 -c "import sys; print(max(1, round(float(sys.argv[1]) * 3600)))" "${HOURS:-24}")
mkdir -p tools/bench/out
log=tools/bench/out/log-$(date +%Y%m%d-%H%M).txt
echo "collecting ${HOURS:-24} h of logs into $log"
# The timeout runs inside the container (see test_device.sh: a host-side one leaves the log stream attached).
docker compose run --rm --entrypoint timeout esphome "$secs" /entrypoint.sh logs tab5-thermostat.yaml --device "$ip" 2>&1 \
  | sed -u 's/\x1b\[[0-9;]*m//g' > "$log" || true
errors=$(grep -cE "\[E\]" "$log" || true)
warnings=$(grep -cE "\[W\]" "$log" || true)
echo "errors: $errors, warnings: $warnings ($(wc -l < "$log") lines)"
if [ "$errors" -gt 0 ]; then
  grep -E "\[E\]" "$log" | sed -E 's/^\[[0-9:.]+\]//' | sort | uniq -c | sort -rn
  exit 1
fi
