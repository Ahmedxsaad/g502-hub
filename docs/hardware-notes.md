# Behaviour verified on this unit

G502 HERO `046d:c08b`, firmware `U1 69.00.B0009`, bootloader `BL2 40.00.B0009`,
HID++ 4.2, profile format 2. Tested 2026-10-25.

## Onboard memory
- 16 sectors × 255 bytes, 5 user profiles in sectors 1-5, 5 ROM profiles in
  `0x0101`-`0x0105`. ROM sectors above `0x0105` answer INVALID_ARGUMENT.
- Every user sector carries a CRC-16/CCITT-FALSE that verifies. ROM sectors carry
  none (`FF FF`).
- The user directory uses `00` as the reserved byte and `FF FF 00 00` as the
  terminator.
- **Neither the factory profiles nor the user profiles have a G-Shift layer**:
  bytes 96-159 are all `FF`. Profile names are all zeros (user) or all `FF` (ROM).
- Writing a sector with a correct CRC: memoryWriteEnd acks and the read-back
  matches. Tested on slot 5, then restored from backup.

## Current profile
- getCurrentProfile returns the 1-based sector (`00 02` = sector 2). libratbag 0.18
  on this system shows it one slot off.
- **ROM profiles cannot be selected**: setCurrentProfile(`0x0101`) answers
  INVALID_ARGUMENT.
- **Selecting the profile that is already active does nothing.** Neither does
  setCurrentDpiIndex with the index that is already active: a live DPI change
  survives both. Switching to another slot and back reloads the profile, and
  takes about 0.1 s.

## Modes
| | Onboard (1) | Host (2) |
|---|---|---|
| setSensorDpi | works, live until the next profile/DPI change | works |
| setReportRate | **INVALID_ARGUMENT**: use profile byte 0 | works |
| setCurrentProfile | works (user slots only) | INVALID_ARGUMENT |
| getCurrentProfile | sector | `00 00` |
| getCurrentDpiIndex | works | still answers |
| spy getMapping | `01..0B` | `01..0B` |

- On entering host mode the mouse keeps the DPI and rate it had.
- Leaving host mode reloads the stored current profile.

## Mouse Button Spy (0x8110)
- Events stream after startMouseButtonSpy in **onboard mode**, with no mode switch.
- Each event is a BE16 bitmap of the buttons held. Bit *i* = onboard button slot *i*:

| Bit | Button | Bit | Button |
|---|---|---|---|
| 0 | G1 left | 6 | G7 (front, left of left click) |
| 1 | G2 right | 7 | G8 (behind G7) |
| 2 | G3 wheel click | 8 | G9 (behind wheel) |
| 3 | G4 back | 9 | wheel tilt right |
| 4 | G5 forward | 10 | wheel tilt left |
| 5 | G6 sniper | | |

- Buttons bound to firmware specials (DPI shift/up/down, profile cycle) are
  reported too, and the firmware still performs the special. A software layer
  can see every button, but needs the binding set to disabled to *replace*
  what the firmware does.

## LEDs
- 0x8070 zone 0 (location 1, "primary") is the **DPI indicator lights**. Zone 1
  (location 2) is the **G logo**. Confirmed visually.
- The effect indexes are 0 off, 1 fixed, 2 breathing, 3 cycle.
- Profile LED block *i* is assumed to drive zone *i* (libratbag's mapping). Not yet
  verified with two different colors.
