# Tab5 Smart Thermostat — Research Notes

*2026-10-28. Covers feasibility, wiring, power and safety for using an M5Stack Tab5 (ESP32-P4) as the wall thermostat at home, controlled locally and integrated with Home Assistant.*

---

## TL;DR

- **Feasible: yes, and not hacky, if it's done the standard way.** Electrically, a low-voltage thermostat is just a set of switches that connect the `R` wire to `W` (heat), `Y` (cool) or `G` (fan). A relay with dry, normally-open contacts does exactly what your old thermostat does inside. Nothing about that is a trick.
- **The Tab5 side is well supported.** ESPHome supports the Tab5 (all three display revisions now have models). ESPHome also has a mature on-device `thermostat` controller with compressor-protection timers, and M5Stack publishes an official Tab5 + Home Assistant panel example.
- **The real work is in four places:**
  1. **Power at the wall.** The Tab5 needs constant power. Your 20+ year-old thermostat almost certainly runs on AA batteries, which usually means there's no `C` (common) wire hooked up.
  2. **Temperature sensing.** The Tab5 has no temperature sensor and runs warm (a reviewer measured 39 °C on the back after 30 minutes at full brightness). You need an external sensor kept away from the device.
  3. **Safe control logic.** The logic has to run on the device itself, not in Home Assistant, and must protect the compressor and fail safe.
  4. **Mounting.** A 3D-printed wall plate or enclosure that also holds the relays and power supply.
- **The one thing that blocks a final design is what's inside the wall at home.** A 10-minute site survey (photos plus a multimeter, checklist in section 4) will answer it for certain. Everything else can be prototyped in the apartment without touching any HVAC.

---

## 0. What public records say about the house (2026-10-28)

*Addresses and listing links are left out on purpose: this repo is public.*

The listing sites (Redfin, Zillow, Realtor.com, Homes.com) block automated access, and the county parcel database was unreachable, so this comes from search snippets and neighboring listings.

**The house:** a 3-story townhouse in Northern Virginia, **built 1999**, about 2,650 sq ft.

**A neighbor on the same street, same era** (built 1998, listed 2026) has **forced-air natural gas heat, central electric AC, and "both HVACs"**, meaning **two separate systems**.

**Elsewhere in the same neighborhood:** some townhomes list **heat pumps**, either for heating and cooling or heat-pump cooling with forced-air heating.

**My inference (to confirm on the visit):**
- **Almost certainly 24 VAC low voltage.** Forced air rules out line-voltage baseboard heat.
- **Two thermostats: confirmed by Dang (2026-10-28).** So there are two systems or zones, probably lower/main and upper level. A common Northern Virginia townhouse layout is a gas furnace + AC for the lower floors and a heat pump or second system for the top floor, often with the air handler in the attic.
- So expect **one conventional system** (R, W, Y, G) and possibly **one heat pump** (R, Y, O/B, G, AUX).
- **Furnace control boards from the 1990s on almost always have a `C` terminal**, so common is available at the furnace even if it was never run to the thermostat.
- 27-year-old HVAC equipment is past its usual 15–20 year life, so at least one system may have been replaced since 1999 and have newer controls.

**Design impact:** plan for 2 thermostats, or 1 Tab5 plus a second, simpler unit. Build the bench rig with 4 relays: W, Y, G, O/B. AUX can reuse the W channel. That covers both a conventional system and a single-stage heat pump with aux heat.

---

## 1. Is the Tab5 a reasonable thermostat?

