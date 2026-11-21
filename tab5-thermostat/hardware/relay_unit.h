// The M5Stack Unit 4-Relay on Port A (milestone 4): its registers, the relay byte, and the link
// state machine that decides the relay fault and when to cut Port A's power. Pure C++ (no ESPHome),
// so tools/bench/test_unit.sh tests it with plain g++. bench-io.yaml does the I2C and calls step()
// once a second. Spec: docs/superpowers/specs/2026-11-18-bench-rig-design.md, "Relay fault".
#pragma once

#include <cstdint>

namespace chestnut_hw {

constexpr uint8_t RELAY_ADDR = 0x26;
constexpr uint8_t REG_MODE = 0x10;
constexpr uint8_t REG_RELAYS = 0x11;
// Mode register value: each relay's LED follows the relay. The unit then mirrors the relays into
// the upper nibble of REG_RELAYS, so a read-back is compared on the low four bits only.
constexpr uint8_t MODE_LEDS_FOLLOW = 0x01;

// Relay 1 = W (heat), 2 = Y (cool), 3 = G (fan), 4 = O/B; bit 0..3. Upper nibble 0.
inline uint8_t relay_byte(bool w, bool y, bool g, bool ob) {
  return (uint8_t) ((w ? 0x01 : 0) | (y ? 0x02 : 0) | (g ? 0x04 : 0) | (ob ? 0x08 : 0));
}

struct LinkTimes {
  uint32_t fault_after_ms = 5000;    // failed checks in a row before the relay fault
  uint32_t cut_after_ms = 10000;     // from the fault to the first Port A power cut
  uint32_t off_for_ms = 3000;        // how long Port A stays off
  uint32_t boot_ms = 500;            // after power returns, answers are ignored while the unit starts
  uint32_t retry_every_ms = 30000;   // between cuts while the unit still doesn't answer
  uint32_t clear_after_ms = 5000;    // steady answers before the fault clears
};

struct LinkOut {
  bool fault;       // relay_fault
  bool port_power;  // what external_5v_power should be
  bool resync;      // write REG_MODE and the current relay byte now (once per power-up)
};

class RelayLink {
 public:
  explicit RelayLink(LinkTimes t = {}) : t_(t) {}

  // Port A was just powered (at boot).
  void start(uint32_t now_ms) { power_up_(now_ms); }

  // One check: did the unit answer (write ok and the read-back's low nibble equal)?
  LinkOut step(bool answered, uint32_t now_ms) {
    if (!power_) {
      if (now_ms - cut_at_ < t_.off_for_ms) return {fault_, false, false};
      power_up_(now_ms);
      return {fault_, true, false};
    }
    if ((int32_t) (now_ms - boot_until_) < 0) return {fault_, true, false};

    if (answered) {
      failing_ = false;
      if (!fault_) {
        const bool rs = resync_pending_;
        resync_pending_ = false;
        return {false, true, rs};
      }
      if (!recovering_) {
        recovering_ = true;
        ok_since_ = now_ms;
      }
      if (now_ms - ok_since_ < t_.clear_after_ms) return {true, true, false};
      fault_ = false;
      recovering_ = false;
      resync_pending_ = false;
      return {false, true, true};
    }

    recovering_ = false;
    if (!fault_) {
      if (!failing_) {
        failing_ = true;
        failing_since_ = now_ms;
      }
      if (now_ms - failing_since_ < t_.fault_after_ms) return {false, true, false};
      fault_ = true;
      fault_since_ = now_ms;
      cut_yet_ = false;
    }
    const bool due = cut_yet_ ? now_ms - cut_at_ >= t_.retry_every_ms : now_ms - fault_since_ >= t_.cut_after_ms;
    if (!due) return {true, true, false};
    power_ = false;
    cut_yet_ = true;
    cut_at_ = now_ms;
    return {true, false, false};
  }

 private:
  void power_up_(uint32_t now_ms) {
    power_ = true;
    boot_until_ = now_ms + t_.boot_ms;
    resync_pending_ = true;
    failing_ = false;
    recovering_ = false;
  }

  LinkTimes t_;
  bool power_ = false;
  bool fault_ = false;
  bool failing_ = false;
  bool recovering_ = false;
  bool resync_pending_ = false;
  bool cut_yet_ = false;
  uint32_t boot_until_ = 0;
  uint32_t failing_since_ = 0;
  uint32_t fault_since_ = 0;
  uint32_t ok_since_ = 0;
  uint32_t cut_at_ = 0;
};

}  // namespace chestnut_hw
