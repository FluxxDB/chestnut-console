// Relay unit tests (tab5-thermostat/hardware/relay_unit.h): the relay byte, and the link state
// machine that turns "did the unit answer this check" into the relay fault and Port A's power.
// Checks are once a second; times are ms from start(0), when Port A was powered at boot.
#include <cstdint>
#include <cstdio>

#include "relay_unit.h"

static int fails = 0, total = 0;
#define CHECK(cond)                                                                \
  do {                                                                             \
    ++total;                                                                       \
    if (!(cond)) {                                                                 \
      ++fails;                                                                     \
      std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);         \
    }                                                                              \
  } while (0)

using chestnut_hw::LinkOut;
using chestnut_hw::relay_byte;
using chestnut_hw::RelayLink;

// Steps from..to (inclusive) once a second with the same answer; returns the last output.
static LinkOut run(RelayLink &l, bool answered, uint32_t from, uint32_t to) {
  LinkOut o{};
  for (uint32_t t = from; t <= to; t += 1000) o = l.step(answered, t);
  return o;
}

int main() {
  // relay_byte_maps_relays
  {
    CHECK(relay_byte(1, 0, 0, 0) == 0x01);
    CHECK(relay_byte(0, 1, 0, 0) == 0x02);
    CHECK(relay_byte(0, 0, 1, 0) == 0x04);
    CHECK(relay_byte(0, 0, 0, 1) == 0x08);
    CHECK(relay_byte(0, 1, 1, 0) == 0x06);
    CHECK(relay_byte(1, 1, 1, 1) == 0x0F);
  }
  // link_boot_resyncs_once: the first answer after power-up asks for the registers to be sent.
  {
    RelayLink l;
    l.start(0);
    LinkOut o = l.step(true, 1000);
    CHECK(!o.fault && o.port_power && o.resync);
    CHECK(!l.step(true, 2000).resync);
  }
  // link_brief_glitch_no_fault: four failed checks are not a fault.
  {
    RelayLink l;
    l.start(0);
    l.step(true, 500);
    for (uint32_t t = 1000; t <= 4000; t += 1000) {
      LinkOut o = l.step(false, t);
      CHECK(!o.fault && o.port_power);
    }
    LinkOut o = l.step(true, 5000);
    CHECK(!o.fault && o.port_power);
  }
  // link_brief_mismatch_no_fault: a read-back mismatch arrives as answered=false; once it reads
  // right again there's no fault and no resync (the next write corrects the relays).
  {
    RelayLink l;
    l.start(0);
    CHECK(l.step(true, 500).resync);
    run(l, false, 1000, 4000);
    LinkOut o = run(l, true, 5000, 8000);
    CHECK(!o.fault && !o.resync && o.port_power);
  }
  // link_fault_after_5s, link_cut_10s_after_fault, link_resync_once_after_recovery: one timeline.
  {
    RelayLink l;
    l.start(0);
    run(l, false, 1000, 5000);
    LinkOut o = l.step(false, 5999);
    CHECK(!o.fault);
    o = l.step(false, 6000);
    CHECK(o.fault && o.port_power);
    o = run(l, false, 7000, 15000);
    CHECK(o.fault && o.port_power);
    o = l.step(false, 15999);
    CHECK(o.port_power);
    o = l.step(false, 16000);
    CHECK(o.fault && !o.port_power);
    o = l.step(true, 17000);  // an answer while Port A is off is ignored
    CHECK(o.fault && !o.port_power && !o.resync);
    o = l.step(false, 18000);
    CHECK(!o.port_power);
    o = l.step(false, 19000);  // 3 s off
    CHECK(o.fault && o.port_power);
    o = l.step(true, 19400);  // still in the 500 ms start-up window: ignored
    CHECK(o.fault && !o.resync);
    for (uint32_t t = 19500; t <= 24400; t += 100) {
      o = l.step(true, t);
      if (o.resync || !o.fault) break;
    }
    CHECK(o.fault && !o.resync);
    o = l.step(true, 24500);
    CHECK(!o.fault && o.resync && o.port_power);
    CHECK(!l.step(true, 25500).resync);
  }
  // link_retry_every_30s: a unit that never comes back gets its power cut every 30 s.
  {
    RelayLink l;
    l.start(0);
    l.step(true, 500);
    bool cut_16 = false, cut_46 = false, cut_76 = false, other_cut = false, fault_always = true;
    bool was_on = true;
    for (uint32_t t = 1000; t <= 80000; t += 1000) {
      LinkOut o = l.step(false, t);
      if (t >= 6000 && !o.fault) fault_always = false;
      if (was_on && !o.port_power) {
        if (t == 16000) cut_16 = true;
        else if (t == 46000) cut_46 = true;
        else if (t == 76000) cut_76 = true;
        else other_cut = true;
      }
      was_on = o.port_power;
    }
    CHECK(cut_16 && cut_46 && cut_76 && !other_cut);
    CHECK(fault_always);
  }
  // link_never_answers_from_boot: no answer at all from the first check; same schedule, never
  // a "failed for good" state.
  {
    RelayLink l;
    l.start(0);
    bool cut_16 = false, cut_46 = false, cut_76 = false, other_cut = false, fault_always = true;
    bool was_on = true;
    for (uint32_t t = 1000; t <= 80000; t += 1000) {
      LinkOut o = l.step(false, t);
      if (t >= 6000 && !o.fault) fault_always = false;
      if (t < 6000 && o.fault) fault_always = false;
      if (was_on && !o.port_power) {
        if (t == 16000) cut_16 = true;
        else if (t == 46000) cut_46 = true;
        else if (t == 76000) cut_76 = true;
        else other_cut = true;
      }
      was_on = o.port_power;
    }
    CHECK(cut_16 && cut_46 && cut_76 && !other_cut);
    CHECK(fault_always);
  }

  if (fails) {
    std::fprintf(stderr, "FAIL: %d of %d checks\n", fails, total);
    return 1;
  }
  std::printf("PASS: %d checks\n", total);
  return 0;
}
