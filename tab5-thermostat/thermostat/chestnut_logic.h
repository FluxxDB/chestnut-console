// Pure thermostat logic: no ESPHome includes, so it compiles on the host for unit tests.
#pragma once

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <string>

namespace chestnut {

enum class Mode { Off, Heat, Cool, Auto };

struct Setpoints {
  int effective_f;
  int low_f;
  int high_f;
};

namespace detail {
inline int clamp_int(int v, int lo, int hi) { return v < lo ? lo : (v > hi ? hi : v); }
}  // namespace detail

// Derives the climate's setpoints (whole degrees F) from the single Comfort target,
// the Eco offset and an optional hold. Heat and Off use a 2 degree band above the
// target, Cool uses a 2 degree band below it, Auto straddles it (widened by Eco).
// The active heat target is never below 50 and the active cool target never above 90;
// the companion setpoint may fall outside 50-90 (Heat high up to 92, Cool low down to 48).
inline Setpoints derive_setpoints(Mode mode, int comfort_f, int eco_offset_f, bool eco, bool hold, int hold_f) {
  using detail::clamp_int;
  comfort_f = clamp_int(comfort_f, 50, 90);
  hold_f = clamp_int(hold_f, 50, 90);
  const int n = clamp_int(eco_offset_f, 2, 10);
  const int centre = hold ? hold_f : comfort_f;

  Setpoints s{};
  switch (mode) {
    case Mode::Cool:
      s.high_f = hold ? hold_f : comfort_f + (eco ? n : 0);
      if (s.high_f > 90) s.high_f = 90;  // the active cool target never exceeds 90
      s.low_f = s.high_f - 2;
      s.effective_f = s.high_f;
      break;
    case Mode::Auto: {
      const int widen = (!hold && eco) ? n : 0;
      s.low_f = centre - 1 - widen;
      s.high_f = centre + 1 + widen;
      s.effective_f = centre;
      // Keep the active targets in range and the band at least 2 wide.
      if (s.low_f < 50) {
        s.low_f = 50;
        if (s.high_f < 52) s.high_f = 52;
      }
      if (s.high_f > 90) {
        s.high_f = 90;
        if (s.low_f > 88) s.low_f = 88;
      }
      break;
    }
    case Mode::Heat:
    case Mode::Off:
    default:
      s.low_f = hold ? hold_f : comfort_f - (eco ? n : 0);
      if (s.low_f < 50) s.low_f = 50;  // the active heat target never drops below 50
      s.high_f = s.low_f + 2;
      s.effective_f = s.low_f;
      break;
  }
  return s;
}

inline float f_to_c(float f) { return (f - 32.0f) * 5.0f / 9.0f; }
inline float c_to_f(float c) { return c * 9.0f / 5.0f + 32.0f; }

// ---- Schedule -------------------------------------------------------------------------

// One schedule period: start minute of day (0-1439) and whether it runs at Eco.
struct Period {
  int start_min;
  bool eco;
};

// Index 0..3 = Wake, Leave, Return, Sleep. Mon-Fri use weekday, Sat-Sun use weekend.
struct Week {
  Period weekday[4];
  Period weekend[4];
};

// period: index of the period in force. key: start_dow*1440 + start_min of the occurrence
// in force, so it changes exactly when a new period instance starts. next_dow/next_min:
// the next start strictly after the queried minute.
struct ScheduleState {
  int period;
  bool eco;
  int key;
  int next_dow;
  int next_min;
};

namespace detail {
inline const Period *day_periods(const Week &w, int dow) { return dow >= 5 ? w.weekend : w.weekday; }

// The period of the day that starts last (ties: highest index). Always valid for 4 periods.
inline int last_starting(const Period *p) {
  int best = 0;
  for (int i = 1; i < 4; i++)
    if (p[i].start_min >= p[best].start_min) best = i;
  return best;
}
}  // namespace detail

// dow: 0=Mon..6=Sun. Within a day periods apply in start-time order, not index order.
// Before the day's first start, the previous day's last-starting period is still in force.
inline ScheduleState schedule_at(const Week &w, int dow, int minute) {
  using detail::clamp_int;
  using detail::day_periods;
  using detail::last_starting;
  dow = ((dow % 7) + 7) % 7;
  minute = clamp_int(minute, 0, 1439);

  ScheduleState s{};
  const Period *today = day_periods(w, dow);

  // Active: latest start <= minute today (ties: highest index), else yesterday's last start.
  int active = -1;
  for (int i = 0; i < 4; i++)
    if (today[i].start_min <= minute && (active < 0 || today[i].start_min >= today[active].start_min)) active = i;
  int start_dow = dow;
  if (active < 0) {
    start_dow = (dow + 6) % 7;
    active = last_starting(day_periods(w, start_dow));
    s.eco = day_periods(w, start_dow)[active].eco;
    s.key = start_dow * 1440 + day_periods(w, start_dow)[active].start_min;
  } else {
    s.eco = today[active].eco;
    s.key = dow * 1440 + today[active].start_min;
  }
  s.period = active;

  // Next: earliest start strictly after now, searching today and up to 7 days ahead.
  s.next_dow = dow;
  s.next_min = minute;
  for (int d = 0; d <= 7; d++) {
    const int nd = (dow + d) % 7;
    const Period *p = day_periods(w, nd);
    int best = -1;
    for (int i = 0; i < 4; i++) {
      if (d == 0 && p[i].start_min <= minute) continue;
      if (best < 0 || p[i].start_min < p[best].start_min) best = i;
    }
    if (best >= 0) {
      s.next_dow = nd;
      s.next_min = p[best].start_min;
      break;
    }
  }
  return s;
}

inline const char *period_name(int period) {
  switch (period) {
    case 0: return "Wake";
    case 1: return "Leave";
    case 2: return "Return";
    case 3: return "Sleep";
    default: return "";
  }
}

// 0 -> "12:00 am", 390 -> "6:30 am", 720 -> "12:00 pm", 1350 -> "10:30 pm".
inline std::string format_12h(int minute) {
  minute = detail::clamp_int(minute, 0, 1439);
  const int h = minute / 60;
  const int m = minute % 60;
  char buf[16];
  std::snprintf(buf, sizeof buf, "%d:%02d %s", h % 12 == 0 ? 12 : h % 12, m, h < 12 ? "am" : "pm");
  return std::string(buf);
}

// ---- Sensor sanity --------------------------------------------------------------------

// Times in ms, temperatures in C.
struct SanityConfig {
  uint32_t stale_ms;   // no reading for longer than this is bad
  uint32_t frozen_ms;  // the identical value for longer than this is bad
  uint32_t recover_ms; // continuous good readings needed to clear a fault
  float min_c;
  float max_c;
  float spike_c;       // a jump of more than this from the last accepted reading is held back
};

namespace detail {
// Wrap-safe time since `then` (uint32 ms, like ESPHome's millis()). A timestamp slightly
// ahead of `now` counts as zero elapsed rather than ~49 days.
inline uint32_t elapsed_ms(uint32_t now, uint32_t then) {
  const uint32_t d = now - then;
  return d > 0x7FFFFFFFu ? 0 : d;
}
}  // namespace detail

// Checks the room temperature before the thermostat sees it. Feed every reading to
// on_reading() and call tick() at least once a second; publish value() (NaN on a fault)
// as the thermostat's input and fault() as the problem sensor.
//
// Bad: NaN, outside [min, max], no reading for stale_ms, or the identical value for
// frozen_ms. A fault starts at the first bad condition and clears after recover_ms of
// continuous good readings; any bad condition restarts that window.
//
// Spike: a reading more than spike_c from the last accepted one is held back. If the next
// reading is within spike_c of the held one, both are accepted (a real change); otherwise
// the held one is dropped and the new reading is judged on its own. A spike is not a fault
// by itself, but while a fault is clearing a held-back reading is not a good reading, so
// it restarts the recovery window. A bad reading drops a held one.
//
// Startup: value() is NaN until the first accepted reading, but fault() stays false until
// stale_ms passes with no reading at all (the clock starts at the first call).
class SanityChecker {
 public:
  explicit SanityChecker(SanityConfig cfg) : cfg_(cfg) {}

