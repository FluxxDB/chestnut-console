#include "check.h"
#include "weather.h"

#include <cmath>
#include <cstring>
#include <string>

using namespace chestnut_weather;

// A reply as Open-Meteo sends it (dummy coordinates), for ?current=temperature_2m,weather_code,is_day
// &temperature_unit=fahrenheit.
static std::string reply(const std::string &current, const std::string &unit = "°F") {
  return "{\"latitude\":52.52,\"longitude\":13.419998,\"generationtime_ms\":0.02,\"utc_offset_seconds\":0,"
         "\"timezone\":\"GMT\",\"timezone_abbreviation\":\"GMT\",\"elevation\":38.0,"
         "\"current_units\":{\"time\":\"iso8601\",\"interval\":\"seconds\",\"temperature_2m\":\"" + unit + "\","
         "\"weather_code\":\"wmo code\",\"is_day\":\"\"},"
         "\"current\":{" + current + "}}";
}
static const std::string NORMAL = "\"time\":\"2026-11-21T20:00\",\"interval\":900,\"temperature_2m\":53.2,\"weather_code\":3,\"is_day\":0";

static void parses_a_normal_reply() {
  Reading r = parse_current(reply(NORMAL));
  CHECK(r.ok);
  CHECK_NEAR(r.temp_f, 53.2, 0.001);
  CHECK(r.code == 3);
  CHECK(!r.is_day);
}

static void parses_negative_and_whole_temperatures() {
  CHECK_NEAR(parse_current(reply("\"temperature_2m\":-12.5,\"weather_code\":71,\"is_day\":1")).temp_f, -12.5, 0.001);
  Reading r = parse_current(reply("\"temperature_2m\":80,\"weather_code\":0,\"is_day\":1"));
  CHECK(r.ok);
  CHECK_NEAR(r.temp_f, 80.0, 0.001);
  CHECK(r.is_day);
}

// Pretty-printed, keys in another order, "current" before "current_units".
static void parses_any_layout() {
  std::string body =
      "{\n  \"current\" : {\n    \"is_day\" : 1,\n    \"weather_code\" : 61 ,\n    \"temperature_2m\" : 44.6\n  },\n"
      "  \"current_units\" : { \"temperature_2m\" : \"°F\" }\n}";
  Reading r = parse_current(body);
  CHECK(r.ok);
  CHECK_NEAR(r.temp_f, 44.6, 0.001);
  CHECK(r.code == 61);
  CHECK(r.is_day);
}

// Only the "current" object counts: a temperature_2m elsewhere (current_units has one, as a string)
// is never read as the reading.
static void reads_only_the_current_object() {
  std::string body = "{\"hourly\":{\"temperature_2m\":[1,2]},\"current_units\":{\"temperature_2m\":\"°F\"},"
                     "\"current\":{\"temperature_2m\":61.0,\"weather_code\":2,\"is_day\":1}}";
  Reading r = parse_current(body);
  CHECK(r.ok);
  CHECK_NEAR(r.temp_f, 61.0, 0.001);
}

static void rejects_bad_replies() {
  CHECK(!parse_current("").ok);
  CHECK(!parse_current("not json").ok);
  CHECK(!parse_current("{\"error\":true,\"reason\":\"Latitude must be in range of -90 to 90°.\"}").ok);
  // Cut off mid-way.
  std::string full = reply(NORMAL);
  CHECK(!parse_current(full.substr(0, full.size() - 30)).ok);
  // No reading, or a null one.
  CHECK(!parse_current(reply("\"weather_code\":3,\"is_day\":0")).ok);
  CHECK(!parse_current(reply("\"temperature_2m\":null,\"weather_code\":3,\"is_day\":0")).ok);
  CHECK(!parse_current(reply("\"temperature_2m\":\"53\",\"weather_code\":3,\"is_day\":0")).ok);
  // No "current" object at all, or one that isn't an object.
  CHECK(!parse_current("{\"current_units\":{\"temperature_2m\":\"°F\"}}").ok);
  CHECK(!parse_current("{\"current_units\":{\"temperature_2m\":\"°F\"},\"current\":53.2}").ok);
}

