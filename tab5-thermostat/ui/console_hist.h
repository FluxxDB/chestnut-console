// The history line's samples: a ring of room temperatures, oldest first. No ESPHome includes,
// so tools/preview/unit/test_hist.cpp builds it with plain g++.
#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <ctime>

namespace chestnut_ui {

// Adds reading t (skipped when NaN; returns whether it was added). A full ring drops its oldest
// sample. start is the epoch time of the oldest sample, or 0 while unknown: it's worked back from
// every sample taken with a set clock, so a clock set after boot (no Wi-Fi yet) still gets one,
// and it stays 0, never a time in 1970, while the clock has never been set.
template<size_t N>
bool hist_push(std::array<float, N> &h, int &n, time_t &start, float t, bool clock_valid, time_t now, int step_s) {
  if (std::isnan(t)) return false;
  if (n == (int) N) {
    std::rotate(h.begin(), h.begin() + 1, h.end());
    n--;
    if (start > 0) start += step_s;
  }
  h[n++] = t;
  if (clock_valid) start = now - (time_t) (n - 1) * step_s;
  return true;
}

}  // namespace chestnut_ui
