#include "check.h"
#include "chestnut_logic.h"

#include <cmath>
#include <cstdint>
#include <string>

using namespace chestnut;

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

// Spec default week: weekday 6:30 C, 8:30 E, 17:30 C, 22:30 E; weekend 8:00 C, 10:00 C, 17:00 C, 23:00 E.
static Week default_week() {
  Week w{};
  w.weekday[0] = {6 * 60 + 30, false};
  w.weekday[1] = {8 * 60 + 30, true};
  w.weekday[2] = {17 * 60 + 30, false};
  w.weekday[3] = {22 * 60 + 30, true};
  w.weekend[0] = {8 * 60, false};
  w.weekend[1] = {10 * 60, false};
  w.weekend[2] = {17 * 60, false};
  w.weekend[3] = {23 * 60, true};
  return w;
}

static void schedule_basic() {
  const Week w = default_week();
  auto s = schedule_at(w, 0, 9 * 60);  // Mon 9:00
  CHECK(s.period == 1 && s.eco);
  CHECK(s.key == 0 * 1440 + 8 * 60 + 30);
  CHECK(s.next_dow == 0 && s.next_min == 17 * 60 + 30);
  CHECK(std::string(period_name(s.period)) == "Leave");
}

static void schedule_midnight_carryover() {
  const Week w = default_week();
  auto night = schedule_at(w, 0, 23 * 60);  // Mon 23:00
  auto early = schedule_at(w, 1, 2 * 60);   // Tue 02:00
  CHECK(night.period == 3 && night.eco);
  CHECK(early.period == 3 && early.eco);
  CHECK(night.key == early.key);
  auto wake = schedule_at(w, 1, 6 * 60 + 30);  // Tue 06:30
  CHECK(wake.period == 0 && !wake.eco);
  CHECK(wake.key != early.key);
  CHECK(early.next_dow == 1 && early.next_min == 6 * 60 + 30);
}

static void schedule_weekend_boundary() {
  const Week w = default_week();
  auto fri = schedule_at(w, 4, 23 * 60);  // Fri 23:00
  CHECK(fri.period == 3 && fri.eco);
  CHECK(fri.next_dow == 5 && fri.next_min == 8 * 60);
  auto mon = schedule_at(w, 0, 5 * 60);  // Mon 05:00 -> Sunday's Sleep
  CHECK(mon.period == 3 && mon.eco);
  CHECK(mon.key == 6 * 1440 + 23 * 60);
  CHECK(mon.next_dow == 0 && mon.next_min == 6 * 60 + 30);
}

static void schedule_out_of_order_times() {
  Week w = default_week();
  w.weekday[1].start_min = 5 * 60;  // Leave before Wake
  auto a = schedule_at(w, 1, 5 * 60 + 30);
  CHECK(a.period == 1);
  auto b = schedule_at(w, 1, 7 * 60);
  CHECK(b.period == 0);
  auto c = schedule_at(w, 1, 9 * 60);
  CHECK(c.period == 0);
  auto d = schedule_at(w, 1, 17 * 60 + 30);
  CHECK(d.period == 2);
  CHECK(a.key != b.key && b.key != d.key && a.key != d.key);
  CHECK(b.key == c.key);
  CHECK(a.next_dow == 1 && a.next_min == 6 * 60 + 30);
}

static void schedule_edges() {
  const Week w = default_week();
  // Exactly at a start: that period is in force, next is strictly later.
  auto s = schedule_at(w, 2, 6 * 60 + 30);
  CHECK(s.period == 0 && s.next_dow == 2 && s.next_min == 8 * 60 + 30);
  // After the last start of Sunday: next is Monday's first.
  s = schedule_at(w, 6, 23 * 60 + 30);
  CHECK(s.period == 3 && s.next_dow == 0 && s.next_min == 6 * 60 + 30);
  // Out-of-range input does not crash.
  s = schedule_at(w, 9, 5000);
  CHECK(s.period >= 0 && s.period <= 3);
}

static void format_12h_cases() {
  CHECK(format_12h(0) == "12:00 am");
  CHECK(format_12h(390) == "6:30 am");
  CHECK(format_12h(720) == "12:00 pm");
  CHECK(format_12h(5) == "12:05 am");
  CHECK(format_12h(1350) == "10:30 pm");
  CHECK(format_12h(1439) == "11:59 pm");
}

