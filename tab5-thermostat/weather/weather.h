// The outside reading on the wall screen: Open-Meteo's current weather, polled by the Tab5 itself.
// Pure C++17 (no ESPHome, no ESP-IDF), so tests/unit/test_weather.cpp checks every rule with g++:
// reading the reply, the weather code in words and as an icon, and when to poll.
// open-meteo.yaml does the fetching (fetch_idf.h) and publishes the result.
#pragma once

#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <string>

namespace chestnut_weather {

// ── Icons: Material Design Icons 7.4.47 (ui/fonts.yaml's f_icon must carry every one) ──
inline constexpr const char *ICON_SUNNY = "\U000F0599";         // weather-sunny
inline constexpr const char *ICON_NIGHT = "\U000F0594";         // weather-night
inline constexpr const char *ICON_PARTLY = "\U000F0595";        // weather-partly-cloudy
inline constexpr const char *ICON_NIGHT_PARTLY = "\U000F0F31";  // weather-night-partly-cloudy
inline constexpr const char *ICON_CLOUDY = "\U000F0590";        // weather-cloudy
inline constexpr const char *ICON_FOG = "\U000F0591";           // weather-fog
inline constexpr const char *ICON_RAIN = "\U000F0597";          // weather-rainy
inline constexpr const char *ICON_POURING = "\U000F0596";       // weather-pouring
inline constexpr const char *ICON_SLEET = "\U000F067F";         // weather-snowy-rainy
inline constexpr const char *ICON_SNOW = "\U000F0598";          // weather-snowy
inline constexpr const char *ICON_HEAVY_SNOW = "\U000F0F36";    // weather-snowy-heavy
inline constexpr const char *ICON_STORM = "\U000F067E";         // weather-lightning-rainy
inline constexpr const char *ICON_HAIL = "\U000F0592";          // weather-hail
// No reading, or a weather code we don't know: the card's original cloud.
inline constexpr const char *ICON_DEFAULT = ICON_CLOUDY;
inline constexpr const char *ALL_ICONS[] = {ICON_SUNNY, ICON_NIGHT, ICON_PARTLY, ICON_NIGHT_PARTLY, ICON_CLOUDY,
                                            ICON_FOG,   ICON_RAIN,  ICON_POURING, ICON_SLEET,       ICON_SNOW,
                                            ICON_HEAVY_SNOW, ICON_STORM, ICON_HAIL};

// ── WMO weather codes (Open-Meteo's weather_code) ──
// In words, short enough for the card (test_wall.sh measures them all). "" for a code that isn't in
// the WMO list Open-Meteo uses.
inline const char *condition_text(int code) {
  switch (code) {
    case 0: return "Clear";
    case 1: return "Mostly clear";
    case 2: return "Partly cloudy";
    case 3: return "Cloudy";
    case 45: case 48: return "Fog";
    case 51: case 53: case 55: return "Drizzle";
    case 56: case 57: return "Icy drizzle";
    case 61: return "Light rain";
    case 63: return "Rain";
    case 65: return "Heavy rain";
    case 66: case 67: return "Freezing rain";
    case 71: return "Light snow";
    case 73: return "Snow";
    case 75: return "Heavy snow";
    case 77: return "Snow grains";
    case 80: case 81: return "Showers";
    case 82: return "Heavy showers";
    case 85: case 86: return "Snow showers";
    case 95: return "Thunderstorms";
    case 96: case 99: return "Hailstorms";
    default: return "";
  }
}

inline const char *icon_for(int code, bool is_day) {
  switch (code) {
    case 0: return is_day ? ICON_SUNNY : ICON_NIGHT;
    case 1: case 2: return is_day ? ICON_PARTLY : ICON_NIGHT_PARTLY;
    case 3: return ICON_CLOUDY;
    case 45: case 48: return ICON_FOG;
    case 51: case 53: case 55: case 61: case 63: case 80: case 81: return ICON_RAIN;
    case 65: case 82: return ICON_POURING;
    case 56: case 57: case 66: case 67: return ICON_SLEET;
    case 71: case 73: case 77: case 85: case 86: return ICON_SNOW;
    case 75: return ICON_HEAVY_SNOW;
    case 95: return ICON_STORM;
    case 96: case 99: return ICON_HAIL;
    default: return ICON_DEFAULT;
  }
}

// ── The request and the reply ──
inline std::string forecast_url(const std::string &base, const std::string &lat, const std::string &lon) {
  return base + "?latitude=" + lat + "&longitude=" + lon +
         "&current=temperature_2m,weather_code,is_day&temperature_unit=fahrenheit&timezone=GMT&forecast_days=1";
}

// Outside air anywhere people live; a value past this is a broken reply, not weather.
inline bool plausible_f(float t) { return std::isfinite(t) && t >= -80.0f && t <= 140.0f; }

struct Reading {
  bool ok = false;     // a usable reading: temp_f is valid
  float temp_f = NAN;
  int code = -1;       // WMO weather code, -1 if the reply had none
  bool is_day = true;
};

namespace detail {
// A small reader for Open-Meteo's reply: walks JSON objects member by member and skips values it
// doesn't need. Not a general parser: it checks only what the reading depends on. Every function
// returns std::string::npos on anything malformed or cut off.
constexpr size_t NPOS = std::string::npos;

inline size_t ws(const std::string &s, size_t i) {
  while (i < s.size() && (s[i] == ' ' || s[i] == '\n' || s[i] == '\r' || s[i] == '\t')) i++;
  return i;
}

// s[i] is the opening quote; returns the index after the closing one.
inline size_t skip_string(const std::string &s, size_t i) {
  for (i++; i < s.size(); i++) {
    if (s[i] == '\\') i++;
    else if (s[i] == '"') return i + 1;
  }
  return NPOS;
}

// Any JSON value starting at s[i] (after whitespace); returns the index after it.
inline size_t skip_value(const std::string &s, size_t i) {
  i = ws(s, i);
  if (i >= s.size()) return NPOS;
  const char c = s[i];
  if (c == '"') return skip_string(s, i);
  if (c == '{' || c == '[') {
    const char close = c == '{' ? '}' : ']';
    i = ws(s, i + 1);
    if (i < s.size() && s[i] == close) return i + 1;
    while (true) {
      if (c == '{') {
        if (i >= s.size() || s[i] != '"') return NPOS;
        i = ws(s, skip_string(s, i));
        if (i == NPOS || i >= s.size() || s[i] != ':') return NPOS;
        i++;
      }
      i = skip_value(s, i);
      if (i == NPOS) return NPOS;
      i = ws(s, i);
      if (i >= s.size()) return NPOS;
      if (s[i] == close) return i + 1;
      if (s[i] != ',') return NPOS;
      i = ws(s, i + 1);
    }
  }
  // A number or true / false / null: up to the next delimiter. One the input ends inside may be cut
  // short ("-12.5" sent, "-1" received), so it doesn't count.
  const size_t start = i;
  while (i < s.size() && s[i] != ',' && s[i] != '}' && s[i] != ']' && s[i] != ' ' && s[i] != '\n' &&
         s[i] != '\r' && s[i] != '\t')
    i++;
  return i > start && i < s.size() ? i : NPOS;
}

// The start of member `key`'s value in the object at s[obj] ('{'), or NPOS. Only that object's own
// members are looked at, not nested ones.
inline size_t member(const std::string &s, size_t obj, const char *key) {
  if (obj == NPOS || obj >= s.size() || s[obj] != '{') return NPOS;
  const std::string want = std::string("\"") + key + "\"";
  size_t i = ws(s, obj + 1);
  if (i < s.size() && s[i] == '}') return NPOS;
  while (i < s.size() && s[i] == '"') {
    const size_t key_end = skip_string(s, i);
    if (key_end == NPOS) return NPOS;
    const bool hit = s.compare(i, key_end - i, want) == 0;
    i = ws(s, key_end);
    if (i >= s.size() || s[i] != ':') return NPOS;
    i = ws(s, i + 1);
    if (hit) return i < s.size() ? i : NPOS;
    i = skip_value(s, i);
    if (i == NPOS) return NPOS;
    i = ws(s, i);
    if (i >= s.size() || s[i] != ',') return NPOS;  // '}' : not found
    i = ws(s, i + 1);
  }
  return NPOS;
}

// A JSON number at s[i]; false for anything else (null, a string, garbage).
inline bool number_at(const std::string &s, size_t i, double *out) {
  if (i == NPOS || i >= s.size() || !(s[i] == '-' || (s[i] >= '0' && s[i] <= '9'))) return false;
  const size_t end = skip_value(s, i);
  if (end == NPOS) return false;
  const std::string text = s.substr(i, end - i);
  char *stop = nullptr;
  const double v = std::strtod(text.c_str(), &stop);
  if (stop != text.c_str() + text.size() || !std::isfinite(v)) return false;
  *out = v;
  return true;
}

// The raw text of a JSON string at s[i] (escapes left as they are).
inline bool string_at(const std::string &s, size_t i, std::string *out) {
  if (i == NPOS || i >= s.size() || s[i] != '"') return false;
  const size_t end = skip_string(s, i);
  if (end == NPOS) return false;
  *out = s.substr(i + 1, end - i - 2);
  return true;
}
}  // namespace detail

// The reading in a reply to forecast_url(). Not ok unless current_units says °F and current has a
// plausible temperature_2m; weather_code and is_day are optional (unknown code: -1; no is_day: day).
inline Reading parse_current(const std::string &body) {
  using namespace detail;
  Reading r;
  const size_t root = ws(body, 0);
  std::string unit;
  if (!string_at(body, member(body, member(body, root, "current_units"), "temperature_2m"), &unit)) return r;
  if (unit != "°F" && unit != "\\u00b0F") return r;
  // The whole current object must have arrived, not just the members read from it.
  const size_t cur = member(body, root, "current");
  if (cur == NPOS || body[cur] != '{' || skip_value(body, cur) == NPOS) return r;
  double v;
  if (!number_at(body, member(body, cur, "temperature_2m"), &v) || !plausible_f((float) v)) return r;
  r.temp_f = (float) v;
  if (number_at(body, member(body, cur, "weather_code"), &v) && v >= 0 && v <= 99 && v == std::floor(v))
    r.code = (int) v;
  if (number_at(body, member(body, cur, "is_day"), &v)) r.is_day = v != 0;
  r.ok = true;
  return r;
}

// ── When to poll ──
struct PollTimes {
  uint32_t ok_ms = 30u * 60u * 1000u;    // after a good reading
  uint32_t retry_ms = 5u * 60u * 1000u;  // after a failed poll
};

enum class Step {
  Wait,   // nothing to do now
  Fetch,  // start a fetch; report back with done()
  Fail,   // a poll fell due with no network: a failed poll (blank the card)
};

// Call step() about once a second with whether the network is up. The first poll goes out as soon
// as the network is up; a poll due with no network fails at once; after a failure the network
// coming back polls at once. millis() wrap is fine (signed differences).
class Poller {
 public:
  explicit Poller(PollTimes t = {}) : t_(t) {}

  Step step(uint32_t now_ms, bool network_up) {
    const bool came_up = network_up && !net_was_up_;
    net_was_up_ = network_up;
    if (in_flight_) return Step::Wait;
    bool due = !scheduled_ || (int32_t) (now_ms - next_ms_) >= 0;
    if (!due && came_up && !last_ok_) due = true;
    if (!due) return Step::Wait;
    if (!network_up) {
      schedule_(false, now_ms);
      return Step::Fail;
    }
    in_flight_ = true;
    return Step::Fetch;
  }

  // The fetch that step() started has finished: ok = a usable reading.
  void done(bool ok, uint32_t now_ms) {
    in_flight_ = false;
    schedule_(ok, now_ms);
  }

  bool in_flight() const { return in_flight_; }

 private:
  void schedule_(bool ok, uint32_t now_ms) {
    last_ok_ = ok;
    scheduled_ = true;
    next_ms_ = now_ms + (ok ? t_.ok_ms : t_.retry_ms);
  }

  PollTimes t_;
  bool scheduled_ = false;
  bool in_flight_ = false;
  bool last_ok_ = false;
  bool net_was_up_ = false;
  uint32_t next_ms_ = 0;
};

}  // namespace chestnut_weather
