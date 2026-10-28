# Main Thermostat console UI: design (milestone 3, functional version)

*2026-10-28. Status: **draft, waiting for Dang's approval**. Owner: pc-chestnut-console. Builder check: mac-chestnut-console.*

## Intent

The Tab5 on the wall *is* the Main Thermostat. Its screen is what the family touches every day, so it has to be obvious at a glance, hard to misuse, and pleasant to look at as a console, not a dev-board demo. This is the **functional version**: the full layout and visual language, wired to the real thermostat entities. A later polish pass (animations, a dial, extra pages) can follow without restructuring.

The Tab5 can't render Home Assistant's own dashboard (it has no browser). Phones and PCs use HA's built-in thermostat card; the Tab5 draws its own UI with ESPHome LVGL.

## Goals

- At a glance: room temperature, target, what the system is doing right now, humidity, outdoor temperature, time.
- Change the target with big − / + buttons. Change mode, fan and Comfort/Eco with one tap. See the schedule state, see when a manual change is holding, and resume the schedule.
- Readable in light and dark, with a theme toggle that also follows sunset and sunrise.
- Works fully when Home Assistant or Wi-Fi is down (only the outdoor reading goes blank).

## Non-goals (for this version)

- The schedule-editing screen (milestone 2 runs the schedule on the device and makes it editable from HA and the web page; a touch editor comes later, owned by the PC), settings pages, top-floor control, voice, animations, a drag dial.
- Home Assistant's dashboard on the Tab5.

## Anti-goals

