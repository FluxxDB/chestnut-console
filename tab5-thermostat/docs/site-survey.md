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

## What decides the power design

Whether the cable in the wall has a **spare conductor**: a fifth wire (often blue, black or brown) that was cut short or folded back, at either end. Research [section 5](research.md#5-getting-power-to-the-wall) ranks the options:

1. **A spare conductor exists:** connect it to C at the furnace. The Tab5 stays all-in-one at the wall, as built (architecture A). Best case.
2. **No spare:** the cleanest answer is the split design (architecture B): the relays move to a small board at the furnace, and two of the four existing wires carry power up to the Tab5. The logic would then run on the furnace board, with the Tab5 as display and sensor. This changes milestone 4 and 5 hardware, so it gets its own brainstorm with Dang first. One point for that brainstorm: the room sensor stays at the wall, so the furnace board needs the temperature from the Tab5 (over Wi-Fi, ESP-NOW, or the other two existing wires, since the Tab5 has RS485), and its own fallback when that link drops, because Wi-Fi going down must never stop heating.
3. Fallbacks: give up the separate fan wire (G becomes C), a Venstar Add-a-Wire, pulling a new cable, or a nearby outlet.

The answer is at the furnace end, which is why the family photos below come first.

## Ask the family (copy and send)

> Thanks for the thermostat photos! A few more would settle the rest. Please don't disconnect or move any wires, and switch the furnace's power off (a light switch on or near it) before opening its front panel.
>
> 1. **The thermostat cable at the wall:** with the faceplate off, gently ease the cable out of the hole an inch. Are there any other wires (blue, black, brown, orange) folded back into the wall? A close photo of the cable, and of any writing on its outer jacket (like "18/5").
> 2. **The old thermostat:** clip it back on the wall plate, and check the heat comes on when you turn it up.
> 3. **The furnace:** where is it (basement, closet, attic)? A photo of the label with the brand and model (usually inside the front panel).
> 4. **Inside the furnace panel:** a photo of the small screw terminals where the thin thermostat wires connect (labelled R, C, W, Y, G or similar). Do any extra thin wires in that cable go nowhere (cut short or tucked back)?
> 5. **Near the furnace:** is there a separate box with lots of thin wires labelled "Zone 1 / Zone 2"? Or are there two furnaces?
> 6. **Outside:** a photo of the label on each outdoor AC unit (how many units are there?).
> 7. **The top-floor thermostat:** a photo of the front, then the same wire photo as the middle-floor one (faceplate off).
> 8. **The middle-floor thermostat's wall:** a wider photo showing the wall around it, and where the nearest power outlet is.

## At the visit (with a multimeter)

Still needed even after the photos:

- **R to C at the furnace board**, about 24–28 V AC. If a spare conductor exists, connect it to C at the furnace and measure R to the spare at the wall.
- The furnace board's **terminal labels** (W1/W2, Y1/Y2, C), its **fuse rating**, and the **transformer's VA rating** (usually 40 VA). The Tab5 adds about 3 VA normally, up to about 8 VA while recharging its battery if it's kept in.
- **2.4 GHz Wi-Fi signal** at the thermostat's spot.
- The thermostat's spot: height, direct sun, nearby supply vents or doors.
- Optional: the current on W, Y and G while each runs, to check the relay contacts.

## Top-floor thermostat

Not surveyed yet (photo request 7 above). It stays as it is for now; the long-term goal is one Tab5 controlling both floors.
