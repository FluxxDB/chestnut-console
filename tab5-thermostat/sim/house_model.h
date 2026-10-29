// Virtual house for the simulated thermostat (milestone 2). Pure C++17, header-only,
// no ESPHome includes, so the host-side unit tests can compile it directly.
#pragma once
#include <cmath>

namespace chestnut {

struct HouseParams {
  float tau_h = 8;      // thermal time constant of the house, hours
  float heat_fph = 10;  // degF per hour added while W (heat) is on
  float cool_fph = 5;   // degF per hour removed while Y (cool) is on
};

// Advance the room temperature by dt_s seconds of
//   dT/dt = (Tout - T)/tau + heat*W - cool*Y        (per hour)
// G (fan) has no thermal effect, so it is not an input.
//
// The equation is linear with constant inputs over a step, so instead of a plain Euler
// step (which overshoots when dt >= tau, and the sim can pass dt = 600 s or more) we use
// its exact solution:  T' = Teq + (T - Teq) * exp(-dt/tau),  Teq = Tout + tau*(heat*W - cool*Y).
// For small dt this equals the Euler step to first order; for any dt it moves monotonically
// toward Teq and never passes it, so drift alone can never overshoot the outdoor temperature.
inline float house_step(float room_f, float outdoor_f, bool w, bool y, float dt_s, const HouseParams &p) {
  if (!(dt_s > 0.0f)) return room_f;
  float drive = (w ? p.heat_fph : 0.0f) - (y ? p.cool_fph : 0.0f);
  if (!(p.tau_h > 0.0f)) return outdoor_f;  // no thermal mass: instantly at outdoor (drive has no meaning)
  float teq = outdoor_f + p.tau_h * drive;
  float dt_h = dt_s / 3600.0f;
  return teq + (room_f - teq) * std::exp(-dt_h / p.tau_h);
}

enum class Weather { Fixed, Winter, Summer };

// Outdoor temperature (degF) at a local minute of day. Fixed returns fixed_f. Winter and
// Summer are a daily cosine-shaped curve: minimum at 05:00, maximum at 15:00 (winter 25..45, summer 70..95).
// The curve is 24 h periodic, so any integer minute (including negative) is accepted.
inline float weather_outdoor_f(Weather kind, float fixed_f, int minute_of_day) {
  float lo, hi;
  switch (kind) {
    case Weather::Winter: lo = 25.0f; hi = 45.0f; break;
    case Weather::Summer: lo = 70.0f; hi = 95.0f; break;
    default: return fixed_f;
  }
  int m = ((minute_of_day % 1440) + 1440) % 1440;
  // Min at 05:00 and max at 15:00 are 10 h apart one way and 14 h the other, so a single
  // cosine can't hit both; use a half-cosine for each leg (rising 10 h, falling 14 h).
  const float kPi = 3.14159265358979f;
  float rise_start = 300.0f, peak = 900.0f;
  float x = (float) m;
  float frac;  // 0 at min, 1 at max
  if (x >= rise_start && x <= peak) {
    frac = 0.5f * (1.0f - std::cos(kPi * (x - rise_start) / (peak - rise_start)));
  } else {
    float since_peak = x >= peak ? x - peak : x + 1440.0f - peak;  // 0..840
    frac = 0.5f * (1.0f + std::cos(kPi * since_peak / (1440.0f - (peak - rise_start))));
  }
  return lo + (hi - lo) * frac;
}

}  // namespace chestnut
