# Site survey

What we know about the house's HVAC, and what's still needed before the install design is final. The photos themselves stay out of this public repo (phone photos can carry the house's location).

## Middle-floor thermostat: photographed 2026-10-30

The wall plate's terminals, and the old thermostat's circuit board, with the faceplate off.

| What | Found | What it means |
|---|---|---|
| Wires at the wall | **4: red → RH, white → W, yellow → Y, green → G** | Heat, cool and fan calls, plus 24 V hot (R). |
| RH and RC | joined by the plate's factory jumper (a short black wire between the two screws) | **One transformer** for heat and cool. Our relays all switch from the same R. |
| B and O | empty | **Not a heat pump** (no reversing valve). `relay_ob` stays unused for this zone. |
| C | no C terminal on the plate, no wire for it | **No C wire at the wall.** The old thermostat runs on 2 AA batteries. |
| Stages | W and Y only | **Single-stage heat, single-stage cool.** |
| Fan jumper on the board (SLW1) | set to **GAS**, not ELECT | **Gas furnace:** the furnace runs its own blower when heating, and the thermostat drives G only for cooling and fan-on. The logic already does exactly this (heating calls W only, cooling Y + G). |
| The old thermostat | board marked **TX9000LC Ver. 1.6, 18-07-2000** (probably a LUX TX9000-series model), green electroluminescent backlight | Most likely the original from when the house was built. |
| The wall opening | a small hole in the drywall behind the plate, no electrical box | The new plate has to cover the old one's outline; nothing to mount into but the wall. |

**So:** this zone is a plain gas furnace with central AC, single stage, one transformer. The Unit 4-Relay covers it with one relay to spare (W, Y, G used, O/B unused). **The one open question is power at the wall:** there are exactly four wires, and all four are in use.

**Re-photographed 2026-11-18:** the same four wires, and nothing else visible in the hole: no fifth wire folded back at the wall. The cable's jacket (and any writing on it) is out of sight inside the wall, so a spare cut short further in, or at the furnace end, is still possible.

## Furnace: photographed 2026-11-18 (outside only)

| What | Found | What it means |
|---|---|---|
| The furnace | **Trane** gas furnace, **electronic ignition** (no standing pilot); the installer's guide beside it covers upflow/downflow "fan assisted combustion" gas furnaces (American Standard, a sister brand under Trane Technologies) | Confirms the gas furnace the GAS jumper pointed to. A furnace like this has a control board with its own 24 V transformer, almost always with a C terminal. The model number isn't in the photos yet (it's on a sticker inside a front door). |
| Its power | a light switch on the stud next to it is the furnace's service switch, wired into its left side | The switch to turn off before opening any panel. |
| Low-voltage cables | **two brown cables** come down from above and enter low on the left side | Most likely the thermostat cable and the outdoor AC's control cable. If one is the AC's, C is already in use on the board (the AC contactor's coil returns to C), so C is there for a fifth wire. |
| Zone panel | none visible in these photos | Not settled; asked below. |
| Filter | 16 × 25 × 1, beside the furnace | For reference only. |

**Still unknown:** how many conductors the thermostat cable has (the deciding question), the board's terminals, the model number, the outdoor unit, and the top floor.

## What decides the power design

Whether the cable in the wall has a **spare conductor**: a fifth wire (often blue, black or brown) that was cut short or folded back, at either end. Research [section 5](research.md#5-getting-power-to-the-wall) ranks the options:

1. **A spare conductor exists:** connect it to C at the furnace. The Tab5 stays all-in-one at the wall, as built (architecture A). Best case.
2. **No spare:** the cleanest answer is the split design (architecture B): the relays move to a small board at the furnace, and two of the four existing wires carry power up to the Tab5. The logic would then run on the furnace board, with the Tab5 as display and sensor. This changes milestone 4 and 5 hardware, so it gets its own brainstorm with Dang first. One point for that brainstorm: the room sensor stays at the wall, so the furnace board needs the temperature from the Tab5 (over Wi-Fi, ESP-NOW, or the other two existing wires, since the Tab5 has RS485), and its own fallback when that link drops, because Wi-Fi going down must never stop heating.
3. Fallbacks: give up the separate fan wire (G becomes C), a Venstar Add-a-Wire, pulling a new cable, or a nearby outlet.

The answer is at the furnace end. The 2026-11-18 photos show the cables from outside; requests 1–3 below look at their wires.

## Ask the family (copy and send)

Updated 2026-11-18 (the first request's photos of the thermostat and the furnace's outside are in).

> Thanks for the furnace photos! A few more would settle the power question. First switch the furnace off at the light switch on the stud beside it, and please don't disconnect or move any wires.
>
> 1. **Inside the furnace:** take off the front door where the thin colored wires connect (they lift up and off). A photo of the circuit board's row of small screw terminals labelled R, C, W, Y, G, with the wires on them. And a photo of the sticker inside the door with the model and serial number.
> 2. **The two brown cables** coming down the furnace's left side: a close photo of the writing on each (like "18/5" or "18-2"), and which one goes up toward the thermostat.
> 3. **Spare wires:** where the brown cables' colored wires come out of their jackets, are any of them not screwed to anything (cut short or folded back)? A photo.
> 4. **Outside:** a photo of the label on each outdoor AC unit (how many units are there?).
> 5. **Near the furnace:** is there a separate box with lots of thin wires labelled "Zone 1 / Zone 2", or a second furnace somewhere?
> 6. **The top-floor thermostat:** a photo of the front, then the same wire photo as the middle-floor one (faceplate off).
> 7. **The middle-floor thermostat's wall:** a wider photo showing the wall around it, and where the nearest power outlet is.
>
> Then put the door back, switch the furnace on, and check the heat comes on when you turn the thermostat up.

## At the visit (with a multimeter)

Still needed even after the photos:

- **R to C at the furnace board**, about 24–28 V AC. If a spare conductor exists, connect it to C at the furnace and measure R to the spare at the wall.
- The furnace board's **terminal labels** (W1/W2, Y1/Y2, C), its **fuse rating**, and the **transformer's VA rating** (usually 40 VA). The Tab5 adds about 3 VA normally, up to about 8 VA while recharging its battery if it's kept in.
- **2.4 GHz Wi-Fi signal** at the thermostat's spot.
- The thermostat's spot: height, direct sun, nearby supply vents or doors.
- Optional: the current on W, Y and G while each runs, to check the relay contacts.

## Top-floor thermostat

Not surveyed yet (photo request 7 above). It stays as it is for now; the long-term goal is one Tab5 controlling both floors.
