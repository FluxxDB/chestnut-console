#!/usr/bin/env bash
# History ring unit test: ui/console_hist.h built with plain g++ (no ESPHome) and run.
set -euo pipefail
cd "$(dirname "$0")/../.."
docker compose --profile dev run --rm --entrypoint bash preview -c \
  'g++ -std=c++17 -Wall -Werror -I /config/ui /tools/unit/test_hist.cpp -o /tmp/test_hist && /tmp/test_hist'
