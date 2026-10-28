# Main Thermostat console UI: design (milestone 3, functional version)

*2026-10-28. Status: **draft, waiting for Dang's approval**. Owner: pc-chestnut-console. Builder check: mac-chestnut-console.*

## Intent

The Tab5 on the wall *is* the Main Thermostat. Its screen is what the family touches every day, so it has to be obvious at a glance, hard to misuse, and pleasant to look at as a console, not a dev-board demo. This is the **functional version**: the full layout and visual language, wired to the real thermostat entities. A later polish pass (animations, a dial, extra pages) can follow without restructuring.

The Tab5 can't render Home Assistant's own dashboard (it has no browser). Phones and PCs use HA's built-in thermostat card; the Tab5 draws its own UI with ESPHome LVGL.

## Goals

- At a glance: room temperature, target, what the system is doing right now, humidity, outdoor temperature, time.
- Change the target with big − / + buttons. Change mode, fan and preset with one tap.
- Readable in light and dark, with a theme toggle that also follows sunset and sunrise.
- Works fully when Home Assistant or Wi-Fi is down (only the outdoor reading goes blank).

## Non-goals (for this version)

- Editing the weekly schedule on the screen (milestone 2 runs the schedule on the device; how it's edited is still open), settings pages, top-floor control, voice, animations, a drag dial.
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
| selected pill / edge | `#dbffe7` / `#9fd9b4` | `#dbffe7` / none | Selected pill (ink text in both themes) |
| humidity card / edge | `#dff9ff` / `#b8e6f2` | `rgba(223,249,255,.10)` / none, text `#dff9ff` | Humidity card |
| history line | `#4098ff` | `#4098ff` | Temperature line |

## Layout

Landscape, 1280×720. LVGL `rotation: 270` (the panel is natively portrait), set in `ui/`. The sizes below are device pixels, scaled from mockup v4 (factor ≈1.95). The builder may adjust ±10% to fit the real fonts.

```
┌──────────────────────────────────────────────────────────────────────┐
│ Main Thermostat  Tuesday, October 28                 7:42 pm   (☾)  │  top bar  ~50
├───────────────────────────────────────┬──────────────────────────────┤
│ Inside now                 ■ Heating  │  Target  (dark card)         │
│                      to 72° · 18 min  │   [−]        72°        [+]  │
│  71°                                  ├──────────────┬───────────────┤
│                                       │ Outside      │ Humidity      │
│ ~~~~~~ temperature line ~~~~~~~ - - - │ 48°  Cloudy  │ 42% Comfort.  │
│ 6 am        Dashed line: target   Now │              │ (cyan card)   │
├───────────────────────────────────────┴──────────────┴───────────────┤
│ Mode (Off)(Heat)(Cool)(Auto) │ Fan (Auto)(On) │ (preset group: pending M2) │  strip ~90
└──────────────────────────────────────────────────────────────────────┘
```

- Outer padding ~26 px, gaps ~18 px, card radius ~24 px.
- Main area: two columns at ~1.32 : 1. The right column is the target card (~57%) over two small cards (~43%).

| Element | Font / size (device px) |
|---|---|
| Title | Space Grotesk 500, ~39 |
| Date, clock | Inter 400, ~21 / ~25 |
| Labels ("Inside now", "Target", card captions) | Inter 400, ~21–23 |
| Room temperature | Inter 400, ~164, tight tracking (≈ −0.045 em); the ° sign smaller and raised |
| Target | Inter 400, ~105 |
| Small-card values | Inter 400, ~50 |
| Pills | Inter 400, ~23, height ~55, fully rounded |
| − / + buttons | ~82×82, radius ~16, glyph ~46 |

## Components and behavior

**Top bar**
- Title, today's date, and a 12-hour clock from the RTC/SNTP time.
- Theme toggle: a pill with a moon icon in light mode and a sun icon in dark.

**Room card**
- "Inside now" with the room temperature in whole °F. It comes from `room_temperature` (°C, converted for display).
- Status, top right: a colored marker, the action word (Heating, Cooling, Fan, Idle, Off) from the climate entity's current action, and a subline:
  - while running: "to 72° · 18 min so far" (minutes since the current action began);
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
  - In Auto the thermostat decides to heat or cool toward the target. The anti-flip-flop gap is hidden logic in milestone 2, not shown on screen.
- **Off mode:** the card shows "Off" and the − / + buttons are hidden.
- The number updates instantly. The new setpoint goes to the climate entity once there's been no tap for ~1.5 s, so a run of taps is one change *(my call)*.

**Outside card**
- Temperature and condition from a Home Assistant weather entity (the builder picks the onboarding default, likely `weather.forecast_home`).
- Shows "—" when HA is unreachable.

**Humidity card**
- `room_humidity` in %.
- Caption *(my call)*: "Dry" below 30%, "Comfortable" 30–60%, "Humid" above 60%.

**Controls strip**
- Three pill groups, separated by hairline dividers:
  - **Mode:** Off / Heat / Cool / Auto
  - **Fan:** Auto / On
  - **Preset:** *pending*. Dang said the Home / Away / Sleep pills from mockup v5 don't match what he decided in the milestone 2 brainstorm, so this group waits for the milestone 2 spec.
- One tap selects, and the selected pill shows Mint Wash.
- If a third group lands, pills may narrow (padding ~20 px) to fit in 1228 px.

**Idle dimming** *(Dang)*
- After 30 s without a touch, the backlight dims to ~10%.
- **The first tap on a dimmed screen only wakes it**: the tap is swallowed and doesn't press anything. The screen returns to full brightness.

**Theme** *(Dang)*
- The toggle switches light/dark immediately.
- It also switches automatically: dark at sunset, light at sunrise, using ESPHome's `sun` component.
- The house's latitude/longitude go in `secrets.yaml`. Never commit them: the repo is public.
- A manual tap overrides the automatic choice until the next sunrise or sunset.
- The current theme survives reboots.

**Sensor fault** *(milestone 2: a bad sensor stops heating/cooling and raises an alert)*
- The room temperature shows "—".
- The status marker turns Muted Steel with "Paused".
- A Signal Yellow `#f8e645` banner with ink text replaces the temperature line: "Temperature sensor problem. Heating and cooling are paused." The docs reserve Signal Yellow for a single high-attention grouping *(my call)*.
- The banner clears by itself when milestone 2 resumes.

**Offline:** everything above works without Home Assistant or Wi-Fi, except the outside card.

## Constraints

- ESPHome 2026.10.x, LVGL, the Tab5 ST7123 panel, landscape via LVGL software rotation. Prefer partial redraws: avoid full-screen invalidation on every tick.
- The package contract in AGENTS.md: `room_temperature`, `room_humidity`, `main_thermostat` (climate). The UI never touches `relay_*` directly.
- Flash budget: compile fonts with glyph subsets (digits, °, %, the needed letters), especially the 164 px and 105 px sizes.
- No secrets or location in git.

## Left to the builder

- How to switch themes in LVGL. For example, two sets of `style_definitions` re-applied to a list of widgets, or `lvgl.widget.update` color updates in one script.
- The exact chart widget and history storage for the temperature line.
- File split inside `tab5-thermostat/ui/` (for example `theme.yaml`, `fonts.yaml`, `console.yaml`), replacing `hello.yaml`.
- The precise ±10% sizing once the fonts render on hardware.
