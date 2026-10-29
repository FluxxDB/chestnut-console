# Shopping list

Parts for the bench prototype and beyond. Prices are USD, checked 2026-10-29. A `~` marks a price seen only in a search result, which may be out of date. Check items off as they're bought.

## Bench rig: buy together (about $90–100 plus shipping, before the USB-C meter)

### M5Stack parts (about $25)

Buy these from **Mouser** (US stock, arrives in days, but may add a tariff surcharge at checkout) or the **[M5Stack store](https://shop.m5stack.com)** (lowest list price, but ships from China: 15–20 business days by air or paid DHL, duties extra). Compare the totals at checkout. Amazon has no genuine M5Stack 4-Relay.

- [ ] **M5Stack Unit ENV III** (U001-C; SHT30 + QMP6988). Temperature and humidity sensor. $5.95 ([store](https://shop.m5stack.com/products/env-iii-unit-with-temperature-humidity-air-pressure-sensor-sht30-qmp6988)). Replaces the **ENV IV (U001-D), which is discontinued**. The SHT30 is about as accurate as the SHT40 for room temperature (±0.2 °C typical). I2C 0x44 and 0x70; Port A is a separate bus from the Tab5's own chips, so the 0x44 doesn't clash.
- [ ] **M5Stack Unit 4-Relay** (U097; Mouser 170-U097). Switches heat (W), cool (Y), fan (G) and the heat-pump reversing valve (O/B). $12.95 ([store](https://shop.m5stack.com/products/4-relay-unit)). I2C 0x26; four normally-open 10 A contacts. The coils run off Port A's 5 V (about 90 mA each), and Port A's current limit isn't documented: check it on the bench.
- [ ] **M5Stack Grove Hub** (1-to-3; U006, Mouser 170-U006). Lets the sensor and relays share the Tab5's single Port A. $3.50 ([store](https://shop.m5stack.com/products/mini-hub-module)).
- [ ] **Grove cable, 50 cm, 2-pack** (A034-C). Keeps the sensor away from the Tab5's heat. $1.95 ([store](https://shop.m5stack.com/products/4pin-buckled-grove-cable)).

### Furnace stand-in and wiring (about $65–70)

- [ ] **24 V AC plug-in transformer**, 40 VA, screw terminals: Jameco ReliaPro **MGT-2440** (#2230627), ~$13.95 ([Jameco](https://www.jameco.com/z/MGT-2440-Jameco-ReliaPro-24-VAC-1600-mA-40-Watt-Wall-Adapter-Transformer_2230627.html)). Stands in for the furnace transformer. **The label must say 24V AC**; many look-alikes are DC. Alternative: Hammond BPE2G (internal fuse), ~$21–29 at Jameco or Digi-Key.
- [ ] **24 V AC/DC indicator lamps**: BAOMAIN AD16-22D 5-color pack (22 mm, screw terminals), $9.99 ([Amazon](https://www.amazon.com/dp/B01MEEIYAM)). Red = heat, blue = cool, green = fan, yellow = O/B. They stand in for the furnace.
- [ ] **Wago 221 lever connectors**: about ten each of 221-412 and 221-413, ~$13 ([Digi-Key](https://www.digikey.com/en/products/detail/wago-corporation/221-413/13549610)), or an Amazon assortment.
- [ ] **18/5 thermostat wire**: Southwire 50 ft, ~$19 ([Home Depot](https://homedepot.com/p/Southwire-50-ft-18-5-Brown-Solid-CU-CL2-Thermostat-Wire-64169640/204862207)), or Cimple Co 25 ft, ~$25 ([Amazon](https://www.amazon.com/dp/B07T6LJD6M)).
- [ ] **Inline fuse holder + 1 A fuses**: Littelfuse 01500274Z holder (5×20 mm) + 0216001.MXP fuses, ~$8 (Mouser or [Digi-Key](https://www.digikey.com/en/products/detail/littelfuse-inc/0216001-MXP/777492)). Goes in the R lead from the transformer.
- [ ] **USB-C power meter**, any inline model that shows watts (one that logs energy is handy). Measures the Tab5's draw, including while it charges its battery.

## Before the house visit

- [ ] **Multimeter** with AC volts and continuity, for the site survey. Pick a model when the visit is planned.

## Later: don't buy yet

- [ ] **Home Assistant box for the house**: Home Assistant Green, $199, about 1.7 W idle, storage built in ([home-assistant.io](https://www.home-assistant.io/green/)). Now cheaper and simpler than a reliable Raspberry Pi 5 setup (about $210+ with its power supply, case and SSD).
- [ ] **24 V AC → DC supply for the Tab5.** Wait for the measured Tab5 draw. One candidate: Altronix VR1T (24 V AC → 12 V DC, 1 A), ~$33, into the Tab5's 6–24 V DC input ([listing](https://www.surveillance-video.com/power-supply-vr1t.html)). Two cautions:
  - an HVAC transformer at light load can read 26–29 V AC, so check the module's input margin;
  - with a bridge rectifier, the Tab5's ground isn't C: never tie it to C, and don't plug the Tab5 into a grounded computer while it runs on 24 V AC.
- [ ] **If the house has no C wire**: Venstar ACC0410 Add-a-Wire, ~$33 ([SupplyHouse](https://www.supplyhouse.com/Venstar-ACC0410-Add-a-Wire)).
- [ ] **Mechanical low-limit "freeze" thermostat**, wired in parallel on R–W, set to about 45–50 °F, as an independent backup: Honeywell T822K1042 (35–85 °F, no batteries), ~$60 ([listing](https://www.industrialstores.com/product_detail/honeywell-t822k1042-mercury-free-heat-thermostat)). It covers the Tab5 failing to call for heat, not a relay stuck on. Mount it where it reads house air, away from the warm Tab5.
- [ ] **Wall plate / enclosure** for the Tab5, relays and power supply. Nothing ready-made fits, so it'll be 3D-printed. The Tab5 is 128 × 80 × 12 mm, wider than a double-gang plate. A Honeywell 50002883-001 cover plate (~$15–20) can hide the old thermostat's outline.
- [ ] **Final relay board**, depending on the site survey.

## Notes

- **The Tab5's battery** (NP-F550, 7.4 V, 2000 mAh, in Dang's unit) powers it only when outside power is lost, and charges only while the Tab5 is on. M5Stack publishes no power-draw figure; its "about 6 hours on battery" works out to roughly 2.5 W. Measure the draw while it charges before sizing the 24 V AC → DC supply.
