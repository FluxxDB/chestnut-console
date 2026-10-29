#include "check.h"
#include "house_model.h"

#include <cmath>

using namespace chestnut;

// Run `seconds` of simulation in steps of `step_s`.
static float run(float t, float out, bool w, bool y, int seconds, float step_s, const HouseParams &p) {
  for (int i = 0; i < (int) (seconds / step_s); i++) t = house_step(t, out, w, y, step_s, p);
  return t;
}

static void house_drifts_toward_outdoor() {
  HouseParams p;
  float t = run(68.0f, 30.0f, false, false, 3600, 1.0f, p);
  CHECK(t > 63.0f && t < 64.5f);
}

// With heat on, the drift term pulls back toward outdoor as the room warms, so the
// analytic result is 68 + (heat*tau)(1 - e^(-1/tau)) = 77.4 (not the drift-free 78).
static void house_heats() {
  HouseParams p;
  float t = run(68.0f, 68.0f, true, false, 3600, 1.0f, p);
  CHECK_NEAR(t, 77.4, 0.2);
  CHECK(t > 68.0f);
}

// Analytic: 78 - (cool*tau)(1 - e^(-1/tau)) = 73.3.
static void house_cools() {
  HouseParams p;
  float t = run(78.0f, 78.0f, false, true, 3600, 1.0f, p);
  CHECK_NEAR(t, 73.3, 0.2);
  CHECK(t < 78.0f);
}

static void house_fan_only_no_effect() {
  // G is not an input to house_step; with W and Y both off the room just drifts.
  HouseParams p;
  float t = run(72.0f, 72.0f, false, false, 3600, 1.0f, p);
  CHECK_NEAR(t, 72.0, 0.001);
}

static void house_large_step_is_stable() {
  HouseParams p;
  // 600 s steps (sim_speed 600) must agree with 1 s steps.
  float fine = run(68.0f, 30.0f, false, false, 3600, 1.0f, p);
  float coarse = run(68.0f, 30.0f, false, false, 3600, 600.0f, p);
  CHECK_NEAR(fine, coarse, 0.05);
  // A step far longer than tau must settle at outdoor, never past it.
  float t = house_step(68.0f, 30.0f, false, false, 1000000.0f, p);
  CHECK(t >= 30.0f && t <= 30.001f);
  float up = house_step(20.0f, 50.0f, false, false, 1000000.0f, p);
  CHECK(up <= 50.0f && up >= 49.999f);
  // Heating with a huge step converges to the equilibrium outdoor + heat*tau.
  float h = house_step(68.0f, 30.0f, true, false, 1000000.0f, p);
  CHECK_NEAR(h, 30.0 + 80.0, 0.01);
}

static void house_degenerate_inputs() {
  HouseParams p;
  CHECK(house_step(68.0f, 30.0f, false, false, 0.0f, p) == 68.0f);
  CHECK(house_step(68.0f, 30.0f, false, false, -5.0f, p) == 68.0f);
  HouseParams z;
  z.tau_h = 0.0f;
  CHECK_NEAR(house_step(68.0f, 30.0f, false, false, 1.0f, z), 30.0, 0.001);
}

static void weather_fixed() {
  CHECK(weather_outdoor_f(Weather::Fixed, 42.0f, 0) == 42.0f);
  CHECK(weather_outdoor_f(Weather::Fixed, 42.0f, 900) == 42.0f);
}

static void weather_winter_extremes() {
  CHECK_NEAR(weather_outdoor_f(Weather::Winter, 0, 300), 25.0, 0.01);
  CHECK_NEAR(weather_outdoor_f(Weather::Winter, 0, 900), 45.0, 0.01);
  CHECK_NEAR(weather_outdoor_f(Weather::Winter, 0, 600), 35.0, 0.01);  // midpoint
}

static void weather_summer_extremes() {
  CHECK_NEAR(weather_outdoor_f(Weather::Summer, 0, 300), 70.0, 0.01);
  CHECK_NEAR(weather_outdoor_f(Weather::Summer, 0, 900), 95.0, 0.01);
}

static void weather_wraps_midnight() {
  // 24 h periodic: minute 1440 + 300 behaves like 300; negatives wrap too.
  CHECK_NEAR(weather_outdoor_f(Weather::Winter, 0, 1440 + 300), 25.0, 0.01);
  CHECK_NEAR(weather_outdoor_f(Weather::Winter, 0, -1440 + 900), 45.0, 0.01);
  float m = weather_outdoor_f(Weather::Winter, 0, 0);
  CHECK(m > 25.0f && m < 45.0f);
}

int main() {
  house_drifts_toward_outdoor();
  house_heats();
  house_cools();
  house_fan_only_no_effect();
  house_large_step_is_stable();
  house_degenerate_inputs();
  weather_fixed();
  weather_winter_extremes();
  weather_summer_extremes();
  weather_wraps_midnight();
  return CHECK_SUMMARY("test_house");
}