- Anything a family member could change by accident (a bump or a kid's poke while the screen is dim).
- Text that's hard to read in either theme (Dang flagged this in mockup v2).
- UI code that reaches into thermostat logic: the UI only reads and commands the contract entities.

## Visual language

**Source:** the Co2 style reference in [`tab5-thermostat/docs/design/`](../../../tab5-thermostat/docs/design/DESIGN.md): an editorial look with ink on paper, hairline rules, pale washes, saturated colors reserved for categories, and no shadows or gradients.

**Adaptations (decided with Dang through mockups v2–v4):**

- **Fonts:** the Co2 fonts are commercial, so we use the substitutes listed in the docs, both free on Google Fonts and compiled into the firmware by ESPHome's `font:` component.
  - **Inter** (400, 500): all numbers, labels and controls.
  - **Space Grotesk** (500): only the "Main Thermostat" title (Dang's pick over Inter, Fraunces and Instrument Serif).
  - The Co2 display serif isn't used: its thin weight read poorly on the screen.
- **Category colors become HVAC status colors:** heating Market Orange `#ff7b1b`, cooling Climate Blue `#4098ff`, fan only Land Teal `#00b595`, idle/off Muted Steel `#8b8d90`. They appear only as the small status marker and the history line, never as large fills.
- **Selected state:** Mint Wash `#dbffe7` with ink text, as the docs reserve mint for selected states.
- **Light-mode contrast:** a deeper canvas plus a 1 px edge on every card. Plain Co2 white-on-`#f9f9f9` made the cards hard to see (Dang, mockup v3).
- **Dark theme:** derived by us from the palette (the docs define light only).

### Color tokens

| Token | Light | Dark | Use |
|---|---|---|---|
| page | `#e9ecf0` | `#181b22` | Screen canvas |
| card | `#ffffff` | `#1f232d` | Card surface |
| card edge | `#d3d8de` | `#2a2f3a` | 1 px card border |
| ink | `#181b22` | `#ffffff` | Primary text and numbers |
| sub | `#585c64` | `#9a9ca1` | Labels and secondary text |
| rule | `#d9d9d9` | `#2e333e` | Dividers |
| emphasis card | `#1f232d` | `#2b303c` | Target card |
| on-emphasis / sub | `#ffffff` / `#a3a6ab` | `#ffffff` / `#9a9ca1` | Text on the target card |
| emphasis button | `#f5f5f5`, ink glyph | `#3a4050`, white glyph | − / + buttons |
| pill / edge | `#eef0f3` / `#d3d8de` | `rgba(255,255,255,.07)` / none | Unselected mode and fan pills |
| selected pill / edge / text | `#dbffe7` / `#9fd9b4` / ink | `#1e3b33` / `#2f6a55` / `#dbffe7` | Selected pill. Dark is a deep mint, since bright mint glared on the dark theme (Dang) |
| humidity card / edge | `#dff9ff` / `#b8e6f2` | `rgba(223,249,255,.10)` / none, text `#dff9ff` | Humidity card |
| history line | `#4098ff` | `#4098ff` | Temperature line |

## Layout

Landscape, 1280×720. LVGL `rotation: 270` (the panel is natively portrait), set in `ui/`. The sizes below are device pixels, scaled from mockup v4 (factor ≈1.95). The builder may adjust ±10% to fit the real fonts.

```
┌──────────────────────────────────────────────────────────────────────┐
│ Main Thermostat  Tue, Oct 28     Return · Comfort until 10:30 pm  7:42 pm (☾) │
├───────────────────────────────────────┬──────────────────────────────┤
│ Inside now                 ■ Heating  │  Target  (dark card)         │
│                      to 72° · 18 min  │   [−]        72°        [+]  │
│  71°                                  ├──────────────┬───────────────┤
│                                       │ Outside      │ Humidity      │
│ ~~~~~~ temperature line ~~~~~~~ - - - │ 48°  Cloudy  │ 42% Comfort.  │
│ 6 am        Dashed line: target   Now │              │ (cyan card)   │
├───────────────────────────────────────┴──────────────┴───────────────┤
│ Mode (Off)(Heat)(Cool)(Auto) │ Fan (Auto)(On) │ (Comfort)(Eco)            │  strip ~90
└──────────────────────────────────────────────────────────────────────┘
```

- Outer padding ~26 px, gaps ~18 px, card radius ~24 px.
- Main area: two columns at ~1.32 : 1. The right column is the target card (~57%) over two small cards (~43%).

All fonts render with **4-bit anti-aliasing** (`bpp: 4`). At ESPHome's default 1 bit, thin strokes broke up on the Tab5 (Dang). Sizes were raised after seeing it on the wall.

| Element | Font / size (device px) |
|---|---|
| Title | Space Grotesk 500, 40 |
| Date, clock | Inter 400, 27 / 30 |
| Labels ("Inside now", "Target", card captions) | Inter 400, 27–30 (all grey text 27) |
| Room temperature | Inter 400, 172, tight tracking (≈ −0.045 em); the ° sign smaller and raised |
| Target | Inter 400, 112 (a range like "67–77°": 78) |
| Small-card values | Inter 400, 56 |
| Pills | Inter 400, 28, height ~55, fully rounded |
| − / + buttons | ~82×82, radius ~16, glyph ~46 |

## Components and behavior

**Top bar**
- Title, today's date, and a 12-hour clock from the RTC/SNTP time.
- **Schedule status** on the right, before the clock *(Dang: in the top bar)*:
  - Following the schedule: the current period and when it ends, for example "Return · Comfort until 10:30 pm".
  - Holding a manual change (target, Eco temperature, or Comfort/Eco; a hold lasts until the next period starts, per milestone 2): "Holding until 10:30 pm" next to a **Resume** pill. Tapping it ends the hold. It was shortened from "Resume schedule" so the larger text fits.
- Theme toggle: a pill with a moon icon in light mode and a sun icon in dark.

**Room card**
- "Inside now" with the room temperature in whole °F, from `checked_temperature`.
- Status, top right: a colored marker, the action word (Heating, Cooling, Fan, Idle, Off) from the climate entity's current action, and a subline:
  - while running: "to 72° · 18 min so far" (minutes since the current action began);
  - still running after a switch to another mode: "Finishing up · stops soon". Milestone 2 lets the furnace or AC finish its minimum run first (up to a few minutes). *(Dang asked why "Heating" stayed after he tapped Cool. On the dev stand-in, the action now follows the mode at once.)*
  - idle: the held target or range;
  - off: "System is off".
- **Temperature line** *(my call: Dang kept the line by not objecting; the default from mockup v3)*:
  - a rolling 12 hours, sampled every 10 min (72 points) and kept in RAM, so it restarts after a reboot;
  - drawn in Climate Blue, with the target as a dashed line;
  - axis labels for the start time and "Now".

**Target card**
- **One target in every mode** *(Dang, 2026-10-28: replaces the two-setpoint Auto from mockup v5)*:
  - One number ("Target") sits between the − / + buttons, in Heat, Cool and Auto alike.
  - Each tap moves the target by 1 °F, clamped to the climate's min/max (the range and step come from the milestone 2 spec).
  - In Auto the thermostat decides to heat or cool toward the target. The anti-flip-flop gap is hidden in milestone 2: ESPHome's thermostat is two-point under the hood, and milestone 2 derives both points from the single target.
- **Comfort vs Eco on the card** *(Dang: show the Eco number big)*:
  - In Comfort, the big number is the Comfort target, labeled "Comfort target".
  - In Eco, the big number is the **Eco temperature** (`effective_target`). In Auto, when Eco widens the range (scheduled Eco, or an Eco level hold), it shows the band edges, e.g. "67–77°". Plain Auto and a temperature hold keep a hidden ±1 around one number, so they show that number. *(Milestone 2's hold model: Comfort/Eco pressed by hand holds the level, − / + holds a temperature.)* It's labeled "Eco target", with "Comfort 72°" in small text.
  - **− / + in Eco change the shown Eco temperature for now** *(Dang)*. Tapping + on 68° writes 69 to `set_target`, which milestone 2 holds until the next period. Comfort isn't changed.
- **Off mode:** the card shows "Off" and the − / + buttons are hidden.
- The number updates instantly. The new setpoint goes to the climate entity once there's been no tap for ~1.5 s, so a run of taps is one change *(my call)*.

**Outside card**
- Temperature and condition from a Home Assistant weather entity (the builder picks the onboarding default, likely `weather.forecast_home`).
- Shows "—" (and a blank condition) whenever no Home Assistant API client is connected, rather than a stale value. HA only resends an attribute when it changes, so a time-based staleness rule would blank valid readings.

**Humidity card**
- `room_humidity` in %.
- Caption *(my call)*: "Dry" below 30%, "Comfortable" 30–60%, "Humid" above 60%.

**Controls strip**
- Three pill groups, separated by hairline dividers:
  - **Mode:** Off / Heat / Cool / Auto
  - **Fan:** Auto / On
  - **Comfort / Eco** *(milestone 2 replaced presets with this; placement is my call)*. Eco lets the house drift the money-saving way (default 4 °F, set in HA or on the web page). Selecting either one manually starts a hold.
- One tap selects, and the selected pill shows Mint Wash.
- Eight pills in three groups fit in 1228 px at ~20 px horizontal padding.

**Idle stages** *(Dang, after seeing it on the wall)*
- **In use: 10%** backlight. Full brightness was too bright on the wall.
- After **30 s** without a touch: **dim**, to about a tenth of the in-use light.
- After another **30 s**: **backlight off and LVGL paused**. The thermostat keeps running, holding the temperature and following the schedule.
- **The first tap on a dimmed or sleeping screen only wakes it** (back to the in-use level). The tap is swallowed and doesn't press anything.
- After a reboot the screen starts at the in-use level.
- Both levels are adjustable entities in HA and on the web page: **Screen Brightness** (default 10) and **Dim Brightness** (default 4). They're light brightness values, which ESPHome gamma-corrects (x^2.8): 4% gives about a tenth of the light of 10%, while a literal 1% would be dark.
- The Tab5's backlight bottoms out not far below the in-use level, so the dim stage also lays a 70% black scrim over the picture.

**Motion** *(Dang tried fades on the wall, then asked for none on the idle stages and snappier buttons)*
- **Dim, sleep and wake switch at once.** No fades: on the Tab5 a full-screen fade plays at only about 4 frames per second (a full redraw takes about 0.23 s).
- **Buttons and pills** press in by 3 px the moment they're touched, then ease back over 80 ms (ease out). This replaces LVGL's default grow, which also eased in over 80 ms. Colors switch at once (a pill lighting up).
- **A tap's result shows right away:** the screen refreshes as soon as a button's action runs, without waiting for the 250 ms refresh.
- **Theme changes stay instant.**

**Theme** *(Dang)*
- The toggle switches light/dark immediately.
- It also switches automatically: dark at sunset, light at sunrise, using ESPHome's `sun` component.
- The house's latitude/longitude go in `secrets.yaml`. Never commit them: the repo is public.
- A manual tap overrides the automatic choice until the next sunrise or sunset.
- The current theme survives reboots. Once the clock is valid after a boot, the theme catches up to the sun once, unless the toggle was used since boot (a power cut may have spanned sunset or sunrise).

**Sensor fault** *(milestone 2: a bad sensor stops heating/cooling and raises an alert)*
- The room temperature shows "—".
- The status marker turns Muted Steel with "Paused". A fault always wins over the climate's action: under a latched interlock, ESPHome's thermostat can still report heating with the relays off.
- If a heat or cool call is still on (after a sensor fault, milestone 2 lets it finish its minimum run), the subline says "Finishing up · stops soon", so the running furnace or AC doesn't look stuck. *(Mac agent's suggestion.)*
- A Signal Yellow `#f8e645` banner with ink text replaces the temperature line: "Temperature sensor problem. Heating and cooling are paused." The docs reserve Signal Yellow for a single high-attention grouping *(my call)*.
- The banner clears by itself when milestone 2 resumes.

**Offline:** everything above works without Home Assistant or Wi-Fi, except the outside card.

## Entity bindings

From the milestone 2 spec (`mac/thermostat-logic` @ cbeebb8, "Entities the screen and HA can use"). The screen **never** writes the climate's setpoints and never touches `relay_*`. Until milestone 2 merges, the UI builds against a stand-in package with the same ids (`ui/dev/contract-stub.yaml`, dev only). The ids are fixed, so the swap is a one-line package change. *(builder check Q1, my call)*

| Screen element | Reads | Writes |
|---|---|---|
| Room temperature | `checked_temperature` (°F, the value the thermostat acts on); "—" when unknown | |
| Status marker / word | `main_thermostat` action (heating / cooling / idle) and mode. Fan state from **`call_fan`**, never the climate action | |
| Status subline | running: "to {target} · {N} min so far", or "Finishing up · stops soon" when the mode no longer calls for it (N timed on the screen from when it saw the action change: exact and offline. A float `action_since` is only ~128 s precise, so the screen doesn't read it); idle and off target: `call_wait_reason` (for example "Waiting · short-cycle protection"); idle and on target: "holding {target}"; mode Off: "System is off", or "System is off · fan on" when `call_fan` | |
| Big target number | `effective_target`; in Auto with Eco and no hold, "`effective_low`–`effective_high`" | `set_target` ±1, clamped 50–90 (debounced). Milestone 2 makes this a hold. |
| Target label | `comfort_level`: "Comfort target" or "Eco target", plus "Comfort {comfort_target}°" in small text while Eco | |
| Comfort / Eco pills | `comfort_level` (select) | `comfort_level` (milestone 2 makes a manual change a hold) |
| Mode pills | `main_thermostat` mode: Off / Heat / Cool / Auto = OFF / HEAT / COOL / HEAT_COOL | `main_thermostat` mode |
| Fan pills | `main_thermostat` fan mode: AUTO / ON | `main_thermostat` fan mode |
| Schedule status (top bar) | `schedule_status` (the ready-made text, used as is); `schedule_hold` controls the Resume pill; `schedule_enabled` off: "Schedule off" with no pill | `resume_schedule` |
| Temperature line | samples of `checked_temperature`; the dashed line is `effective_target` (the band centre in Auto) | |
| Humidity | `room_humidity`; "—" when unknown | |
| Outside | HA weather entity `weather.forecast_home`, imported; "—" when no HA client is connected | |
| Sensor fault banner | `sensor_fault` | |
| Interlock fault banner | `interlock_fault` | none on the wall *(my call: it's a latched safety fault; clear it from HA or the web page with `clear_interlock_fault`)* |

**Extra states** *(from the builder check; wording is my call)*:
- **Interlock fault:** a Signal Yellow banner: "Heating and cooling were both requested, so the system stopped. Clear it in Home Assistant once it's checked."
- **Clock not set:** the top bar shows the `schedule_status` text ("Schedule paused: clock not set") in sub color.
- **Schedule off:** "Schedule off" in sub color, with no Resume pill.
- **Fan running with nothing else:** a teal marker with "Fan".

## Constraints

- ESPHome 2026.10.x, LVGL, the Tab5 ST7123 panel, landscape via LVGL software rotation. Prefer partial redraws: avoid full-screen invalidation on every tick.
- The package contract in AGENTS.md, extended by the milestone 2 entity table above. The UI never touches `relay_*` (internal in milestone 2) or the climate's low/high setpoints directly.
- Flash budget: compile fonts with glyph subsets (digits, °, %, the needed letters), especially the 164 px and 105 px sizes.
- No secrets or location in git.

## Left to the builder

- How to switch themes in LVGL. For example, two sets of `style_definitions` re-applied to a list of widgets, or `lvgl.widget.update` color updates in one script.
- The exact chart widget and history storage for the temperature line.
- File split inside `tab5-thermostat/ui/` (for example `theme.yaml`, `fonts.yaml`, `console.yaml`), replacing `hello.yaml`.
- The precise ±10% sizing once the fonts render on hardware.