| Factor | Finding | Impact |
|---|---|---|
| ESPHome support | Original revision (ILI9881C display + GT911 touch, made before Oct 14 2025) has been supported for a while. Newer units use ST7123 or ST7121 controllers: ST7123 display support landed in ESPHome **2026.2.0**, its touch component in **2026.7.0**, and the docs now list `M5STACK-TAB5`, `M5STACK-TAB5-ST7123` and `M5STACK-TAB5-ST7121` models. | ✅ Supported, but **check your revision first** (see section 8). |
| Official HA example | M5Stack's "Tab5 Home Assistant HMI" is an ESPHome + LVGL panel with a Climate page (target temp, mode, fan). It needs ESPHome ≥ 2025.12, and its docs warn it may not support the newer display ICs. | ✅ Good starting point for the UI. |
| Built-in temperature sensor | **None.** The BMI270 IMU's die temperature is useless for room temperature. | ⚠️ Add an external sensor, such as M5Stack ENV IV/ENV Pro or any SHT4x, on Port A. |
| Self-heating | Back reaches about 39 °C after 30 minutes at full brightness. | ⚠️ Keep the sensor thermally separated (below the unit, vented, on a short lead). Dim the screen when idle. |
| Power input | USB-C (5 V) or the **RS485 connector's power input, 6–24 V DC**. **Not 24 V AC.** | ⚠️ Needs a 24 VAC → DC converter (section 5). |
| Power draw | Not published. | ❓ Measure it yourself (section 8). My rough estimate: 2–4 W with the screen on. |
| Wireless | 2.4 GHz Wi-Fi 6 through the ESP32-C6 co-processor. No 5 GHz. | Fine for a thermostat. |
| Expansion | Port A (HY2.0-4P: GND, 5V, G53, G54) is an I²C bus that can share a temperature sensor and an **M5Stack Unit 4-Relay** (I²C address 0x26, rated 250 VAC / 28 VDC, 10 A, ESPHome external component from M5Stack). There's also Ext.Port GPIO, M5-Bus, RS485 and USB-A host. | ✅ Plenty of ways to drive relays. |
| Size and mounting | 128 × 80 × 12 mm, 121 g. 1/4"-20 tripod nut plus threaded inserts. | ✅ Covers a typical old thermostat's footprint. Needs a custom wall plate. |
| Operating range | 0–40 °C. | ✅ Indoors. |

**Verdict:** It's a reasonable, if slightly overpowered, thermostat brain and display. It's not a turnkey product, but every piece needed (display driver, Wi-Fi, LVGL UI, thermostat logic, relay driver, HA integration) already exists in ESPHome. You'd be assembling proven parts, not inventing anything.

---

## 2. How a thermostat works electrically, and why this isn't hacky

```
   FURNACE / AIR HANDLER                         WALL
 ┌───────────────────────────┐            ┌────────────────────┐
 │  120V ──[transformer]──┐  │            │   THERMOSTAT       │
 │                24VAC   │  │            │   (= switches)     │
 │        R (hot) ────────┼──┼─── red ────┼──┬──┬──┬           │
 │                        │  │            │  │  │  │  closing  │
 │        W (heat call) ◄─┼──┼─── white ──┼──┘  │  │  R→W = heat│
 │        Y (cool call) ◄─┼──┼─── yellow ─┼─────┘  │  R→Y = cool│
 │        G (fan call)  ◄─┼──┼─── green ──┼────────┘  R→G = fan │
 │        C (common) ─────┘  │ ─ blue/blk ┼─ (only to POWER     │
 │                           │  (often    │    the thermostat)  │
 └───────────────────────────┘   missing) └────────────────────┘
```

- The furnace has a 24 V AC transformer. `R` is one side and `C` is the other.
- The thermostat never powers the HVAC equipment. It only **connects R to a call wire**. The furnace control board, gas valve, AC contactor and so on do the rest, and **the furnace keeps its own safety devices** (high-limit switch, flame sensor, pressure switches) whatever the thermostat does.
- `C` exists only so the thermostat itself can get power. Old battery thermostats don't need it, so installers often didn't connect it, though there may be a spare wire in the bundle.
- **Replacing those switches with relays (dry, normally-open contacts rated ≥ 30 VAC) is electrically identical** to what the old thermostat does internally. That part needs no clever tricks.

What *would* be hacky, and should be avoided:
- **Power-stealing** (trickling current through `W`/`Y` the way some Nest models do). It's fiddly and can chatter equipment, and the Tab5 draws too much for it anyway.
- Driving 24 VAC with ESP GPIO, transistors or triacs you designed yourself instead of relays.
- Plugging a USB phone charger into 24 VAC "because it seemed to work."
- Running the thermostat logic only in Home Assistant, so that HA going down means no heat.

---

## 3. What could be in your wall

