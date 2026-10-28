# Shopping list

Parts for the bench prototype and beyond. Prices are rough 2026 USD. Check items off as they're bought.

## Bench rig: buy together (about $80–100)

- [ ] **M5Stack Unit ENV IV** (SHT40 + BMP280). Temperature and humidity sensor. ~$8–10
- [ ] **M5Stack Unit 4-Relay** (U097). Switches heat (W), cool (Y), fan (G) and the heat-pump reversing valve (O/B). ~$13–16
- [ ] **M5Stack Grove Hub** (1-to-3) + one **50 cm Grove cable**. Lets the sensor and relays share the Tab5's single Port A, and keeps the sensor away from the Tab5's heat. ~$5
- [ ] **24 V AC plug-in transformer**, 20–40 VA. Stands in for the furnace transformer. **The label must say 24V AC**; many look-alikes are DC. ~$15
- [ ] **24 V AC/DC LED indicator lights**, 4 colors (red = heat, blue = cool, green = fan, yellow = O/B). Stand in for the furnace. ~$10
- [ ] **Wago 221 lever connectors** + a few feet of **18-gauge thermostat wire**. ~$15–20
- [ ] **Inline fuse holder + 1 A fuses**. Fuses the 24 V AC side. ~$5
- [ ] **USB-C power meter**. Measures the Tab5's power draw. ~$15

## Before the house visit

- [ ] **Multimeter** with AC volts and continuity, for the site survey. ~$30

## Later: don't buy yet

- [ ] **24 V AC → DC supply for the Tab5.** Wait for the measured Tab5 draw. Likely a bridge rectifier + filter capacitor + buck converter rated ≥ 50 V input, or a ready-made module.
- [ ] **Home Assistant box for the house.** Home Assistant Green (~$199, ~1.7 W idle) or a Raspberry Pi 5 (~$127 bare plus storage and power supply).
- [ ] **Mechanical low-limit "freeze" thermostat** wired in parallel on R–W, set to about 45–50 °F, as an independent backup.
- [ ] **Wall plate / enclosure** for the Tab5, relays and power supply (likely 3D-printed).
- [ ] **Final relay board**, depending on the site survey.
