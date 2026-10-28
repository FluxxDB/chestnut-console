# Desktop preview of the Tab5 console: ESPHome's host platform + an SDL window under Xvfb.
FROM esphome/esphome:2026.10.1
RUN apt-get update \
 && apt-get install -y --no-install-recommends libsdl2-dev xvfb imagemagick xdotool \
 && rm -rf /var/lib/apt/lists/*