A digital thermostat with a backlight from around 2000 is **almost certainly a 24 VAC low-voltage system**, but which kind matters:

| System | Typical terminals | What it means for this project |
|---|---|---|
| **Gas/oil furnace + central AC** (most likely) | R, W, Y, G, maybe C | Easiest case. 3 relays (W, Y, G). |
| **Heat pump** (common in mild or Southern climates) | R, Y, O/B, G, W2/AUX, E, C | 4–5 relays. The `O/B` reversing valve and the aux-heat rules need care. Still very doable. |
| **Two-stage furnace or AC** | adds W2 / Y2 | More relays. ESPHome supports supplemental stages. |
| **Separate heat and cool transformers** | Rh and Rc (no jumper) | Fine with relays: each relay's common goes to the right R. **Never bridge Rh and Rc.** |
| **Boiler / hot-water heat** | 2 wires (R, W) | Heat only, and no C, so power has to come another way. |
| **Millivolt (wall/floor furnace, gas fireplace)** | 2 wires, no transformer | A relay can switch it, but there's no 24 V to power the Tab5. |
| **Line voltage 120/240 V** (electric baseboard) | Thick wires with wire nuts, often labelled 120/240 V | 🛑 **Stop.** A totally different (and dangerous) project. Unlikely given your description. |

Your apartment may well be a different type from your house. Apartments often have heat pumps, or electric baseboard heat with **line-voltage** thermostats.

---

## 4. Site survey checklist (next visit, or anyone at the house)

