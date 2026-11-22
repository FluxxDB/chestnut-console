// Screen flip tests (tab5-thermostat/hardware/screen_flip.h): the IMU's orientation reading
// (ESPHome's motion "orientation" sensor: 0/90/180/270, NAN when lying flat) turned into one of the
// two landscape screen rotations, after the pose has held for a settle time.
#include <cmath>
#include <cstdint>
#include <cstdio>

#include "screen_flip.h"

static int fails = 0, total = 0;
#define CHECK(cond)                                                                \
  do {                                                                             \
    ++total;                                                                       \
    if (!(cond)) {                                                                 \
      ++fails;                                                                     \
      std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);         \
    }                                                                              \
  } while (0)

using chestnut_hw::ScreenFlip;
using chestnut_hw::screen_rotation_for;

// Camera on the right reads 90 here; the screen then needs 270. Opposite pose reads 270 -> 90.
static ScreenFlip make(int start = 270) { return ScreenFlip(90.0f, start, 1000); }

static void starts_at_the_boot_rotation() {
  CHECK(make(270).rotation() == 270);
  CHECK(make(90).rotation() == 90);
}

static void lying_flat_keeps_the_rotation() {
  auto f = make(270);
  for (uint32_t t = 0; t <= 5000; t += 250)
    CHECK(f.step(NAN, t) == 270);
}

static void same_pose_keeps_the_rotation() {
  auto f = make(270);
  for (uint32_t t = 0; t <= 5000; t += 250)
    CHECK(f.step(90.0f, t) == 270);
}

static void opposite_pose_flips_after_the_settle_time() {
  auto f = make(270);
  CHECK(f.step(270.0f, 0) == 270);
  CHECK(f.step(270.0f, 500) == 270);
  CHECK(f.step(270.0f, 999) == 270);
  CHECK(f.step(270.0f, 1000) == 90);
  CHECK(f.rotation() == 90);
}

static void flips_back() {
  auto f = make(270);
  f.step(270.0f, 0);
  f.step(270.0f, 1000);
  CHECK(f.rotation() == 90);
  CHECK(f.step(90.0f, 2000) == 90);
  CHECK(f.step(90.0f, 3000) == 270);
}

static void a_brief_turn_does_not_flip() {
  auto f = make(270);
  f.step(270.0f, 0);
  f.step(270.0f, 800);
  CHECK(f.step(90.0f, 900) == 270);    // back before the settle time: the pending flip is dropped
  CHECK(f.step(270.0f, 1000) == 270);  // a new pending flip starts here, not at 0
  CHECK(f.step(270.0f, 1999) == 270);
  CHECK(f.step(270.0f, 2000) == 90);
}

static void portrait_keeps_the_rotation_and_drops_a_pending_flip() {
  auto f = make(270);
  f.step(270.0f, 0);
  CHECK(f.step(0.0f, 600) == 270);
  CHECK(f.step(180.0f, 2000) == 270);
  CHECK(f.step(270.0f, 2100) == 270);  // pending restarts at 2100
  CHECK(f.step(270.0f, 3099) == 270);
  CHECK(f.step(270.0f, 3100) == 90);
}

static void lying_flat_drops_a_pending_flip() {
  auto f = make(270);
  f.step(270.0f, 0);
  CHECK(f.step(NAN, 700) == 270);
  CHECK(f.step(270.0f, 800) == 270);
  CHECK(f.step(270.0f, 1799) == 270);
  CHECK(f.step(270.0f, 1800) == 90);
}

static void booted_upside_down_corrects_itself() {
  auto f = make(90);  // boot rotation 90 while the Tab5 actually hangs camera-right
  CHECK(f.step(90.0f, 0) == 90);
  CHECK(f.step(90.0f, 1000) == 270);
}

static void other_calibrations() {
  ScreenFlip f(270.0f, 270, 1000);  // camera-right reads 270, so 90 is the opposite pose
  f.step(90.0f, 0);
  CHECK(f.step(90.0f, 1000) == 90);
  ScreenFlip g(0.0f, 270, 1000);     // camera-right reads 0, opposite reads 180
  g.step(180.0f, 0);
  CHECK(g.step(180.0f, 1000) == 90);
  g.step(0.0f, 2000);
  CHECK(g.step(0.0f, 3000) == 270);
  CHECK(g.step(360.0f, 4000) == 270);  // 360 is the same pose as 0
}

static void unsnapped_angles_near_a_pose_count_as_that_pose() {
  auto f = make(270);
  f.step(262.0f, 0);
  CHECK(f.step(281.0f, 1000) == 90);   // within 30 degrees of 270
  auto g = make(270);
  g.step(225.0f, 0);
  CHECK(g.step(225.0f, 5000) == 270);  // 45 degrees off: neither pose, keep
}

static void survives_millis_wraparound() {
  auto f = make(270);
  const uint32_t t0 = 0xFFFFFF00u;
  f.step(270.0f, t0);
  CHECK(f.step(270.0f, t0 + 500) == 270);
  CHECK(f.step(270.0f, t0 + 1000) == 90);  // t0 + 1000 wraps past zero
}

// The HA lock (select "Screen Rotation"): 0 = Auto, 1 = Camera right, 2 = Camera left.
static void lock_auto_follows_the_imu() {
  CHECK(screen_rotation_for(0, 270) == 270);
  CHECK(screen_rotation_for(0, 90) == 90);
}

static void lock_pins_the_rotation() {
  CHECK(screen_rotation_for(1, 90) == 270);
  CHECK(screen_rotation_for(1, 270) == 270);
  CHECK(screen_rotation_for(2, 270) == 90);
  CHECK(screen_rotation_for(2, 90) == 90);
}

static void unknown_lock_index_means_auto() {
  CHECK(screen_rotation_for(-1, 90) == 90);
  CHECK(screen_rotation_for(7, 270) == 270);
}

// The firmware's instance (screen-flip.yaml): created on the first call, which fixes the calibration;
// it starts at the boot rotation (camera right) and settles in 1 s.
static void the_firmware_instance_is_created_once() {
  auto &a = chestnut_hw::screen_flip(90.0f);
  auto &b = chestnut_hw::screen_flip(0.0f);
  CHECK(&a == &b);
  CHECK(a.rotation() == 270);
  a.step(270.0f, 0);
  CHECK(a.step(270.0f, 999) == 270);
  CHECK(a.step(270.0f, 1000) == 90);
}

int main() {
  the_firmware_instance_is_created_once();
  lock_auto_follows_the_imu();
  lock_pins_the_rotation();
  unknown_lock_index_means_auto();
  starts_at_the_boot_rotation();
  lying_flat_keeps_the_rotation();
  same_pose_keeps_the_rotation();
  opposite_pose_flips_after_the_settle_time();
  flips_back();
  a_brief_turn_does_not_flip();
  portrait_keeps_the_rotation_and_drops_a_pending_flip();
  lying_flat_drops_a_pending_flip();
  booted_upside_down_corrects_itself();
  other_calibrations();
  unsnapped_angles_near_a_pose_count_as_that_pose();
  survives_millis_wraparound();
  if (fails) {
    std::fprintf(stderr, "screen_flip: %d of %d checks FAILED\n", fails, total);
    return 1;
  }
  std::printf("screen_flip: %d checks passed\n", total);
  return 0;
}
