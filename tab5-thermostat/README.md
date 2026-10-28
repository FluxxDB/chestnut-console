# Tab5 thermostat firmware

ESPHome config for the Main Thermostat. This folder is mounted as `/config` in the `esphome` container.

## First-time setup

1. **Find your screen revision.** The sticker on the back of the Tab5, just above the Espressif logo, names the display driver chip. In [`tab5-thermostat.yaml`](tab5-thermostat.yaml), leave exactly one `display:` line active:
   - ILI9881C → `hardware/display-ili9881c.yaml` (original, made before Oct 2025)
   - ST7123 → `hardware/display-st7123.yaml`
   - ST7121 → `hardware/display-st7121.yaml` (also try this one if ST7123 leaves the screen blank while touch works)
2. **Secrets.** `cp secrets.yaml.example secrets.yaml` and fill it in. The Tab5 only joins **2.4 GHz** Wi-Fi.
3. **Compile** (from the repo root):
   ```bash
   docker compose run --rm --no-deps esphome compile tab5-thermostat.yaml
   ```
   The first build downloads the ESP-IDF toolchain and takes a while. Later builds are quick.

## Flashing

**First flash over USB-C.** The factory image is `.esphome/build/tab5-thermostat/build/firmware.factory.bin`. Any of these work:

- **Linux with the Tab5 attached:** `docker compose run --rm --no-deps --device /dev/ttyACM0 esphome run tab5-thermostat.yaml --device /dev/ttyACM0`
- **WSL (what the PC uses, no admin needed):** run the official Windows build of esptool ([releases](https://github.com/espressif/esptool/releases), `esptool-vX-windows-amd64.zip`) against the Tab5's COM port (it shows up as `303a:1001 USB JTAG/serial debug unit`):
  ```bash
  cp tab5-thermostat/.esphome/build/tab5-thermostat/build/firmware.factory.bin /mnt/c/Users/<you>/AppData/Local/Temp/
  esptool.exe --chip esp32p4 --port COM6 --baud 921600 write-flash 0x0 C:\\Users\\<you>\\AppData\\Local\\Temp\\firmware.factory.bin
  ```
  `esptool.exe --port COM6 chip-id` reads the chip revision. Or attach the Tab5 to WSL with usbipd-win (`usbipd bind` once as admin, then `usbipd attach --wsl --busid <id>`) and do the Linux step.
- **Browser:** https://web.esphome.io in Chrome or Edge → Connect → Install → choose the factory `.bin`.

**After that, updates go over Wi-Fi:**
```bash
docker compose run --rm --no-deps esphome run tab5-thermostat.yaml --device <tab5-ip>
```
The Tab5 shows its IP address on screen. mDNS (`tab5-thermostat.local`) won't resolve from inside WSL's NAT, so use the IP.

**Logs over Wi-Fi:**
```bash
docker compose run --rm --no-deps esphome logs tab5-thermostat.yaml --device <tab5-ip>
```
The I2C scan in the boot log tells you the revision: touch at `0x14` is the original, `0x55` is ST7123/ST7121.

## Connecting to Home Assistant

In HA: Settings → Devices & services → Add integration → ESPHome → host = the Tab5's IP, with the `api_encryption_key` from `secrets.yaml`. Then, in the device's options, enable **"Allow the device to perform Home Assistant actions"** (needed later for controlling the top floor from the Tab5).

## Phone page

Browse to `http://<tab5-ip>/` and log in with `web_username` / `web_password` from `secrets.yaml`. It only works on the home network; never port-forward it to the internet.
