#!/usr/bin/env bash
# Every console preview test, in order. Stops at the first failure.
set -euo pipefail
cd "$(dirname "$0")"
for t in test_hist.sh test_rig.sh test_stub.sh test_layout.sh test_bindings.sh test_theme.sh test_idle.sh test_anim.sh test_review.sh test_wall.sh test_contract.sh; do
  echo "== $t"
  if ! out=$(./"$t" 2>&1); then
    echo "$out" | grep -E "FAIL|want" | head -20
    echo "FAIL: $t"; exit 1
  fi
  echo "$out" | grep -E "^PASS" | tail -1
done
echo "PASS: all console tests"
