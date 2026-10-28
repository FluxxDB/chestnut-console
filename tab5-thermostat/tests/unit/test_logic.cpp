#include "check.h"
#include "chestnut_logic.h"

static void derive_heat_comfort() {
  auto s = derive_setpoints(Mode::Heat, 72, 4, false, false, 0);
  CHECK(s.effective_f == 72 && s.low_f == 72 && s.high_f == 74);
}

static void derive_heat_eco() {
  auto s = derive_setpoints(Mode::Heat, 72, 4, true, false, 0);
  CHECK(s.effective_f == 68 && s.low_f == 68 && s.high_f == 70);
}

static void derive_cool_eco() {
  auto s = derive_setpoints(Mode::Cool, 72, 4, true, false, 0);
  CHECK(s.effective_f == 76 && s.high_f == 76 && s.low_f == 74);
}

static void derive_auto() {
  auto s = derive_setpoints(Mode::Auto, 72, 4, false, false, 0);
  CHECK(s.low_f == 71 && s.high_f == 73 && s.effective_f == 72);
}

static void derive_auto_eco() {
  auto s = derive_setpoints(Mode::Auto, 72, 4, true, false, 0);
  CHECK(s.low_f == 67 && s.high_f == 77 && s.effective_f == 72);
}

static void derive_hold_overrides_eco_heat() {
  auto s = derive_setpoints(Mode::Heat, 72, 4, true, true, 69);
  CHECK(s.effective_f == 69 && s.low_f == 69);
}

static void derive_hold_auto_no_widen() {
  auto s = derive_setpoints(Mode::Auto, 72, 4, true, true, 69);
  CHECK(s.low_f == 68 && s.high_f == 70 && s.effective_f == 69);
}

static void derive_clamps() {
  auto s = derive_setpoints(Mode::Heat, 95, 20, false, false, 0);
  CHECK(s.effective_f == 90);
}

static void derive_eco_offset_clamps() {
  auto s = derive_setpoints(Mode::Heat, 72, 1, true, false, 0);
  CHECK(s.low_f == 70);
  s = derive_setpoints(Mode::Heat, 72, 20, true, false, 0);
  CHECK(s.low_f == 62);
  s = derive_setpoints(Mode::Cool, 72, 20, true, false, 0);
  CHECK(s.high_f == 82 && s.low_f == 80);
  s = derive_setpoints(Mode::Auto, 72, 1, true, false, 0);
  CHECK(s.low_f == 69 && s.high_f == 75);
}

static void derive_input_clamps() {
  auto s = derive_setpoints(Mode::Heat, 40, 4, false, false, 0);
  CHECK(s.effective_f == 50);
  s = derive_setpoints(Mode::Heat, 72, 4, false, true, 95);
  CHECK(s.low_f == 90 && s.high_f == 92);
  s = derive_setpoints(Mode::Heat, 72, 4, false, true, 0);
  CHECK(s.low_f == 50);
}

static void derive_off_matches_heat() {
  auto s = derive_setpoints(Mode::Off, 72, 4, true, false, 0);
  CHECK(s.effective_f == 68 && s.low_f == 68 && s.high_f == 70);
}

static void derive_output_clamps() {
  auto s = derive_setpoints(Mode::Heat, 50, 10, true, false, 0);
  CHECK(s.low_f == 50 && s.effective_f == 50 && s.high_f == 52);
  s = derive_setpoints(Mode::Cool, 90, 10, true, false, 0);
  CHECK(s.high_f == 90 && s.effective_f == 90 && s.low_f == 88);
  s = derive_setpoints(Mode::Auto, 50, 10, true, false, 0);
  CHECK(s.low_f == 50 && s.high_f == 61 && s.high_f - s.low_f >= 2 && s.effective_f == 50);
  s = derive_setpoints(Mode::Auto, 90, 10, true, false, 0);
  CHECK(s.high_f == 90 && s.low_f == 79 && s.high_f - s.low_f >= 2 && s.effective_f == 90);
}

static void conversions() {
  CHECK_NEAR(f_to_c(72), 22.2222f, 1e-3);
  CHECK_NEAR(c_to_f(20), 68.0f, 1e-3);
}

int main() {
  derive_heat_comfort();
  derive_heat_eco();
  derive_cool_eco();
  derive_auto();
  derive_auto_eco();
  derive_hold_overrides_eco_heat();
  derive_hold_auto_no_widen();
  derive_clamps();
  derive_eco_offset_clamps();
  derive_input_clamps();
  derive_off_matches_heat();
  derive_output_clamps();
  conversions();
  return CHECK_SUMMARY("test_logic");
}
