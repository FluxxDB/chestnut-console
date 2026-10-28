// Minimal CHECK macros for the host-side unit tests. No dependencies.
#pragma once
#include <cmath>
#include <cstdio>

namespace check {
inline int &failures() { static int n = 0; return n; }
inline int &total() { static int n = 0; return n; }
}  // namespace check

#define CHECK(cond)                                                          \
  do {                                                                       \
    ++check::total();                                                        \
    if (!(cond)) {                                                           \
      ++check::failures();                                                   \
      std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);   \
    }                                                                        \
  } while (0)

#define CHECK_NEAR(a, b, tol) CHECK(std::fabs((double) (a) - (double) (b)) <= (double) (tol))

// Print the summary and return the process exit code.
#define CHECK_SUMMARY(name)                                                  \
  (check::failures() == 0                                                    \
       ? (std::printf("%s: %d checks passed\n", name, check::total()), 0)    \
       : (std::fprintf(stderr, "%s: %d of %d checks FAILED\n", name,         \
                       check::failures(), check::total()), 1))
