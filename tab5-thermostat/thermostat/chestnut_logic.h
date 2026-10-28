// Pure thermostat logic: no ESPHome includes, so it compiles on the host for unit tests.
#pragma once

#include <cstdio>
#include <string>

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
// The active heat target is never below 50 and the active cool target never above 90;
// the companion setpoint may fall outside 50-90 (Heat high up to 92, Cool low down to 48).
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

namespace chestnut_detail {
inline const Period *day_periods(const Week &w, int dow) { return dow >= 5 ? w.weekend : w.weekday; }

// The period of the day that starts last (ties: highest index). Always valid for 4 periods.
inline int last_starting(const Period *p) {
  int best = 0;
  for (int i = 1; i < 4; i++)
    if (p[i].start_min >= p[best].start_min) best = i;
  return best;
}
}  // namespace chestnut_detail

// dow: 0=Mon..6=Sun. Within a day periods apply in start-time order, not index order.
// Before the day's first start, the previous day's last-starting period is still in force.
inline ScheduleState schedule_at(const Week &w, int dow, int minute) {
  using chestnut_detail::clamp_int;
  using chestnut_detail::day_periods;
  using chestnut_detail::last_starting;
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
  minute = chestnut_detail::clamp_int(minute, 0, 1439);
  const int h = minute / 60;
  const int m = minute % 60;
  char buf[16];
  std::snprintf(buf, sizeof buf, "%d:%02d %s", h % 12 == 0 ? 12 : h % 12, m, h < 12 ? "am" : "pm");
  return std::string(buf);
}
