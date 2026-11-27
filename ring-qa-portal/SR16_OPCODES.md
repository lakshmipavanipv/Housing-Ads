# SR16 opcode map (Ring QA Portal)

Every command is a Jieli frame written to characteristic `b002`; replies and pushes arrive on `b003`.

```
AB | flag (01 request, 11 reply) | len (2 bytes BE) | CRC16/ARC of body (2 bytes BE) | CMD Key KeyFlag | payload
```

KeyFlag `10` = read, `00` = write/push, `30` = ACK of a history page. Every frame the ring sends (flag != 11) must be ACKed with `CMD Key KeyFlag` (plus one `00` pad for `{6,9}`).

The single-byte IDs in the original opcode sheet (B9, C0, DF, ...) are RWfit app message IDs, not wire bytes. Sending them bare does nothing. Never write to service FF00/FF01: it is the ring's OTA (firmware update) channel.

## Portal modes

| Mode | Frame(s) sent | What it exercises | Verified 2026-11-16 |
|---|---|---|---|
| Time | `{2,1,0}` [yy mm dd hh mi ss] | ring clock (set) | OK on R001, R003 |
| Counter | `{2,96,16}` read japa count goal | counter | OK (goal = 33) |
| HR | `{6,9,0}` [03 05 01], then [03 05 00] | PPG (green) | OK |
| SpO2 | `{6,9,0}` [09 05 01], then [09 05 00] | PPG (red/IR) | OK |
| Battery | `{2,3,16}`, reply [%, mV BE] | battery | OK |
| Steps | none | — | N/A: no SR16 command |
| Sleep | none | — | N/A: no SR16 command |
| Switch Off | `{2,14,0}` [00] | health-monitor master off (low power) | OK |
| Switch On | `{2,14,0}` [01] | health-monitor master on | OK |

A mode is OK when the ring answers every frame; N/A counts as passed. SR16 has no display-mode switch, no power-off and no restart command.

## Test stages

| Stage | How the portal reads it |
|---|---|
| Battery | `{2,3,16}` → [%, mV BE] |
| HR (live) | Arm `{6,9,0}` [03 05 01]. The ring pushes `{2,36,0}` [ts32 BE, bpm, 0] every 1-3 s. It self-disarms after ~30 s, so the portal re-arms. Disarm with [03 05 00]. |
| SpO2 | Stored history pull `{5,9,16}`, ACK each page with `{5,9,0x30}`. Records are [ts32 BE, value, pad] (6 bytes). The ring records one every ~10 min. The pull is destructive: an ACKed page is erased. |
| HRV | Same as SpO2, using `{5,10,16}` / `{5,10,0x30}`. |
| Steps | Pull `{5,26,16}` and `{5,2,16}`. Records are 16 bytes; steps are a 24-bit BE value at offset 5. The record stamped "now" is today's total; hour-aligned records are hourly buckets. |
| Count | Ring pushes `{2,0x53,0}` with 8-byte records [ts32 BE, count32 BE]. |
| Time | Read: the timestamp inside a live HR push (there is no clock getter, and `{2,1,16}` returns empty). Set: `{2,1,0}`. Read again and check that the drift is within 3 s. |

The ring's timestamps (ts32) count seconds since 2000-01-01 in local time.

## Sensors (PPG / G-sensor / wear)

The ring never streams raw PPG or accelerometer samples over BLE. It has no gyroscope; motion comes from a 3-axis accelerometer ("G-sensor").

- **PPG:** exercised by the live metric command `{6,9,0}` [metric, 05, on/off]. Metric codes: 03 HR, 09 SpO2, 0a HRV, 0d stress. Only HR produces live pushes; SpO2 and HRV come from stored history.
- **G-sensor:** produces the step records (`{5,26,16}` and `{5,2,16}`).
- **Factory self-test** (from the RWfit SDK, `analysisRingFactoryState`):
  1. `{2,103,0}` [01] enters test mode.
  2. `{2,112,16}` reads [G-sensor, Heart(PPG), Wear]. The first read gives FF FF FF (still testing); later reads gave **01 01 FE** on SR16-1.
  3. `{2,103,0}` [00] exits test mode.

  1 most likely means pass. FE for wear is unconfirmed; it probably means "not worn".

  **Exiting test mode reboots the ring.** The ring dropped the connection, and its name changed from "SR16-1" to "Velvue". For this reason it is not used as a portal mode. `{2,103,16}` returns a 4-byte status whose meaning is unknown.

## Other commands found in the RWfit SDK (not used by the portal)

| Frame | Function |
|---|---|
| `{2,11,0}` | vibrate [level 1-3, count] (used by Buzz) |
| `{2,8,x}` | screen-on time |
| `{2,9,x}` | sedentary reminder |
| `{2,10,16}` | do not disturb (read) |
| `{2,12,x}` | raise-to-wake / bright schedule |
| `{2,16,x}` | alarms |
| `{2,20,x}` | notification switches |
| `{2,22,x}` | timed HR |
| `{2,33,x}` | drink reminder |
| `{2,37,x}` | timed SpO2 |
| `{2,99,16}` | capabilities |
| `{2,102,x}` | LED |
| `{2,104,x}` | wear hand |
| `{2,106,x}` | timed HRV |
| `{2,107,x}` | timed stress |
| `{2,111,0}` | clear japa count (destructive) |
| `{4,1,0}` | message push |
| `{6,1,0}` | take photo |
| `{6,4,16}` | call alert |

No command was found that turns the OLED screen on remotely.