// The unit must be °F: a reply in °C (or with no units) would show a wrong number.
// A reply cut off anywhere gives no reading, or the right one: never a shortened number.
static void any_cut_is_no_reading_or_the_right_one() {
  for (const std::string &cur : {NORMAL, std::string("\"temperature_2m\":-12.5,\"weather_code\":75,\"is_day\":1")}) {
    const std::string full = reply(cur);
    const Reading want = parse_current(full);
    CHECK(want.ok);
    for (size_t n = 0; n < full.size(); n++) {
      Reading r = parse_current(full.substr(0, n));
      CHECK(!r.ok || (r.temp_f == want.temp_f && r.code == want.code && r.is_day == want.is_day));
    }
  }
}

static void rejects_other_units() {
  CHECK(!parse_current(reply(NORMAL, "°C")).ok);
  CHECK(!parse_current("{\"current\":{\"temperature_2m\":53.2,\"weather_code\":3,\"is_day\":0}}").ok);
}

static void rejects_implausible_temperatures() {
  CHECK(!parse_current(reply("\"temperature_2m\":200.0,\"weather_code\":3,\"is_day\":0")).ok);
  CHECK(!parse_current(reply("\"temperature_2m\":-100.0,\"weather_code\":3,\"is_day\":0")).ok);
  CHECK(plausible_f(-60.0f) && plausible_f(130.0f));
  CHECK(!plausible_f(NAN));
}

// A missing or unknown weather code keeps the temperature: no words, the default icon.
static void unknown_code_keeps_the_temperature() {
  Reading r = parse_current(reply("\"temperature_2m\":50.0,\"is_day\":1"));
  CHECK(r.ok);
  CHECK(r.code == -1);
  CHECK(std::strcmp(condition_text(r.code), "") == 0);
  CHECK(std::strcmp(icon_for(r.code, true), ICON_DEFAULT) == 0);
  r = parse_current(reply("\"temperature_2m\":50.0,\"weather_code\":4,\"is_day\":1"));
  CHECK(r.ok);
  CHECK(std::strcmp(condition_text(4), "") == 0);
  CHECK(std::strcmp(icon_for(4, false), ICON_DEFAULT) == 0);
}

// A missing is_day counts as day.
static void missing_is_day_is_day() {
  Reading r = parse_current(reply("\"temperature_2m\":50.0,\"weather_code\":0"));
  CHECK(r.ok);
  CHECK(r.is_day);
}

static void conditions_in_words() {
  CHECK(std::strcmp(condition_text(0), "Clear") == 0);
  CHECK(std::strcmp(condition_text(1), "Mostly clear") == 0);
  CHECK(std::strcmp(condition_text(2), "Partly cloudy") == 0);
  CHECK(std::strcmp(condition_text(3), "Cloudy") == 0);
  CHECK(std::strcmp(condition_text(45), "Fog") == 0);
  CHECK(std::strcmp(condition_text(48), "Fog") == 0);
  CHECK(std::strcmp(condition_text(53), "Drizzle") == 0);
  CHECK(std::strcmp(condition_text(57), "Icy drizzle") == 0);
  CHECK(std::strcmp(condition_text(61), "Light rain") == 0);
  CHECK(std::strcmp(condition_text(63), "Rain") == 0);
  CHECK(std::strcmp(condition_text(65), "Heavy rain") == 0);
  CHECK(std::strcmp(condition_text(66), "Freezing rain") == 0);
  CHECK(std::strcmp(condition_text(71), "Light snow") == 0);
  CHECK(std::strcmp(condition_text(73), "Snow") == 0);
  CHECK(std::strcmp(condition_text(75), "Heavy snow") == 0);
  CHECK(std::strcmp(condition_text(77), "Snow grains") == 0);
  CHECK(std::strcmp(condition_text(80), "Showers") == 0);
  CHECK(std::strcmp(condition_text(82), "Heavy showers") == 0);
  CHECK(std::strcmp(condition_text(85), "Snow showers") == 0);
  CHECK(std::strcmp(condition_text(95), "Thunderstorms") == 0);
  CHECK(std::strcmp(condition_text(99), "Hailstorms") == 0);
  CHECK(std::strcmp(condition_text(-1), "") == 0);
  CHECK(std::strcmp(condition_text(100), "") == 0);
}

