// I2C glue for the Unit 4-Relay on Port A (milestone 4), used by bench-io.yaml. The pure parts
// (registers, relay byte, link state machine) are in relay_unit.h. Never call these while Port A is
// unpowered: the unpowered units hold the bus lines low and every transfer then stalls the loop.
#pragma once

#include <driver/i2c_master.h>

#include "esphome/components/i2c/i2c_bus.h"
#include "relay_unit.h"

namespace chestnut_hw {

// The one relay link (ESPHome declares globals above the project's includes, so it can't be a
// `globals:` entry of this type).
inline RelayLink &relay_link() {
  static RelayLink link;
  return link;
}

inline bool write_reg(esphome::i2c::I2CBus *bus, uint8_t reg, uint8_t value) {
  const uint8_t buf[2] = {reg, value};
  return bus->write(RELAY_ADDR, buf, 2) == esphome::i2c::ERROR_OK;
}

inline bool read_reg(esphome::i2c::I2CBus *bus, uint8_t reg, uint8_t *value) {
  return bus->write_readv(RELAY_ADDR, &reg, 1, value, 1) == esphome::i2c::ERROR_OK;
}

// Recovery (safe) mode sets up neither the board's I2C buses nor its IO expander, so Port A keeps
// the power it had, and the relay unit the relays it held (checked on the bench, 2026-11-18). Cut
// it straight through the ESP-IDF driver: IO expander 1 (0x43, internal bus on GPIO31/32), output
// register 0x05, bit 2 = external 5 V (Port A). Returns whether the write went through.
inline bool cut_port_a_power_raw() {
  bool ok = false;
  i2c_master_bus_config_t bc = {};
  bc.i2c_port = -1;
  bc.sda_io_num = GPIO_NUM_31;
  bc.scl_io_num = GPIO_NUM_32;
  bc.clk_source = I2C_CLK_SRC_DEFAULT;
  bc.glitch_ignore_cnt = 7;
  bc.flags.enable_internal_pullup = true;
  i2c_master_bus_handle_t bus;
  if (i2c_new_master_bus(&bc, &bus) != ESP_OK) return false;
  i2c_device_config_t dc = {};
  dc.dev_addr_length = I2C_ADDR_BIT_LEN_7;
  dc.device_address = 0x43;
  dc.scl_speed_hz = 100000;
  i2c_master_dev_handle_t dev;
  if (i2c_master_bus_add_device(bus, &dc, &dev) == ESP_OK) {
    uint8_t reg = 0x05, out = 0;
    if (i2c_master_transmit_receive(dev, &reg, 1, &out, 1, 100) == ESP_OK) {
      const uint8_t w[2] = {0x05, (uint8_t) (out & ~0x04)};
      ok = i2c_master_transmit(dev, w, 2, 100) == ESP_OK;
    }
    i2c_master_bus_rm_device(dev);
  }
  i2c_del_master_bus(bus);
  return ok;
}

}  // namespace chestnut_hw
