// Pure thermostat logic: no ESPHome includes, so it compiles on the host for unit tests.
#pragma once

enum class Mode { Off, Heat, Cool, Auto };

struct Setpoints {
  int effective_f;
  int low_f;
  int high_f;
};

namespace chestnut_detail {
inline int clamp_int(int v, int lo, int hi) { return v < lo ? lo : (v > hi ? hi : v); }
}  // namespace chestnut_detail

// Derives the climate's setpoints (whole degrees F) from the single Comfort target,
// the Eco offset and an optional hold. Heat and Off use a 2 degree band above the
// target, Cool uses a 2 degree band below it, Auto straddles it (widened by Eco).
inline Setpoints derive_setpoints(Mode mode, int comfort_f, int eco_offset_f, bool eco, bool hold, int hold_f) {
  using chestnut_detail::clamp_int;
  comfort_f = clamp_int(comfort_f, 50, 90);
  hold_f = clamp_int(hold_f, 50, 90);
  const int n = clamp_int(eco_offset_f, 2, 10);
  const int centre = hold ? hold_f : comfort_f;

  Setpoints s{};
  switch (mode) {
    case Mode::Cool:
      s.high_f = hold ? hold_f : comfort_f + (eco ? n : 0);
      s.low_f = s.high_f - 2;
      s.effective_f = s.high_f;
      break;
    case Mode::Auto: {
      const int widen = (!hold && eco) ? n : 0;
      s.low_f = centre - 1 - widen;
      s.high_f = centre + 1 + widen;
      s.effective_f = centre;
      break;
    }
    case Mode::Heat:
    case Mode::Off:
    default:
      s.low_f = hold ? hold_f : comfort_f - (eco ? n : 0);
      s.high_f = s.low_f + 2;
      s.effective_f = s.low_f;
      break;
  }
  return s;
}

inline float f_to_c(float f) { return (f - 32.0f) * 5.0f / 9.0f; }
inline float c_to_f(float c) { return c * 9.0f / 5.0f + 32.0f; }