// ---- Sanity checker -------------------------------------------------------------------
// Unit = 1000 ms: stale 2 s, frozen 30 s, recover 5 s, 2..40 C, spike 2 C.

static SanityConfig sanity_cfg() { return SanityConfig{2000, 30000, 5000, 2.0f, 40.0f, 2.0f}; }

// Feeds one reading per `period_ms` (and a tick in between) from `from` to `to` inclusive.
static void feed(SanityChecker &s, uint32_t from, uint32_t to, uint32_t period_ms, float c) {
  for (uint32_t t = from; (uint32_t)(t - from) <= (uint32_t)(to - from); t += period_ms) {
    s.on_reading(t, c);
    s.tick(t + period_ms / 2);
  }
}

static void sanity_nan_faults_immediately() {
  SanityChecker s(sanity_cfg());
  s.on_reading(0, 21.0f);
  CHECK(!s.fault());
  CHECK_NEAR(s.value(), 21.0, 1e-6);
  s.on_reading(100, NAN);
  CHECK(s.fault());
  CHECK(std::isnan(s.value()));
}

static void sanity_out_of_range() {
  SanityChecker s(sanity_cfg());
  s.on_reading(0, 21.0f);
  s.on_reading(100, 45.0f);
  CHECK(s.fault());
  CHECK(std::isnan(s.value()));
  SanityChecker lo(sanity_cfg());
  lo.on_reading(0, 1.9f);
  CHECK(lo.fault());
  // The limits themselves are fine.
  SanityChecker a(sanity_cfg()), b(sanity_cfg());
  a.on_reading(0, 2.0f);
  b.on_reading(0, 40.0f);
  CHECK(!a.fault() && !b.fault());
  CHECK_NEAR(a.value(), 2.0, 1e-6);
  CHECK_NEAR(b.value(), 40.0, 1e-6);
}

static void sanity_stale() {
  SanityChecker s(sanity_cfg());
  s.on_reading(0, 21.0f);
  s.tick(2000);
  CHECK(!s.fault());
  s.tick(2001);
  CHECK(s.fault());
  CHECK(std::isnan(s.value()));
}

static void sanity_startup() {
  SanityChecker s(sanity_cfg());
  CHECK(std::isnan(s.value()));
  CHECK(!s.fault());
  s.tick(5000);  // first call; the stale clock starts here
  s.tick(7000);
  CHECK(!s.fault());
  CHECK(std::isnan(s.value()));
  s.tick(7001);
  CHECK(s.fault());
  // A first reading in time means no fault at all.
  SanityChecker t(sanity_cfg());
  t.tick(0);
  t.on_reading(1500, 20.0f);
  t.tick(3000);
  CHECK(!t.fault());
  CHECK_NEAR(t.value(), 20.0, 1e-6);
  // A bad first reading faults at once.
  SanityChecker n(sanity_cfg());
  n.on_reading(0, NAN);
  CHECK(n.fault());
}

static void sanity_frozen() {
  SanityChecker s(sanity_cfg());
  for (uint32_t t = 0; t <= 30000; t += 500) {
    if (t % 1000 == 0) s.on_reading(t, 21.5f);
    s.tick(t);
  }
  CHECK(!s.fault());  // exactly frozen_ms: not yet
  s.tick(30001);
  CHECK(s.fault());
  CHECK(std::isnan(s.value()));

  // Tiny alternating noise is a live sensor.
  SanityChecker n(sanity_cfg());
  for (uint32_t t = 0; t <= 100000; t += 1000) {
    n.on_reading(t, (t / 1000) % 2 ? 21.5f : 21.51f);
    n.tick(t + 500);
    CHECK(!n.fault());
  }
}

static void sanity_spike_filtered() {
  SanityChecker s(sanity_cfg());
  s.on_reading(0, 21.0f);
  s.on_reading(1000, 31.0f);
  CHECK(!s.fault());
  CHECK_NEAR(s.value(), 21.0, 1e-6);
  s.on_reading(2000, 21.1f);
  CHECK(!s.fault());
  CHECK_NEAR(s.value(), 21.1, 1e-6);
  // A second, different spike replaces the first; the held one is dropped.
  SanityChecker d(sanity_cfg());
  d.on_reading(0, 21.0f);
  d.on_reading(1000, 31.0f);
  d.on_reading(2000, 40.0f);
  CHECK_NEAR(d.value(), 21.0, 1e-6);
  d.on_reading(3000, 21.2f);
  CHECK(!d.fault());
  CHECK_NEAR(d.value(), 21.2, 1e-6);
}