  void on_reading(uint32_t now_ms, float c) {
    start(now_ms);
    // A gap since the previous reading is caught even if tick() was late.
    if (time_bad(now_ms)) mark_bad();
    last_rx_ms_ = now_ms;
    if (!std::isnan(c)) {
      if (!have_frozen_ || c != frozen_value_) {
        frozen_value_ = c;
        frozen_since_ms_ = now_ms;
        have_frozen_ = true;
      }
    }
    // Still frozen counts too: the identical value keeps arriving but is not good.
    if (std::isnan(c) || c < cfg_.min_c || c > cfg_.max_c || time_bad(now_ms)) {
      mark_bad();
      return;
    }
    const bool accepted = accept(c);
    if (fault_) {
      if (!accepted)
        good_valid_ = false;
      else if (!good_valid_) {
        good_since_ms_ = now_ms;
        good_valid_ = true;
      }
    }
    maybe_clear(now_ms);
  }

  void tick(uint32_t now_ms) {
    start(now_ms);
    if (time_bad(now_ms)) {
      mark_bad();
      return;
    }
    maybe_clear(now_ms);
  }

  bool fault() const { return fault_; }
  float value() const { return (fault_ || !have_value_) ? NAN : value_; }

 private:
  void start(uint32_t now_ms) {
    if (started_) return;
    started_ = true;
    last_rx_ms_ = now_ms;
  }

  bool time_bad(uint32_t now_ms) const {
    if (detail::elapsed_ms(now_ms, last_rx_ms_) > cfg_.stale_ms) return true;
    return have_frozen_ && detail::elapsed_ms(now_ms, frozen_since_ms_) > cfg_.frozen_ms;
  }

  void mark_bad() {
    fault_ = true;
    good_valid_ = false;
    held_ = false;
  }

  // Spike filter for an in-range reading. Returns false if the reading was held back.
  bool accept(float c) {
    if (have_value_ && held_ && std::fabs(c - held_value_) <= cfg_.spike_c) {
      held_ = false;  // a real change: both readings are accepted, c is the newest
      take(c);
      return true;
    }
    held_ = false;  // not confirmed: the held reading is dropped
    if (have_value_ && std::fabs(c - value_) > cfg_.spike_c) {
      held_ = true;
      held_value_ = c;
      return false;
    }
    take(c);
    return true;
  }

  void take(float c) {
    value_ = c;
    have_value_ = true;
  }

  void maybe_clear(uint32_t now_ms) {
    if (fault_ && good_valid_ && have_value_ && detail::elapsed_ms(now_ms, good_since_ms_) >= cfg_.recover_ms)
      fault_ = false;
  }

  SanityConfig cfg_;
  bool started_ = false;
  uint32_t last_rx_ms_ = 0;
  bool have_frozen_ = false;
  float frozen_value_ = 0;
  uint32_t frozen_since_ms_ = 0;
  bool have_value_ = false;
  float value_ = 0;
  bool held_ = false;
  float held_value_ = 0;
  bool fault_ = false;
  bool good_valid_ = false;
  uint32_t good_since_ms_ = 0;
};

}  // namespace chestnut