static void icons_follow_the_condition() {
  CHECK(std::strcmp(icon_for(0, true), ICON_SUNNY) == 0);
  CHECK(std::strcmp(icon_for(0, false), ICON_NIGHT) == 0);
  CHECK(std::strcmp(icon_for(2, true), ICON_PARTLY) == 0);
  CHECK(std::strcmp(icon_for(2, false), ICON_NIGHT_PARTLY) == 0);
  CHECK(std::strcmp(icon_for(3, false), ICON_CLOUDY) == 0);
  CHECK(std::strcmp(icon_for(45, true), ICON_FOG) == 0);
  CHECK(std::strcmp(icon_for(63, true), ICON_RAIN) == 0);
  CHECK(std::strcmp(icon_for(65, true), ICON_POURING) == 0);
  CHECK(std::strcmp(icon_for(66, true), ICON_SLEET) == 0);
  CHECK(std::strcmp(icon_for(73, true), ICON_SNOW) == 0);
  CHECK(std::strcmp(icon_for(75, true), ICON_HEAVY_SNOW) == 0);
  CHECK(std::strcmp(icon_for(95, false), ICON_STORM) == 0);
  CHECK(std::strcmp(icon_for(96, true), ICON_HAIL) == 0);
  CHECK(std::strcmp(ICON_DEFAULT, ICON_CLOUDY) == 0);
}

// Every icon icon_for can return is in ALL_ICONS (the list the font's glyphs must cover), and each
// is one 4-byte UTF-8 character in Material Design Icons' range (U+F0000 and up).
static void icons_are_all_listed() {
  auto listed = [](const char *g) {
    for (const char *a : ALL_ICONS)
      if (std::strcmp(a, g) == 0) return true;
    return false;
  };
  for (int code = -2; code <= 101; code++) {
    CHECK(listed(icon_for(code, true)));
    CHECK(listed(icon_for(code, false)));
  }
  for (const char *g : ALL_ICONS) {
    const unsigned char *u = (const unsigned char *) g;
    CHECK(std::strlen(g) == 4 && u[0] == 0xF3 && u[1] >= 0xB0);
  }
}

static const uint32_t MIN = 60u * 1000u;

// The first poll goes out as soon as the network is up.
static void first_poll_when_the_network_is_up() {
  Poller p;
  CHECK(p.step(1000, true) == Step::Fetch);
  CHECK(p.in_flight());
  CHECK(p.step(2000, true) == Step::Wait);  // one at a time
}

// A poll that falls due with no network is a failed poll (the card blanks), retried in 5 minutes,
// and at once when the network comes up.
static void no_network_is_a_failure() {
  Poller p;
  CHECK(p.step(1000, false) == Step::Fail);
  CHECK(!p.in_flight());
  CHECK(p.step(2000, false) == Step::Wait);
  CHECK(p.step(3000, true) == Step::Fetch);  // network up: at once
  Poller q;
  CHECK(q.step(1000, false) == Step::Fail);
  CHECK(q.step(1000 + 5 * MIN - 1, false) == Step::Wait);
  CHECK(q.step(1000 + 5 * MIN, false) == Step::Fail);
}

static void success_waits_30_minutes() {
  Poller p;
  CHECK(p.step(0, true) == Step::Fetch);
  p.done(true, 2000);
  CHECK(!p.in_flight());
  CHECK(p.step(2000 + 30 * MIN - 1, true) == Step::Wait);
  CHECK(p.step(2000 + 30 * MIN, true) == Step::Fetch);
}

