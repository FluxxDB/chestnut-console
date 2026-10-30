// History ring tests (ui/console_hist.h): the samples, and the start time the history line's
// first label shows, including a clock that isn't set yet (no Wi-Fi at boot, so no SNTP).
#include <array>
#include <cmath>
#include <cstdio>

#include "console_hist.h"

static int fails = 0, total = 0;
#define CHECK(cond)                                                                \
  do {                                                                             \
    ++total;                                                                       \
    if (!(cond)) {                                                                 \
      ++fails;                                                                     \
      std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);         \
    }                                                                              \
  } while (0)

using chestnut_ui::hist_push;
constexpr int STEP = 600;
constexpr time_t T0 = 1793000000;  // Oct 2026

int main() {
  // Clock set throughout: start is the first sample's time, and moves on a step per roll.
  {
    std::array<float, 3> h{};
    int n = 0;
    time_t start = 0;
    CHECK(hist_push(h, n, start, 20, true, T0, STEP));
    CHECK(n == 1 && start == T0);
    hist_push(h, n, start, 21, true, T0 + STEP, STEP);
    hist_push(h, n, start, 22, true, T0 + 2 * STEP, STEP);
    CHECK(n == 3 && start == T0);
    hist_push(h, n, start, 23, true, T0 + 3 * STEP, STEP);
    CHECK(n == 3 && start == T0 + STEP);
    CHECK(h[0] == 21 && h[1] == 22 && h[2] == 23);
  }
  // Clock never set: no start time (the label stays blank), even once the ring is full and rolls.
  // A start of 0 + steps would show a time from 1970.
  {
    std::array<float, 3> h{};
    int n = 0;
    time_t start = 0;
    for (int i = 0; i < 5; i++) hist_push(h, n, start, 20, false, 0, STEP);
    CHECK(n == 3 && start == 0);
  }
  // Clock set after the first sample: start is worked back from the first sample with a set clock.
  {
    std::array<float, 3> h{};
    int n = 0;
    time_t start = 0;
    hist_push(h, n, start, 20, false, 0, STEP);
    hist_push(h, n, start, 21, true, T0, STEP);
    CHECK(n == 2 && start == T0 - STEP);
    hist_push(h, n, start, 22, true, T0 + STEP, STEP);
    hist_push(h, n, start, 23, true, T0 + 2 * STEP, STEP);
    CHECK(n == 3 && start == T0);
  }
  // Clock unreadable after being set: start keeps moving a step per roll.
  {
    std::array<float, 3> h{};
    int n = 0;
    time_t start = 0;
    for (int i = 0; i < 3; i++) hist_push(h, n, start, 20, true, T0 + i * STEP, STEP);
    hist_push(h, n, start, 21, false, 0, STEP);
    CHECK(n == 3 && start == T0 + STEP);
  }
  // No reading: nothing is recorded.
  {
    std::array<float, 3> h{};
    int n = 0;
    time_t start = 0;
    CHECK(!hist_push(h, n, start, NAN, true, T0, STEP));
    CHECK(n == 0 && start == 0);
  }

  if (fails) {
    std::fprintf(stderr, "FAIL: history ring, %d of %d checks failed\n", fails, total);
    return 1;
  }
  std::printf("PASS: history ring, %d checks\n", total);
  return 0;
}
