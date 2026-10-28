#include "check.h"
#include "chestnut_logic.h"

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
  return CHECK_SUMMARY("test_logic");
}
