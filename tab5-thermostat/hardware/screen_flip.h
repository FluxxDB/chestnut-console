// Screen auto-flip: turns the IMU's orientation reading into one of the two landscape screen
// rotations, so the Tab5 can stand or hang either way round (camera on the right: 270 degrees,
// camera on the left: 90 degrees). Pure C++ (no ESPHome), so tools/bench/test_unit.sh tests it with
// plain g++. screen-flip.yaml feeds it ESPHome's motion "orientation" sensor (0/90/180/270, NAN
// when lying flat). Spec: docs/superpowers/specs/2026-11-21-screen-auto-flip-design.md.
#pragma once

#include <cmath>
#include <cstdint>

namespace chestnut_hw {

constexpr int ROTATION_CAMERA_RIGHT = 270;
constexpr int ROTATION_CAMERA_LEFT = 90;

// Smallest angle between two directions, in degrees (0..180).
inline float angle_between(float a, float b) {
  float d = std::fmod(std::fabs(a - b), 360.0f);
  return d > 180.0f ? 360.0f - d : d;
}

class ScreenFlip {
 public:
  // camera_right_reading: the orientation reading while the Tab5 stands camera-right (measured on
  // the bench; depends on how the IMU sits on the board). boot_rotation: what the screen shows now.
  ScreenFlip(float camera_right_reading, int boot_rotation, uint32_t settle_ms)
      : camera_right_(camera_right_reading), rotation_(boot_rotation), settle_ms_(settle_ms) {}

  // One reading at now_ms. Returns the rotation to show: it changes only once the other landscape
  // pose has been read continuously for settle_ms. Portrait, flat (NAN) and the current pose drop a
  // pending flip.
  int step(float reading, uint32_t now_ms) {
    const int want = pose_(reading);
    if (want == 0 || want == rotation_) {
      pending_ = 0;
      return rotation_;
    }
    if (pending_ != want) {
      pending_ = want;
      since_ = now_ms;
    } else if (now_ms - since_ >= settle_ms_) {
      rotation_ = want;
      pending_ = 0;
    }
    return rotation_;
  }

  int rotation() const { return rotation_; }

 private:
  // The rotation a reading asks for, or 0 when it is neither landscape pose.
  int pose_(float reading) const {
    if (std::isnan(reading))
      return 0;
    if (angle_between(reading, camera_right_) <= TOLERANCE)
      return ROTATION_CAMERA_RIGHT;
    if (angle_between(reading, camera_right_ + 180.0f) <= TOLERANCE)
      return ROTATION_CAMERA_LEFT;
    return 0;
  }

  static constexpr float TOLERANCE = 30.0f;
  float camera_right_;
  int rotation_;
  uint32_t settle_ms_;
  int pending_ = 0;
  uint32_t since_ = 0;
};

// The firmware's one instance (screen-flip.yaml). The first call fixes the calibration; it starts at
// the boot rotation (display_rotation, camera right) and needs a pose to hold 1 s before flipping.
// A function-local static, because ESPHome declares `globals:` before it includes this header.
inline ScreenFlip &screen_flip(float camera_right_reading) {
  static ScreenFlip flip(camera_right_reading, ROTATION_CAMERA_RIGHT, 1000);
  return flip;
}

// The HA select "Screen Rotation": 0 = Auto (follow the IMU), 1 = Camera right, 2 = Camera left.
// Any other index counts as Auto.
inline int screen_rotation_for(int lock_index, int auto_rotation) {
  if (lock_index == 1)
    return ROTATION_CAMERA_RIGHT;
  if (lock_index == 2)
    return ROTATION_CAMERA_LEFT;
  return auto_rotation;
}

}  // namespace chestnut_hw