static void failure_retries_in_5_minutes() {
  Poller p;
  CHECK(p.step(0, true) == Step::Fetch);
  p.done(false, 2000);
  CHECK(p.step(2000 + 5 * MIN - 1, true) == Step::Wait);
  CHECK(p.step(2000 + 5 * MIN, true) == Step::Fetch);
}

// A Wi-Fi blip after a good reading doesn't poll early (the reading is still fresh); after a
// failed poll it does.
static void network_return_polls_only_after_a_failure() {
  Poller p;
  CHECK(p.step(0, true) == Step::Fetch);
  p.done(true, 1000);
  CHECK(p.step(10 * MIN, false) == Step::Wait);
  CHECK(p.step(10 * MIN + 1000, true) == Step::Wait);
  CHECK(p.step(1000 + 30 * MIN, false) == Step::Fail);  // due with no network: blank
  CHECK(p.step(1000 + 30 * MIN + 1000, true) == Step::Fetch);
}

// The network going away mid-fetch doesn't count until the fetch reports back.
static void waits_for_the_fetch_in_flight() {
  Poller p;
  CHECK(p.step(0, true) == Step::Fetch);
  CHECK(p.step(30 * MIN, false) == Step::Wait);
  p.done(false, 30 * MIN + 1);
  CHECK(p.step(30 * MIN + 2, true) == Step::Fetch);  // the network is up again after a failure
}

// millis() wraps after 49.7 days; the timing doesn't care.
static void survives_millis_wrap() {
  Poller p;
  const uint32_t t0 = 0xFFFFFFFFu - 60000u;
  CHECK(p.step(t0, true) == Step::Fetch);
  p.done(true, t0);
  CHECK(p.step(t0 + 29 * MIN, true) == Step::Wait);  // wrapped past 0
  CHECK(p.step(t0 + 30 * MIN, true) == Step::Fetch);
  p.done(false, t0 + 30 * MIN);
  CHECK(p.step(t0 + 35 * MIN - 1, true) == Step::Wait);
  CHECK(p.step(t0 + 35 * MIN, true) == Step::Fetch);
}

// Odd but valid layouts around the reading: nested values, escaped quotes, a repeated key (the first
// counts), some nesting before "current".
static void reads_past_odd_values() {
  std::string body = "{\"note\":\"a \\\"quoted\\\" } { string\",\"deep\":{\"a\":[1,{\"b\":[[2],[3]]},\"x\"]},"
                     "\"current_units\":{\"temperature_2m\":\"°F\"},"
                     "\"current\":{\"temperature_2m\":40.5,\"weather_code\":1,\"is_day\":1},"
                     "\"current\":{\"temperature_2m\":99.0,\"weather_code\":3,\"is_day\":1}}";
  Reading r = parse_current(body);
  CHECK(r.ok);
  CHECK_NEAR(r.temp_f, 40.5, 0.001);
  CHECK(r.code == 1);
  std::string nested = "{\"n\":";
  for (int i = 0; i < 10; i++) nested += "[";
  for (int i = 0; i < 10; i++) nested += "]";
  nested += ",\"current_units\":{\"temperature_2m\":\"°F\"},\"current\":{\"temperature_2m\":40.5}}";
  CHECK(parse_current(nested).ok);
}

// Thousands of nested brackets (a broken or hostile reply) are refused, not followed: the reader
// runs on the main loop's small stack.
static void refuses_deep_nesting() {
  for (const char *open : {"[", "{\"a\":"}) {
    std::string body = "{\"x\":";
    for (int i = 0; i < 4000; i++) body += open;
    body += "1";
    for (int i = 0; i < 4000; i++) body += open[0] == '[' ? "]" : "}";
    body += ",\"current_units\":{\"temperature_2m\":\"°F\"},\"current\":{\"temperature_2m\":40.5}}";
    CHECK(!parse_current(body).ok);
  }
}

