# Milestone 4: the bench rig

*Design, 2026-11-18. Owner: pc-chestnut-console. Status: **approved by Dang 2026-11-18**; decided with Dang in three surveys that day. Builder check by a fresh reviewer done (3 points, settled below); mac-chestnut-console to review its side.*

Marks: **Dang** = he decided it; **PC call** = my default, open to change; **Mac** = the Mac agent's side to settle.

## Why

The ENV III sensor, the Unit 4-Relay and the Grove Hub arrived on 2026-11-18. Until now the Tab5 has run the thermostat logic against the virtual house: a pretend room and pretend relays. Milestone 4 swaps those for the real parts on the bench at the apartment, so the thermostat is proven on real hardware (a real temperature reading, real relays clicking, real faults) before anything is wired to the house. The logic, the wall screen and the Home Assistant dashboard stay the same; only what feeds them changes.

## Decided with Dang

1. **Real sensor and relays** on the Tab5. The room temperature and humidity are the apartment's real air; the relays click and light their LEDs when the thermostat calls. **The virtual house stays as a build option** for demos. On real hardware, HA's Simulation tab hides itself (it already does when the sim's entities are missing).
2. **The relays switch nothing** on the bench. Each relay's LED and its click are the indicators. No 24 V AC on the desk, nothing more to buy.
3. **All-in-one layout:** the sensor and the relays both plug into the Tab5's Port A through the Grove Hub. The split design (relays at the furnace) is a separate design pass, once the family's photos show whether the thermostat cable has a spare wire ([site-survey.md](../../../tab5-thermostat/docs/site-survey.md)).
4. **USB-C power** stays. Powering the Tab5 from 24 V AC moves out of milestone 4, to the power decision.
5. **Relay fault:** if the relay unit stops answering (a loose cable, the unit unplugged), a **Relay Fault** problem shows on the Tab5's screen, on the dashboard's System tab and as a phone alert, and **the thermostat stops calling**, like a sensor fault.
6. **Temperature offset set from HA:** a correction Dang can change from the dashboard's System tab, kept across reboots, for when the sensor reads steadily off compared with another thermometer.
7. **Relays off for certain, by cutting Port A's power.** The Tab5 powers Port A only once it's running normally, and cuts it when the relay unit stops answering, so every relay drops even after a crash or a boot loop, or in a virtual-house build. Dang accepted the catch: cutting Port A also powers off the sensor, so a relay fault brings a sensor fault with it.
8. **Done when** all four hold:
   - the heat, cool and fan relays follow the thermostat's calls from the Tab5's screen and from HA, with the minimum run and off times;
   - **unplug tests:** unplugging the sensor raises the sensor fault and stops calling; unplugging the relay unit raises the relay fault;
   - **reboot tests:** every relay is off at boot, after a reboot, and after a power cut in the middle of a call;
   - **a 24-hour run** on real hardware with no errors in the device log.

Dang also confirmed the playback of the PC calls below.

## Non-goals and anti-goals

- **Non-goals:** 24 V AC power; the fake furnace (transformer and lamps); the split design; the top floor; an enclosure; the ENV III's air pressure reading. **No wall-screen restyle** (Dang, 2026-10-29): the screen only gains the relay-fault text, in the existing fault banner.
- **Anti-goal:** a relay left on after a crash, reboot or fault. The relay unit has its own small chip (an STM32) that holds the relays where they were when the Tab5 resets without losing power, so "off at boot" has to be written by the firmware, early.
- **Anti-goal:** a hardware-specific copy of the logic. The logic package stays shared by the virtual house, the host sim, the tests and the real hardware.
- **Anti-goal:** the virtual house's knobs or faults reaching the thermostat while it runs on real hardware. The two are never loaded together.
- **Anti-goal:** personal info in the repo (it's public): no IPs, no photos.

## How it fits

### The package contract

Today's contract (AGENTS.md) has the sim package provide `room_temperature`, `room_humidity` and `relay_heat` / `relay_cool` / `relay_fan` / `relay_ob`. A new **hardware package** provides the same ids from the real parts, so the logic doesn't change. Two additions:

| id | type | real hardware | virtual house |
|---|---|---|---|
| `relay_fault` | binary sensor (problem) | on while the relay unit isn't answering | **Mac:** always off, or a sim fault option that turns it on (useful to test the logic and dashboard without hardware) |
| `temperature_offset` | number, °F | the HA-settable correction (below), applied to the ENV III's reading | **Mac:** the same number, applied to the virtual sensor's reading, so the dashboard and HA's tests always have it |

### The hardware package (PC)

A new file in `tab5-thermostat/hardware/` (**PC call:** `bench-io.yaml`):

- **Port A** gets its own I2C bus on GPIO53 (SDA) and GPIO54 (SCL) (from M5Stack's Tab5 pin map; the builder verifies it). The existing bus on GPIO31/32 is the Tab5's internal one and stays as it is.
- **ENV III:** ESPHome's `sht3xd` platform at 0x44, providing `room_temperature` (°C, with the offset applied) and `room_humidity`. The pressure chip (QMP6988) isn't configured.
- **Unit 4-Relay:** a small driver of our own in `hardware/`, at address 0x26. **Changed while planning (2026-11-18):** M5Stack's official ESPHome component (`unit4relay`) was read and isn't used. Its relay write reads the unit first and, if that read fails, writes back a byte that was never set (which could switch on any relay). It reports a write as done even when it failed, and if the unit doesn't answer at boot it gives up for good, so it can't recover after a Port A power cut. Ours writes all four relays as one byte from the switch states (no read first), reads it back every second to detect a fault, and sets the unit up again after every power-up. **PC call:** relay 1 = W (heat), 2 = Y (cool), 3 = G (fan), 4 = O/B (never switched), labelled on the bench.
- **Port A power:** the board's `external_5v_power` switch (IO expander 1, pin 2, in `hardware/tab5-base.yaml`) is taken to feed Port A; **the first bench step confirms it** (with it off, the relay unit and sensor don't answer; with it on, they do). It starts off at every boot. The hardware package turns it on only once startup has reached the point where the relay unit can be written. The unit's own chip then starts with every relay off, and the package writes the switches' states (all off) to it before the logic can call.
- **Off at boot:** the relay switches keep `restore_mode: ALWAYS_OFF` and `internal: true` as the contract says. **The bench also checks** what the expander does through a Tab5 reset and in ESPHome's safe mode (which stops before most components start). If Port A stays powered through a reset, the package switches it off as the very first thing at boot, and the safe-mode path is tested by hand.
- **No relay logic of its own** beyond off-at-boot and the fault handling below. The logic package's software interlock stays the only thing that decides what's on (ESPHome's `interlock:` option doesn't apply to I2C relays anyway).

### Choosing virtual house or real hardware

**PC call:** one line in `tab5-thermostat.yaml` picks the package, the same way the screen-revision line does: `sim: !include sim/virtual-house.yaml` or the hardware package, never both. Real hardware is the default once milestone 4 is done. The host sim (`main-thermostat-sim.yaml`), the tests and the desktop preview keep using the virtual house or the stub, unchanged.

### Relay fault

- **Detection (PC):** the relay unit counts as not answering when its I2C reads or writes fail for a few seconds in a row (**PC call:** about 5 s, so a single glitch doesn't alert).
- **Who switches what (PC call, from the builder check):** the relay switches always report what the logic last commanded; only the logic package drives them, as the contract says. The hardware package never changes them behind the logic's back; it only sends their states to the unit.
- **The logic on a fault (Mac):** it turns every call off **at once**, like the interlock does, rather than letting a running call finish its minimum run as a sensor fault does (the unit can't be trusted to carry out a call), and doesn't call again until the fault clears. The minimum off times count from the moment of the fault.
- **Making it real (PC):** if the unit still isn't answering about 10 s after the fault starts (**PC call**), the package cuts Port A's power, so every relay drops whatever state the unit's chip was in. It waits a few seconds, powers Port A again, and the unit restarts with every relay off. Once the unit answers steadily, the package sends it the switches' states and the fault clears. Heat and cool are off by then; the fan follows the fan mode, so with Fan On it comes back on (Fan On is Dang's standing choice and harmless to the equipment; agreed with mac-chestnut-console 2026-11-18). If it still doesn't answer, it retries (**PC call:** every 30 s), and the fault stays on.
- **The sensor during a power cut:** it goes off with Port A, so the logic's sensor fault turns on too, and clears once the sensor reads again after power returns.
- **Wall screen (PC):** the existing fault banner gets a relay line, such as "Relay unit not responding. Heating and cooling are paused." (**PC call:** if two faults are on at once, interlock beats relay, and relay beats sensor.)
- **HA (PC):** a fourth alert, **Relay fault**, built exactly like the sensor-fault alert: an alert switch on the System tab (`input_boolean.chestnut_alert_relay_fault`, on by default like the others), the "alerted" helper, the cleared notice, and the entity check covering the new entity id. The System tab shows it. **PC call:** the sensor-fault alert isn't held back during a relay fault; the relay alert's text says the sensor drops with it.

### Temperature offset

- A number entity **Temperature Offset** on the Tab5, in °F, **PC call:** from −5.0 to +5.0 in 0.1 steps, default 0, restored across reboots.
- **PC call (from the builder check):** it lives in the package that provides `room_temperature` (the hardware package on real hardware, the virtual house otherwise), and is added to the reading **before** the logic's sanity checks, so the checked temperature, the wall screen, HA and the history all show the corrected value. **The logic doesn't know it exists:** no new signal between the packages.
- A change of more than 2 °C (3.6 °F) at once looks like any other jump to the sanity checks and is held back for one reading (a few seconds). That's acceptable for a setting changed by hand.
- **Dashboard (PC):** a control for it on the System tab. It also shows on the Tab5's own web page, as ESPHome lists it. Not on the wall screen.

## Testing

- **The existing suites keep passing unchanged:** the logic's unit and scenario tests and the HA tests run against the virtual house, and the wall-screen preview against its stub. Whatever `relay_fault` adds to the logic gets scenario tests on the virtual house (**Mac**).
- **First bench step (PC):** confirm the `external_5v_power` switch feeds Port A, and what the IO expander does through a reset and in safe mode (see the hardware package). The design's Port A handling depends on the answer.
- **A bench test script (PC)**, like `tools/preview/test_device.sh`: flashes the Tab5, reads the boot log, and checks the ENV III and the relay unit are found on Port A, the readings are sane, and every relay is off after boot.
- **The hands-on checks** for Dang go in a short checklist (in the hardware README): relay clicks from the screen and from HA; pull the sensor cable, then the relay cable; reboot from HA mid-call; pull USB mid-call (the battery keeps it running, so the power-cut test is pulling USB *and* holding the power button, or removing the battery first; the builder writes the exact steps).
- **The 24-hour run:** leave it on real hardware for a day; a script collects the device log over that time and reports errors and warnings, and HA's history shows no gaps in the temperature.

## Who does what

- **PC:** the hardware package, the Port A bus, the entry-point switch, the wall-screen banner text, the dashboard (offset control, relay-fault alert and display), HA automations, flashing, the bench test script and checklist.
- **Mac:** the logic's handling of `relay_fault` (cut every call at once, count the minimum off times from the fault), the virtual house's `relay_fault` (**PC call:** a new Sim Fault option, "Relay unit unplugged", so the logic and HA's alert can be tested without hardware) and `temperature_offset`, the contract table in AGENTS.md, and scenario tests for all of it.

## Left to the builder

The exact pin check, the I2C frequency, the fault timing, file and entity names beyond the contract ids, the bench test script's details, and the hands-on checklist's wording.

## Risks to check first

**Checked on the bench 2026-11-18** (a throwaway build, Dang watching the relays):

- **Port A:** GPIO53 is SDA, GPIO54 is SCL. The board's `external_5v_power` switch does feed Port A: off, the unpowered units drag the bus lines low and every I2C attempt fails slowly (about 50 ms each); on, the relay unit (0x26), the ENV III (0x44) and its pressure chip (0x70) answer. **So the firmware never touches Port A's bus while it's off, and doesn't scan it:** a full scan with Port A off blocked the main loop for about 6 s and the watchdog restarted the Tab5.
- **The relay unit:** relay 1–4 match the numbers printed on it (W, Y, G, O/B). Reading register 0x11 back returns the relays mirrored into the LED bits (writing 0x01 reads back 0x11), so the driver compares only the low four bits. The first write right after power-up can go unanswered while the unit starts.
- **The sensor** read 23.6 °C (74.5 °F) and 56% humidity on the desk.
- **Current:** on battery with the screen dark, 0.137 A; with relays 1 and 3 on, 0.263 A, so two relay coils add about 0.13 A (about 1 W). Port A handles it.
- **Restart:** Port A keeps its power through a Tab5 restart, and the relay unit keeps its relays: at the very start of boot, relay 1 was still on. It drops when the board's IO expander setup switches Port A off, well under a second into boot (Dang saw it as instant). The `ALWAYS_OFF` on `external_5v_power` covers this.
- **Recovery (safe) mode:** without a fix, Port A stays powered and **relay 1 stayed on** (Dang watched), because recovery mode never sets up the IO expander. **Fixed and verified:** an `on_safe_mode` hook clears the expander's Port A bit directly through the chip's I2C driver (the board's buses aren't running in recovery mode); with it, relay 1 went dark on entering recovery mode and stayed dark. Updates over Wi-Fi from recovery mode work on this board.

- **The relay component on ESPHome 2026.10.1 and the ESP32-P4:** it's a plain I2C component, so it should build, but check before anything else with a throwaway build that reads the ENV III and clicks each relay once.
- **Port A's 5 V current:** M5Stack doesn't document its limit. Two relay coils (about 90 mA each) plus the sensor is about 200 mA; measure it on the bench with the Tab5's battery monitor or a USB meter.
