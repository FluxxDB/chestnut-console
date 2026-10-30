# Shopping list

Parts for the bench prototype and beyond. Prices are USD, checked 2026-10-29. A `~` marks a price seen only in a search result, which may be out of date. Check items off as they're bought.

## Buy first (about $22 plus shipping)

These are the parts the real thermostat needs, and all three go into the final install. Reviewed one by one with Dang on 2026-10-29.

Buy these from **Mouser** (US stock, arrives in days, but may add a tariff surcharge at checkout) or the **[M5Stack store](https://shop.m5stack.com)** (lowest list price, but ships from China: 15–20 business days by air or paid DHL, duties extra). Compare the totals at checkout. Amazon has no genuine M5Stack 4-Relay.

- [ ] **M5Stack Unit ENV III** (U001-C; SHT30 + QMP6988). Temperature and humidity sensor. $5.95 ([store](https://shop.m5stack.com/products/env-iii-unit-with-temperature-humidity-air-pressure-sensor-sht30-qmp6988)). Replaces the **ENV IV (U001-D), which is discontinued**. The SHT30 is about as accurate as the SHT40 for room temperature (±0.2 °C typical). I2C 0x44 and 0x70; Port A is a separate bus from the Tab5's own chips, so the 0x44 doesn't clash. Comes in a case with a 20 cm Grove cable. Chosen over the Adafruit SHT45 + PTFE (more accurate, dust filter, ~$15.50, but a bare board) for being plug-and-play. **Mount it below the Tab5**, in its own vented pocket, never above or behind it: the Tab5's warm air rises.
- [ ] **M5Stack Unit 4-Relay** (U097; Mouser 170-U097). Switches heat (W), cool (Y), fan (G) and the heat-pump reversing valve (O/B). $12.95 ([store](https://shop.m5stack.com/products/4-relay-unit)). I2C 0x26; four normally-open 10 A contacts with an LED each; M5Stack publishes an official ESPHome component. It fails safe: if the Tab5 crashes or loses power, every relay opens. It comes with a 20 cm Grove cable and four plug-in terminals, and it's a 112 × 23 mm bar that fits behind the Tab5. The coils run off Port A's 5 V (about 90 mA each); Port A's current limit isn't documented, so check it on the bench.
  - **Four relays cover** a single-stage furnace + AC, a heat pump with backup heat, split Rh/Rc transformers and a zone panel. **They don't cover** two-stage equipment (W2 or Y2 terminals in use) or a "communicating" system. The site survey confirms (see below).
- [ ] **M5Stack Grove Hub** (1-to-3; U006, Mouser 170-U006). Lets the sensor and relays share the Tab5's single Port A; neither unit can be chained. $3.50 ([store](https://shop.m5stack.com/products/mini-hub-module)). The 20 cm cables that come with the sensor and relays are enough, so no extra cables.

**No USB-C power meter needed.** The Tab5's built-in monitor (INA226) measures the battery: unplugged, the Tab5 runs on the battery, so battery current × voltage is its real draw, and a negative current while plugged in is the charging draw. Measured 2026-10-29: see "Notes".

## Optional: a fake furnace for the desk (about $65–70)

A stand-in furnace, so the relays switch real 24 V AC on the desk before anything touches the house: the lamps light up as heat, cool and fan come on. **Not required.** The thermostat logic is already tested against M2's simulated house, and a multimeter in continuity mode (see "Before the house visit") can confirm each relay switches.

- [ ] **24 V AC plug-in transformer**, 40 VA, screw terminals: Jameco ReliaPro **MGT-2440** (#2230627), ~$13.95 ([Jameco](https://www.jameco.com/z/MGT-2440-Jameco-ReliaPro-24-VAC-1600-mA-40-Watt-Wall-Adapter-Transformer_2230627.html)). Stands in for the furnace transformer. **The label must say 24V AC**; many look-alikes are DC. Alternative: Hammond BPE2G (internal fuse), ~$21–29 at Jameco or Digi-Key.
- [ ] **24 V AC/DC indicator lamps**: BAOMAIN AD16-22D 5-color pack (22 mm, screw terminals), $9.99 ([Amazon](https://www.amazon.com/dp/B01MEEIYAM)). Red = heat, blue = cool, green = fan, yellow = O/B. They stand in for the furnace.
- [ ] **Wago 221 lever connectors**: about ten each of 221-412 and 221-413, ~$13 ([Digi-Key](https://www.digikey.com/en/products/detail/wago-corporation/221-413/13549610)), or an Amazon assortment.
- [ ] **18/5 thermostat wire**: Southwire 50 ft, ~$19 ([Home Depot](https://homedepot.com/p/Southwire-50-ft-18-5-Brown-Solid-CU-CL2-Thermostat-Wire-64169640/204862207)), or Cimple Co 25 ft, ~$25 ([Amazon](https://www.amazon.com/dp/B07T6LJD6M)).
- [ ] **Inline fuse holder + 1 A fuses**: Littelfuse 01500274Z holder (5×20 mm) + 0216001.MXP fuses, ~$8 (Mouser or [Digi-Key](https://www.digikey.com/en/products/detail/littelfuse-inc/0216001-MXP/777492)). Goes in the R lead from the transformer. Optional even with the fake furnace: the transformer above is a power-limited "Class 2" type.

Thermostat wire is sold in rolls, but the fake furnace needs only a few feet. Many hardware stores sell it by the foot, and any similar wire works.

## Before the house visit

- [ ] **Multimeter** with AC volts and continuity, for the site survey. Pick a model when the visit is planned. On the bench, its continuity mode also confirms each relay switches.

### Site survey checklist

Photos anyone at the house can take now:
- The old thermostat's **wiring terminals** (face pulled off): which letters have wires, their colors, and any jumper between Rh and Rc. This photo alone answers the system type, the stages, any heat pump and the C wire.
- The old thermostat's **model label**.
- The **furnace or air handler's model sticker** (behind the front panel) and the **outdoor unit's sticker**.
- Near the furnace: whether there's a **zone panel**, and whether the top-floor thermostat runs to the same furnace or a separate system.
- The thermostat's spot: which wall, how high, direct sun, nearby supply vents or doors, and the nearest outlet.

At the visit, with the multimeter:
- **R to C voltage** (about 24–28 V AC means a working C wire). If there's no C wire, look for a spare conductor at both ends of the cable.
- The furnace control board's **terminal labels** (W1/W2, Y1/Y2, C) and its **fuse rating**.
- Optional: the current on W, Y and G while each runs, to check the relay contacts.
- **2.4 GHz Wi-Fi signal** at the thermostat's spot.
- The **furnace transformer's VA rating** (on its label, usually 40 VA). The Tab5 adds about 3 VA normally, up to about 8 VA while recharging its battery if it's kept in.
- The **wall opening** (hole or box size) and the old thermostat's outline, for the enclosure design.

## Later: don't buy yet

- [ ] **Home Assistant box for the house**: Home Assistant Green, $199, about 1.7 W idle, storage built in ([home-assistant.io](https://www.home-assistant.io/green/)). Now cheaper and simpler than a reliable Raspberry Pi 5 setup (about $210+ with its power supply, case and SSD).
- [ ] **24 V AC → DC supply for the Tab5.** The Tab5's draw is now measured (see "Notes"), so 1 A at 12 V is plenty. Candidate: Altronix VR1T (24 V AC → 12 V DC, 1 A), ~$33, into the Tab5's 6–24 V DC input ([listing](https://www.surveillance-video.com/power-supply-vr1t.html)). Two cautions:
  - an HVAC transformer at light load can read 26–29 V AC, so check the module's input margin;
  - with a bridge rectifier, the Tab5's ground isn't C: never tie it to C, and don't plug the Tab5 into a grounded computer while it runs on 24 V AC.
- [ ] **If the house has no C wire**: Venstar ACC0410 Add-a-Wire, ~$33 ([SupplyHouse](https://www.supplyhouse.com/Venstar-ACC0410-Add-a-Wire)).
- [ ] **Mechanical low-limit "freeze" thermostat**, wired in parallel on R–W, set to about 45–50 °F, as an independent backup: Honeywell T822K1042 (35–85 °F, no batteries), ~$60 ([listing](https://www.industrialstores.com/product_detail/honeywell-t822k1042-mercury-free-heat-thermostat)). It covers the Tab5 failing to call for heat, not a relay stuck on. Mount it where it reads house air, away from the warm Tab5.
- [ ] **Wall plate / enclosure** for the Tab5, relays and power supply. Nothing ready-made fits, so it'll be 3D-printed. The Tab5 is 128 × 80 × 12 mm, wider than a double-gang plate. A Honeywell 50002883-001 cover plate (~$15–20) can hide the old thermostat's outline.
- [ ] **Final relay board**, depending on the site survey.

## Notes

- **Measured Tab5 power** (2026-10-29, from its built-in battery monitor):
  - **In use** (screen at 10%, Wi-Fi on): **1.3–1.4 W**. Asleep with the screen off draws less (not measured).
  - **Charging the battery**: **+4.05 W** (a fixed 0.51 A), and only until the battery is full.
  - **From the 24 V AC wires**, including about 0.9 W for two relays and converter losses: **about 3 W normally**, and **about 8 W (0.35 A)** while recharging after the battery has been used.
- **The battery (NP-F550, 7.4 V, 2000 mAh) is optional on the wall.** The thermostat runs entirely from the wire power. The battery only covers power cuts, and a gas furnace can't run during one anyway, since its blower and igniter need house power. So all it would keep going is the screen and the clock.
  - The likely choice is to **leave it out** of the wall install. A lithium pack kept full and warm inside an enclosure for years ages faster. Without it, the clock comes back from the internet once Wi-Fi returns, and heating holds its current level meanwhile.
  - Keep it in for the bench.
