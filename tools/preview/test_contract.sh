#!/usr/bin/env bash
# The preview's stand-in (ui/dev/contract-stub.yaml) can't drift from milestone 2's contract: every
# entity the console uses exists in both with the same type, and the stub defines nothing M2 lacks
# (mac-chestnut-console's ask, when the stub became a preview-only fixture).
# M2's packages come from this tree once merged, else from origin/mac/thermostat-logic.
set -euo pipefail
cd "$(dirname "$0")/../.."
t=tab5-thermostat
m2=("$t/thermostat/logic.yaml" "$t/sim/virtual-house.yaml")
if [ ! -f "${m2[0]}" ]; then
  tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
  git fetch -q origin mac/thermostat-logic
  for i in "${!m2[@]}"; do
    git show "origin/mac/thermostat-logic:${m2[$i]}" > "$tmp/$i.yaml"
    m2[$i]="$tmp/$i.yaml"
  done
  echo "  (M2 packages from origin/mac/thermostat-logic @ $(git rev-parse --short origin/mac/thermostat-logic))"
fi
python3 tools/preview/check_contract.py "$t/ui/dev/contract-stub.yaml" \
  "$t/ui/console.yaml" "$t/ui/console-logic.yaml" "$t/ui/theme.yaml" -- "${m2[@]}"
