# Screen auto-flip: design

Status: approved by Dang 2026-11-21, with an HA lock added and a 1 s settle time. Owner: PC (`tab5-thermostat/hardware/`, UI rotation).

## Why

The wall enclosure (designed 2026-11-21, files outside the repo) mounts the Tab5 **camera on the left**, the other way round from the bench, where the screen runs at `display_rotation: 270°`. Dang asked for the screen to follow the device's orientation instead of a fixed setting, so the Tab5 can hang or stand either way round.

## What it does

- The Tab5's IMU (Bosch BMI270 on the internal I2C bus, `bsp_bus`, default address 0x68) reports which way gravity points.
- The screen shows the right way up in **either landscape pose**:
  - camera on the right: 270°, today's setting;
  - camera on the left: 90°.
- **Portrait poses and lying flat change nothing.** The screen keeps its last rotation. The UI is a fixed 1280 × 720 landscape layout, so portrait isn't supported.
- **A new pose must hold for 1 s before the screen flips**, so picking the Tab5 up or brushing it doesn't make it flicker.
- **At boot** the screen starts at `display_rotation` (270°) and corrects itself within about a second if the Tab5 is the other way round.
- **Touch follows the screen.** ESPHome's LVGL rotates touch coordinates with the display.
- **HA lock (Dang's choice):** a config select, **Screen Rotation**, with three options:
  - **Auto**, the default: follow the IMU;
  - **Camera right**: pin 270°;
  - **Camera left**: pin 90°.
  It's restored after a reboot. A lock restored at boot is applied before LVGL starts. Switching back to Auto shows whatever pose the IMU has settled on.

## How

ESPHome 2026.10.1 already has every piece:

- **IMU driver:** the `bmi270` component, polled every 250 ms.
- **Pose reading:** the `motion` sensor of `type: orientation`. It reports the in-plane gravity direction snapped to 0/90/180/270°, or NAN while the device lies within 30° of flat.
- **Runtime rotation:** `LvglComponent::set_rotation()`, the code behind `lvgl.display.set_rotation`. Rotation is already enabled because `ui/console.yaml` sets `rotation`, so the screen uses the same PPA-accelerated software rotation as today.

New pieces:

- **`tab5-thermostat/hardware/screen_flip.h`:** pure C++ (no ESPHome), unit-tested with plain g++ like `relay_unit.h`.
  - `ScreenFlip(camera_right_reading, boot_rotation, settle_ms)`
  - `int step(float reading, uint32_t now_ms)` returns the rotation to show.
  - A reading within 30° of the camera-right value means 270°; within 30° of the opposite value means 90°. Anything else, or NAN, keeps the current rotation and drops a pending flip.
  - Survives `millis()` wraparound.
  - `screen_rotation_for(lock_index, auto_rotation)` applies the HA lock. An unknown index counts as Auto.
- **`tab5-thermostat/hardware/screen-flip.yaml`**, a package included from `tab5-thermostat.yaml`:
  - the `bmi270` component;
  - the internal orientation sensor (not sent to HA, to avoid traffic 4 times a second);
  - an `on_value` lambda that feeds `ScreenFlip`;
  - the `Screen Rotation` select;
  - a `screen_apply` script that shows `screen_rotation_for(lock, flip.rotation())` and calls `id(lvgl_main)->set_rotation()` only when that differs from what LVGL shows;
  - log lines when the reading changes and when the screen flips.
- **`imu_camera_right`:** a substitution in that package. It is the orientation reading when the Tab5 stands camera-right, which depends on how the BMI270 sits on the board, so it's **measured once on the bench**. Flash, stand the Tab5 both ways, read the log, set the value.
- **`tools/bench/test_unit.sh`** runs every `tools/bench/unit/*.cpp`, not only the relay test.
- The desktop preview doesn't include the package, so it keeps its fixed rotation.

## Not doing

- Portrait layouts.
- Using the gyroscope. Gravity alone decides the pose.

## Tests

- **Unit** (`tools/bench/unit/test_screen_flip.cpp`):
  - boot rotation;
  - flat or same pose keeps the rotation;
  - the opposite pose flips after exactly the settle time;
  - flipping back;
  - a brief turn doesn't flip;
  - portrait and flat drop a pending flip;
  - booting upside down corrects itself;
  - other calibrations, including 0/180 and 360 ≡ 0;
  - unsnapped angles: within 30° counts, 45° doesn't;
  - `millis()` wraparound;
  - the lock: Auto follows the IMU, the other two pin the rotation, an unknown index counts as Auto.
- **Build:** `docker compose run --rm esphome compile tab5-thermostat.yaml`, then the existing suites.
- **On the device:**
  - the i2c scan shows 0x68;
  - stood camera-right the screen reads correctly, and turned camera-left it flips within about a second;
  - touch lands where tapped in both poses;
  - portrait and flat leave it alone;
  - the HA lock pins it and survives a reboot.

## Bench result (2026-11-22)

- **IMU:** the i2c scan found the BMI270 at 0x68, polled every 250 ms.
- **Calibration:** camera-right reads 0°, camera-left reads 180°, so `imu_camera_right: "0"`. The first flash used a placeholder of 90, so both poses counted as portrait and nothing flipped, as designed.
- **Flipping:** turned camera-left, the screen went to 90° about 1.25 s after the 180° reading. Back camera-right, it returned to 270°. Lying flat in between changed nothing.
- **Touch:** Dang tapped in both poses and taps landed in the right place.
- **HA lock:** "Camera left", set through the web page, pinned the screen at 90° straight away; "Auto" returned it to 270° (camera-right).
- **Tests:** `tools/bench/test_unit.sh` passed (screen flip 87 checks, relay link 31). `tab5-thermostat/tests/run.sh all` passed 130 scenarios. The device firmware compiles (RAM 18.1 %, flash 17.8 %).