**Without opening anything:**
1. Photo of the thermostat front, and the **brand and model number** (often behind a flip-down door or on the back plate once it's pulled off).
2. Does it take batteries? That strongly suggests no C wire is in use.
3. Photo of the **outdoor unit's nameplate** (it tells AC from heat pump) and the **furnace / air handler nameplate**.

**Thermostat cover off.** This is low voltage, but switch off the furnace's service switch or breaker first so a stray short can't blow the furnace fuse:

4. Photo of the terminals with the wires attached: **letters and colors**.
5. **Count every conductor in the cable**, including any cut short and folded back into the wall. Those spares are gold.
6. Read the cable jacket if visible (for example "18/5" means 5 conductors of 18 AWG).

**At the furnace / air handler** (remove the access panel, with power off):

7. Photo of the **low-voltage terminal strip** on the control board (R, C, W, Y, G…) and which thermostat-cable colors land where. **Check whether the spare conductor is connected or just cut off.**
8. Photo of the **transformer label** (its VA rating, usually 40 VA).
9. Note the **fuse rating** on the control board (often 3 A or 5 A).

**Multimeter, power on:**

10. At the thermostat: **R to C** (if there is a C), expected around 24–30 VAC.
11. If no C is connected at the wall but there's a spare conductor: connect it to C at the furnace, then measure R to that spare at the wall.
12. Optional: with the old thermostat calling for heat, measure the current in W with a clamp meter or an in-series meter. That helps size the relays (usually well under 1 A).

**With those photos, I can tell you exactly which design works, with no guessing.**

---

## 5. Getting power to the wall

Ranked from best to worst:

1. **C wire already connected at both ends.** Use it.
2. **Spare conductor in the cable.** Connect it to `C` at the furnace board and you're done. This is common and takes about 15 minutes.
3. **Only 4 conductors (R/W/Y/G), no spare.** Options:
   - **Split design** (section 6B): move the relays to the furnace and use 2 of the existing conductors purely as R/C power for the wall display. This is the cleanest option.
   - Give up `G` (fan-only mode) and repurpose that conductor as `C`. The fan still runs with heat and cool, and HA can't run it on its own.
   - Venstar Add-A-Wire (ACC0410, about $33): installs at the equipment end and multiplexes signals to free a conductor. I haven't verified how it behaves with a relay-based thermostat, so treat it as a fallback.
4. **Pull new 18/8 thermostat cable.** Easy with attic or basement access, hard in a finished wall. 18/8 leaves spares for later.
5. **Separate 5 V supply at the wall** (an in-wall USB outlet or Class 2 transformer nearby). It works, but needs an outlet or new wiring.

**Converting 24 VAC to DC for the Tab5:**
- 24 VAC rectified peaks around **34 V**, and an unloaded transformer can read 28–30 VAC, which peaks near **40 V**. So you need a bridge rectifier, a filter capacitor, and a **buck converter rated ≥ 50 V input**, or a ready-made "24 VAC → 5 V" module with that rating.
- Feed the Tab5 either **5 V via USB-C** or **12 V into the RS485 power input** (spec 6–24 V DC). **Never feed the RS485 input raw rectified 24 VAC** (over spec).
- **Fuse it** (about 0.5–1 A) on the 24 VAC side so a fault in your board can't take out the furnace fuse.
- **Power budget:** a 40 VA transformer supplies about 1.6 A at 24 VAC. The furnace's own load (gas valve, contactor, fan relay) typically leaves plenty of headroom for a 2–4 W display. Confirm with the transformer label and your measured Tab5 draw.
- **Don't charge the NP-F550 battery from the thermostat wires.** If you have the Tab5 Kit, leave the battery out for the wall install, or limit charging. A charging battery can multiply the draw.

---

## 6. Architecture options

### A. All-in-one at the wall
The Tab5 *is* the thermostat: it runs ESPHome's `thermostat` logic, drives relays (Unit 4-Relay on Port A, or a GPIO relay board) mounted behind it, reads an external SHT4x, and is powered from R/C through the converter.
- ➕ One device, fully local, and closest to what you pictured.
- ➖ UI and HVAC control share one fairly complex firmware (LVGL, Wi-Fi co-processor), so a UI crash briefly stops control. Needs a C wire and room behind the plate for relays and the converter.

### B. Split: relay "brain" at the furnace, Tab5 at the wall
A small, boring ESP32 relay board at the furnace runs the thermostat logic, wired to the furnace terminals with short jumpers, where 24 VAC and C are right there. The Tab5 on the wall is the display and sensor, powered by 2 of the existing thermostat conductors (R/C). The temperature reaches the brain over Wi-Fi via ESPHome `packet_transport` (UDP, direct device-to-device, no HA needed) or through HA.
- ➕ Works even with a 2- or 4-wire cable and no C. The HVAC-controlling part is tiny and rock-solid, and you can update or reboot the Tab5 freely.
- ➖ Two devices, and the brain needs a fallback if it loses the wall temperature (for example a return-air sensor, or going idle plus an alert).

### C. Commercial thermostat + Tab5 as the UI
For example a Honeywell T6 Pro Z-Wave, an Ecobee (local via HomeKit), or a Venstar with its local API. The Tab5 just controls it through HA.
- ➕ Zero HVAC DIY. ➖ The Tab5 isn't really the thermostat. This is the fallback if the site survey turns up something awkward.

**My take:** A is what you described, and it's a fine first prototype because it exercises every piece. **Pick A or B for the house after the site survey.** If there's a C or spare wire, A is reasonable. If there isn't, B is the cleaner, non-hacky answer.

---

## 7. Safety and reliability requirements (non-negotiable for the real install)

- **Logic runs on the device** (ESPHome `thermostat`). HA is only for remote control, schedules and history. HA's `generic_thermostat` runs inside HA, so don't use it as the primary controller.
- **Relays are normally-open with `restore_mode: ALWAYS_OFF`**, so losing power or rebooting means "call for nothing."
- **Compressor protection:** `min_cooling_off_time` / `min_cooling_run_time` (around 5 minutes is a common starting point; follow the equipment manual) and **`startup_delay: true`** so a reboot or power blip can't short-cycle the compressor. Use furnace min run/off times too, since short-cycling gas furnaces is also bad.
- **Heat/cool interlock:** heat and cool must never be energized together. Enforce it beyond the thermostat logic. ESPHome GPIO switches support `interlock:`; for I²C relays, enforce it in config.
- **Heat pump only:** handle the `O/B` reversing-valve polarity and aux/emergency heat rules correctly.
- **Sensor sanity checks:** if the temperature reading goes missing or implausible, stop calling and raise an alert.
- **An independent backup** (my suggestion): a cheap mechanical low-limit "freeze" thermostat wired in parallel on R–W, set to about 45–50 °F. If your device dies in winter while you're away, the pipes don't freeze. It's standard practice for vacation homes.
- **Keep the old thermostat** so you can swap back in five minutes.
- **Handling:** 24 VAC Class 2 is low-risk to work on, but shorting R to C blows the furnace board fuse, so switch the furnace off before touching wires. Anything line-voltage means stop.

---

## 8. What you can do now from the apartment (no HVAC needed)

1. **Identify your Tab5 display revision.** In an I²C scan, GT911 at **0x14** means the original model (ILI9881C). **0x55** means ST7123 or ST7121; try `M5STACK-TAB5-ST7123` first and switch to `-ST7121` if the screen stays blank but touch works.
2. **Set up Home Assistant + ESPHome** on your PC (Docker or a VM is fine for development) and flash the Tab5 with a minimal ESPHome config. Then try M5Stack's HMI example.
3. **Measure the Tab5's power draw** with a USB-C power meter at idle, dim, and full brightness. That number settles the power-supply design.
4. **Build the bench rig.** This is literally the final electrical setup with the furnace swapped for lights:
   - A **plug-in 24 VAC Class 2 wall transformer** (no line-voltage wiring needed). It stands in for the furnace transformer.
   - A relay board (Unit 4-Relay or a GPIO relay module) switching **24 VAC indicator LEDs or small 24 VAC relay coils** labelled W / Y / G / (O/B). They stand in for the furnace.
   - An external SHT4x / ENV unit on Port A.
   - A 24 VAC → 5 V/12 V converter powering the Tab5 from that transformer.
5. **Write the ESPHome thermostat config** (timers, interlock, `startup_delay`, sensor sanity checks) and **test every failure mode on the bench**: Wi-Fi off, HA off, power cut mid-cycle, sensor unplugged, reboot loops.
6. **Design the UI** in LVGL: big setpoint, mode, fan, humidity, schedule.
7. **Look at the apartment thermostat** if you're curious (take the cover off and photograph it), but don't modify a rental's HVAC without the landlord's OK. It may also be a different system type than your house.

---

## 9. Open questions

- What's in the wall at home? (Site survey, section 4.) Can someone at the house take the photos before your next visit?
- Climate and region: heat pump, or furnace + AC?
- Which Tab5 do you have (bare unit or Kit with battery), and which display revision?
- Do you already run Home Assistant anywhere?
- What do you want it to do beyond basic control: schedules, remote sensors in other rooms, occupancy, weather, voice (the Tab5 has mics and a speaker)?

---

## 10. Bench prototype shopping list (2026-10-28)

Prices are rough (2026, USD) and change often.

**Buy now: the bench rig** (about $80–100 total)

| Item | Why | ~Price |
|---|---|---|
| M5Stack **Unit ENV IV** (SHT40 + BMP280) | Temperature and humidity sensor. ESPHome supports it natively (`sht4x`). | $8–10 |
| M5Stack **Unit 4-Relay** (U097) | Switches W / Y / G / O-B. I²C at 0x26, with an ESPHome component from M5Stack. | $13–16 |
| M5Stack **Grove Hub** (1-to-3) + one **50 cm Grove cable** | Port A is a single connector; the hub lets the sensor and relays share it, and the long cable keeps the sensor away from the Tab5's heat. | $5 |
| **24 V AC plug-in transformer**, 20–40 VA | Stands in for the furnace transformer. **Must say "24V AC" output**; many look-alikes are 24 V DC. | $15 |
| **24 V AC/DC LED indicator lights**, 4 colors | Stand in for the furnace: red = heat (W), blue = cool (Y), green = fan (G), yellow = heat-pump reversing valve (O/B). | $10 |
| **Wago 221 lever connectors** + a few feet of **18-gauge thermostat wire** | Clean, solder-free bench wiring, the same kind as a real install. | $15–20 |
| **Inline fuse holder + 1 A fuse** | Same habit as the real install: fuse the 24 V AC side. | $5 |
| **USB-C power meter** | Measures the Tab5's draw, which decides the power-supply design. | $15 |

**Buy before the house visit**
- **Multimeter** with AC volts and continuity (about $30), for the site survey.

**Don't buy yet**
- **24 V AC → DC supply for the Tab5:** wait until the Tab5's draw is measured. Likely a bridge rectifier, a filter capacitor, and a buck converter rated ≥ 50 V input (for example a Pololu D36V28F5), or a ready-made module.
- **Home Assistant box:** prototype on a Home Assistant VM on Proxmox; it being on and off doesn't matter for the bench. Buy the house box later: **Home Assistant Green**, $199 after the 2026 price increases, about 1.7 W idle, or a Pi 5 (4 GB) at about $127 bare plus storage and power supply. Against a PC idling around 50–80 W, it pays for itself in roughly 2–3 years, and it has to be at the house anyway.
- **Final install parts:** wall plate or enclosure, mechanical freeze backup thermostat, final relay board. These depend on the site survey.

**Notes**
- With everything on, the 4-Relay unit draws a few hundred mA from Port A's 5 V. In practice only 2 relays are on at once (heat or cool, plus fan), but check it on the bench.
- ESPHome's `interlock:` only works with GPIO switches. With the I²C relay unit, enforce "never heat and cool together" in config.

---

## Sources

- [M5Stack Tab5 product docs](https://docs.m5stack.com/en/core/Tab5): specs, RS485 6–24 V input, ports, display revision changelog
- [M5Stack Tab5 Home Assistant HMI example](https://docs.m5stack.com/en/homeassistant/applications/dashboard/tab5_ha_hmi)
- [ESPHome MIPI DSI display driver](https://esphome.io/components/display/mipi_dsi/): Tab5 models
- [ESPHome ST7123 touchscreen](https://esphome.io/components/touchscreen/st7123/)
- [ESPHome 2026.2.0](https://community.home-assistant.io/t/esphome-2026-2-0-faster-builds-leaner-runtime-esphome-smart-home-made-simple/1022093) / [2026.7.0 changelog](https://esphome.io/changelog/2026.7.0.html)
- [ESPHome thermostat climate component](https://esphome.io/components/climate/thermostat/)
- [ESPHome packet_transport](https://esphome.io/components/packet_transport/) and [UDP](https://esphome.io/components/packet_transport/udp/)
- [M5Stack Unit 4-Relay ESPHome component](https://docs.m5stack.com/en/homeassistant/components/switch/unit_4relay)
- [Tao of Mac: M5Stack Tab5 review (July 2026)](https://taoofmac.com/space/reviews/2026/07/18/1920): heat, display revisions, ESPHome support
- [CNX Software Tab5 review](https://www.cnx-software.com/news/m5stack/page/5/?amp=1)
- [HA community: M5Stack Tab5 thread](https://community.home-assistant.io/t/m5stack-tab5/888543)
- [Sonoff THR320D ESPHome device page](https://devices.esphome.io/devices/sonoff-thr320d/): interlock caveat
- [HA community: short-cycling discussion](https://community.home-assistant.io/t/local-control/436862?page=3)
- [Hackaday: ESPThermostat](https://hackaday.io/project/182191-espthermostat): prior art, ESP32 + 4 relays + 24 VAC→5 V
- [Thermostat wire color guide (Aire Serv)](https://aireserv.com/about/blog/2020/february/the-thermostat-wire-color-code-you-need-to-know)
- [Inspectapedia: C wire](https://inspectapedia.com/heat/C-Wire-Common-Thermostat.php)
- [Venstar ACC0410 Add-A-Wire](https://www.supplyhouse.com/Venstar-ACC0410-Add-a-Wire)
- [Arduino forum: smart thermostat and transformers](https://forum.arduino.cc/t/smart-thermostat-and-transformers/413996): 24 VAC → DC approach
- [raspberry.tips: HA hardware comparison 2026](https://raspberry.tips/en/raspberrypi-tutorials/home-assistant-hardware-comparison-2026-green-blue-yellow-vs-raspberry-pi): HA Green $199, ~1.7 W idle; Pi 5 prices
- [Matter Alpha: HA Green price hike](https://www.matteralpha.com/news/home-assistant-green-price-hiked-here-s-why)
- [RobotShop: M5Stack 4-Relay Unit](https://www.robotshop.com/products/m5stack-4-relay-unit)