// A number too big for a float is refused before it's converted.
static void refuses_huge_numbers() {
  CHECK(!parse_current(reply("\"temperature_2m\":1e300,\"weather_code\":3,\"is_day\":0")).ok);
  CHECK(!parse_current(reply("\"temperature_2m\":-1e300,\"weather_code\":3,\"is_day\":0")).ok);
  // A weather code out of range is unknown; the temperature still counts.
  Reading r = parse_current(reply("\"temperature_2m\":50,\"weather_code\":1e300,\"is_day\":0"));
  CHECK(r.ok && r.code == -1);
}

// What a finished fetch gives: a reading only from a complete 200 reply.
static void reading_only_from_a_whole_200_reply() {
  const std::string good = reply(NORMAL);
  CHECK(reading_from(200, good, false).ok);
  CHECK(!reading_from(404, good, false).ok);
  CHECK(!reading_from(500, good, false).ok);
  CHECK(!reading_from(-1, "", false).ok);  // no reply
  CHECK(!reading_from(200, good, true).ok);  // the body overflowed: parts were dropped
  CHECK(!reading_from(200, "", false).ok);
}

// A reading older than 40 minutes (a fetch stuck past its own timeouts, say) is blanked once,
// even with a fetch still in flight; a reading that keeps being renewed never is.
static void a_stuck_reading_expires() {
  Poller p;
  CHECK(p.step(0, true) == Step::Fetch);
  p.done(true, 0);
  CHECK(p.step(30 * MIN, true) == Step::Fetch);  // this fetch never reports back
  CHECK(p.step(40 * MIN, true) == Step::Wait);
  CHECK(p.step(40 * MIN + 1, true) == Step::Expire);
  CHECK(p.step(40 * MIN + 2, true) == Step::Wait);  // once
  CHECK(p.step(90 * MIN, true) == Step::Wait);
  Poller q;
  CHECK(q.step(0, true) == Step::Fetch);
  q.done(true, 0);
  bool expired = false;
  for (uint32_t t = 1000; t < 5u * 60u * MIN; t += 1000) {
    const Step s = q.step(t, true);
    expired |= s == Step::Expire;
    if (s == Step::Fetch) q.done(true, t);
  }
  CHECK(!expired);
}

// After a failed poll there's nothing on show to expire.
static void no_expiry_after_a_failure() {
  Poller p;
  CHECK(p.step(0, true) == Step::Fetch);
  p.done(true, 0);
  CHECK(p.step(30 * MIN, true) == Step::Fetch);
  p.done(false, 30 * MIN + 500);
  bool expired = false;
  for (uint32_t t = 30 * MIN + 1000; t < 120 * MIN; t += 1000) {
    const Step s = p.step(t, false);
    expired |= s == Step::Expire;
  }
  CHECK(!expired);
}

static void url_carries_the_place_and_units() {
  std::string u = forecast_url("https://api.open-meteo.com/v1/forecast", "52.52", "13.41");
  CHECK(u == "https://api.open-meteo.com/v1/forecast?latitude=52.52&longitude=13.41"
             "&current=temperature_2m,weather_code,is_day&temperature_unit=fahrenheit&timezone=GMT&forecast_days=1");
}

int main() {
  parses_a_normal_reply();
  parses_negative_and_whole_temperatures();
  parses_any_layout();
  reads_only_the_current_object();
  rejects_bad_replies();
  any_cut_is_no_reading_or_the_right_one();
  rejects_other_units();
  rejects_implausible_temperatures();
  unknown_code_keeps_the_temperature();
  missing_is_day_is_day();
  conditions_in_words();
  icons_follow_the_condition();
  icons_are_all_listed();
  first_poll_when_the_network_is_up();
  no_network_is_a_failure();
  success_waits_30_minutes();
  failure_retries_in_5_minutes();
  network_return_polls_only_after_a_failure();
  waits_for_the_fetch_in_flight();
  survives_millis_wrap();
  url_carries_the_place_and_units();
  reads_past_odd_values();
  refuses_deep_nesting();
  refuses_huge_numbers();
  reading_only_from_a_whole_200_reply();
  a_stuck_reading_expires();
  no_expiry_after_a_failure();
  return CHECK_SUMMARY("test_weather");
}