static void sanity_real_jump_accepted() {
  SanityChecker s(sanity_cfg());
  s.on_reading(0, 21.0f);
  s.on_reading(1000, 24.0f);
  CHECK_NEAR(s.value(), 21.0, 1e-6);  // held back for one more reading
  s.on_reading(2000, 24.1f);
  CHECK(!s.fault());
  CHECK_NEAR(s.value(), 24.1, 1e-6);
}

static void sanity_recovery_after_5_units() {
  SanityChecker s(sanity_cfg());
  s.on_reading(0, 21.0f);
  s.tick(2001);
  CHECK(s.fault());
  const uint32_t t = 2001;  // fault starts; the sensor comes back at once
  for (uint32_t d = 0; d < 5000; d += 250) {
    s.on_reading(t + d, 21.0f + 0.01f * (d / 250));
    s.tick(t + d);
  }
  s.tick(t + 4999);
  CHECK(s.fault());
  CHECK(std::isnan(s.value()));
  s.on_reading(t + 5000, 21.3f);
  s.tick(t + 5001);
  CHECK(!s.fault());
  CHECK_NEAR(s.value(), 21.3, 1e-6);
}

static void sanity_recovery_restarts_on_bad() {
  SanityChecker s(sanity_cfg());
  const uint32_t t = 10000;
  s.on_reading(t, NAN);
  CHECK(s.fault());
  for (uint32_t d = 250; d <= 3000; d += 250) s.on_reading(t + d, 21.0f + 0.01f * (d / 250));
  s.on_reading(t + 3250, NAN);  // bad again: the window starts over
  CHECK(s.fault());
  for (uint32_t d = 3500; d < 8500; d += 250) {
    s.on_reading(t + d, 21.0f + 0.01f * (d / 250));
    s.tick(t + d);
  }
  s.tick(t + 8499);
  CHECK(s.fault());  // would have cleared at t+5250 without the restart
  s.on_reading(t + 8500, 21.5f);
  s.tick(t + 8501);
  CHECK(!s.fault());
}

static void sanity_millis_wrap() {
  const uint32_t t0 = 0xFFFFF000u;
  // Healthy across the wrap, with noise so it is not frozen.
  SanityChecker s(sanity_cfg());
  for (uint32_t d = 0; d <= 20000; d += 1000) {
    s.on_reading(t0 + d, (d / 1000) % 2 ? 21.5f : 21.6f);
    s.tick(t0 + d + 500);
    CHECK(!s.fault());
  }
  // Stale across the wrap.
  SanityChecker st(sanity_cfg());
  st.on_reading(t0, 21.0f);
  st.tick(t0 + 2000);
  CHECK(!st.fault());
  st.tick(t0 + 2001);
  CHECK(st.fault());
  // Frozen across the wrap.
  SanityChecker fr(sanity_cfg());
  for (uint32_t d = 0; d <= 30000; d += 1000) {
    fr.on_reading(t0 + d, 21.5f);
    fr.tick(t0 + d);
  }
  CHECK(!fr.fault());
  fr.tick(t0 + 30001);
  CHECK(fr.fault());
  // Recovery across the wrap.
  SanityChecker rc(sanity_cfg());
  rc.on_reading(t0 + 3000, NAN);
  CHECK(rc.fault());
  for (uint32_t d = 3250; d < 8250; d += 250) {
    rc.on_reading(t0 + d, 21.0f + 0.01f * ((d / 250) % 5));
    rc.tick(t0 + d);
  }
  rc.tick(t0 + 8248);
  CHECK(rc.fault());
  rc.on_reading(t0 + 8250, 21.0f);
  rc.tick(t0 + 8251);
  CHECK(!rc.fault());
}

// ---- Sanity checker: rule interactions -------------------------------------------------

// Readings every `step` ms from `from` up to but not including `to`, alternating
// around `base` so the sensor never looks frozen. Ticks run at each reading.
static void feed_noisy(SanityChecker &s, uint32_t from, uint32_t to, uint32_t step, float base) {
  for (uint32_t t = from; (uint32_t)(t - from) < (uint32_t)(to - from); t += step) {
    s.on_reading(t, base + ((t / step) % 2 ? 0.05f : 0.0f));
    s.tick(t);
  }
}

// A held-back spike during recovery is not a good reading: the window restarts.
static void sanity_spike_during_recovery() {
  SanityChecker s(sanity_cfg());
  s.on_reading(0, 21.0f);
  s.on_reading(100, NAN);
  feed_noisy(s, 1000, 3000, 500, 21.0f);  // window starts at 1000
  s.on_reading(3000, 29.0f);              // spike vs the last accepted value: held, window restarts
  CHECK(s.fault());
  feed_noisy(s, 3500, 6000, 500, 21.1f);  // drops the spike; window restarts at 3500
  s.tick(6000);
  CHECK(s.fault());                       // the first window would have cleared at 6000
  feed_noisy(s, 6000, 8500, 500, 21.1f);
  s.tick(8499);
  CHECK(s.fault());
  s.on_reading(8500, 21.2f);
  s.tick(8500);
  CHECK(!s.fault());
}

// A stuck sensor stays faulted while its readings keep arriving, and recovers only after it moves.
static void sanity_frozen_holds_until_change() {
  SanityChecker s(sanity_cfg());
  feed(s, 0, 40000, 1000, 21.5f);
  CHECK(s.fault());
  feed(s, 41000, 80000, 1000, 21.5f);
  CHECK(s.fault());
  feed_noisy(s, 81000, 86000, 1000, 21.5f);  // it moved: the window starts at 81000 (the first value differs)
  s.tick(85999);
  CHECK(s.fault());
  s.on_reading(86000, 21.7f);
  s.tick(86000);
  CHECK(!s.fault());
  CHECK_NEAR(s.value(), 21.7, 1e-6);
}

// A gap between readings is caught by on_reading even without ticks, and the late reading
// does not clear the fault.
static void sanity_late_reading_after_gap() {
  SanityChecker s(sanity_cfg());
  s.on_reading(0, 21.0f);
  s.on_reading(10000, 21.0f);
  CHECK(s.fault());
  CHECK(std::isnan(s.value()));
}

// Stale during recovery restarts the window.
static void sanity_stale_during_recovery() {
  SanityChecker s(sanity_cfg());
  s.on_reading(0, NAN);
  s.on_reading(500, 21.0f);
  s.on_reading(1000, 21.1f);
  s.tick(3001);  // nothing since 1000: stale again
  CHECK(s.fault());
  feed_noisy(s, 3500, 8500, 500, 21.1f);  // window restarts at 3500
  s.tick(8499);
  CHECK(s.fault());
  s.on_reading(8500, 21.2f);
  s.tick(8500);
  CHECK(!s.fault());
}

// A bad reading between a held spike and the next reading drops the held one.
static void sanity_bad_drops_held_spike() {
  SanityChecker s(sanity_cfg());
  s.on_reading(0, 21.0f);
  s.on_reading(1000, 31.0f);  // held
  s.on_reading(2000, NAN);
  s.on_reading(3000, 31.1f);  // must not confirm the old held reading
  CHECK(s.fault());
  CHECK(std::isnan(s.value()));
  s.on_reading(4000, 31.2f);  // within spike of the new held reading: real change
  feed_noisy(s, 4500, 9000, 500, 31.2f);
  s.tick(8999);
  CHECK(s.fault());
  s.on_reading(9000, 31.3f);
  s.tick(9000);
  CHECK(!s.fault());
  CHECK_NEAR(s.value(), 31.3, 1e-6);
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
  schedule_basic();
  schedule_midnight_carryover();
  schedule_weekend_boundary();
  schedule_out_of_order_times();
  schedule_edges();
  format_12h_cases();
  sanity_nan_faults_immediately();
  sanity_out_of_range();
  sanity_stale();
  sanity_startup();
  sanity_frozen();
  sanity_spike_filtered();
  sanity_real_jump_accepted();
  sanity_recovery_after_5_units();
  sanity_recovery_restarts_on_bad();
  sanity_millis_wrap();
  sanity_spike_during_recovery();
  sanity_frozen_holds_until_change();
  sanity_late_reading_after_gap();
  sanity_stale_during_recovery();
  sanity_bad_drops_held_spike();
  return CHECK_SUMMARY("test_logic");
}
