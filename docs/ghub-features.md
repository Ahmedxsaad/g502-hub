# Logitech G HUB feature inventory: G502 HERO / G502 SE HERO (USB 046d:c08b)

Reference for building a Linux replacement. Compiled 2026-10-25.

**Storage legend** (used throughout)

- **[ONBOARD]**: stored in the mouse's onboard memory (HID++ feature 0x8100). It works with no software running, but only while the mouse is in On-Board Memory mode.
- **[SOFTWARE]**: needs G HUB running. G HUB either emulates the feature on the host or pushes it to the mouse live; in that case it is not persisted.
- **[BOTH]**: available in software mode, plus a reduced version that can live onboard.

**How sure each claim is**

- A claim with a source tag like `[S3]` is documented in that source.
- **(probe)** means I measured it on the user's own mouse (connected on this machine as `046d:c08b`, "G502 SE HERO Gaming Mouse"). I used read-only HID++ 2.0 queries and `ratbagctl` (libratbag 0.18).
- **UNCONFIRMED** means I could not find a source for it. Section 11 collects these.

> Important caveat about the "official manual". The only full G HUB manual Logitech ever published is the 114-page *G HUB Manual* [S1]. It dates from 2019–2020 (PDF CreationDate Dec 2019, ModDate Aug 2020). The UI has been restyled since then and some labels have changed, for example the global settings moved behind a cog or hamburger menu [S20]. Nobody has published a newer screen-by-screen manual. Feature semantics have stayed stable, but treat exact capitalisation and labels as "as of the 2020 manual" unless a newer source is cited.

---

## 0. Device ground truth (what the hardware actually exposes)

| Item | Value | Source |
|---|---|---|
| Name reported by device | `G502 HERO Gaming Mouse` (the SE is a colour variant with the same PID and sensor) | (probe), [S22] |
| Sensor | HERO 25K. It was marketed as HERO 16K until Sept 2020. **G HUB 2020.8.5950 "Enabled 25600 DPI"** for the G502 HERO, and the sensor already reported 25 600 to libratbag, so this was a software unlock; retailers describe it as a firmware update. | [S6], [S7], [S37], [S40] |
| DPI range / step | **100 – 25 600 DPI, step 50**. The device's 0x2201 `getSensorDpiList` returns `0x0064, 0xE032, 0x6400`, meaning 100, step 50, 25 600. | (probe) |
| Sensor's built-in default DPI | 1000. This is 0x2201 `getSensorDpi` "default" and is used when no profile applies it. | (probe) |
| Report rates | 125 / 250 / 500 / 1000 Hz. The 0x8060 bitmap `0x8B` means 8/4/2/1 ms. Nothing above 1 kHz. | (probe), [S1] |
| Programmable buttons | 11. Both 0x8100 `buttonCount` and 0x8110 `getNbButtons` return 11. A 12th control, the wheel-mode toggle, is mechanical and not programmable. | (probe), [S2] |
| Onboard profile slots | **5**. The 0x8100 descriptor reports profileCount=5 and 5 ROM/OOB profiles. Logitech states "Up to 5 profiles (requires firmware 127.1.7)". The original paper guide describes 3 preset profiles. | (probe), [S5], [S2] |
| Onboard memory geometry | memoryModel 1, profileFormat 2, macroFormat 1, 16 sectors × **255 bytes** (about 4 KB). Each sector ends in a CRC-16/CCITT at offset `sector_size − 2`. Sector 0 is the profile directory, and the ROM factory profiles are at 0x0101–0x0105. Mechanical-layout byte 0x0A means G-Shift is supported and DPI-Shift is supported (libratbag decoding). Various-info 0x01 means corded. | (probe), [S30], [S38], [S40] |
| RGB lighting zones | **2** in HID++ 0x8070 v3: zone 0 = location 1 "primary" (DPI-indicator strip), zone 1 = location 2 "logo". Each has 4 effects: 0x00 off, 0x01 fixed, 0x0A breathing, 0x03 cycle. Note that Logitech's spec sheet says "LIGHTSYNC RGB: 1 zone" [S5], but the hardware and the G HUB UI ("PRIMARY / LOGO" [S1]) both show two. | (probe), [S1] |
| Firmware entities (0x0003) | **This unit:** application `U1 69.00.B0009`, bootloader `BL2 40.00.B0009` (probe). **Other units** documented by Solaar: `U1 27.03.B0010` / bootloader `BOT 81.00.B0002` [S39]. That matches G HUB's "127.3.10" release [S37], so G HUB seems to show the version as prefix digit, then number, revision and build ("1"+"27".3.10). By that reading this unit would show as about "169.0.9" (inference, UNCONFIRMED). **The user's mouse is on a different firmware and bootloader line from the commonly documented G502 HERO.** It also reports onboard *profile format 2*, while OpenGHub's G502 notes describe format 3. Verify layouts on this exact unit before writing flash. In bootloader/DFU mode the mouse enumerates as `046d:aae6` [S39]. | (probe), [S39], [S37] |
| Firmware update feature | 0x00C2 "DFU Control (signed)". Updates are signed, so G HUB or Logitech tools are needed to flash them. | (probe) |

HID++ 2.0 feature table read from the device (probe). These indices are needed for any custom driver:

```
idx  1 0x0001 FeatureSet              idx 11 0x8060 ReportRate
idx  2 0x8070 ColorLEDEffects v3      idx 12 0x8100 OnboardProfiles
idx  3 0x0003 DeviceFwVersion v2      idx 13 0x8110 MouseButtonSpy
idx  4 0x0005 DeviceName              idx 14 0x00C2 DFUControl (signed)
idx  5 0x1300 LEDControl(?)           idx 15 0x1801 (hidden/eng) Manufacturing
idx  6 0x18A1 (hidden/eng) LED test   idx 16 0x1802 (hidden/eng) DeviceReset
idx  7 0x1E00 EnableHiddenFeatures    idx 17 0x1806 (hidden/eng) ConfigurableDeviceProperties v5
idx  8 0x1E22 (hidden/eng) SPI access idx 18 0x18B1 (hidden/eng) ?
idx  9 0x1EB0 (hidden/eng) ?          idx 19 0x180B (hidden/eng) ?
idx 10 0x2201 AdjustableDPI v1
```

Several features are **absent**, and that has consequences:

- No 0x2202 Extended DPI, so there is **no separate X/Y DPI**.
- No 0x2230 angle snapping and no 0x2240 surface tuning.
- No 0x8061 extended report rate.
- No 0x1B04 reprogrammable controls and no 0x2121 hi-res wheel.

Button remapping on this mouse therefore works in one of two ways. In onboard mode, the bindings live inside onboard profiles (0x8100). In host or software mode, G HUB captures raw buttons through 0x8110 Mouse Button Spy and synthesises the output itself. G HUB injects that output through Logitech virtual keyboard and mouse devices [S27].

Physical button map. These are Logitech's numbering [S2] and the libratbag button index (probe):

| Logitech # / G-name | Control | Factory function | libratbag idx | Lua `arg` (§7) |
|---|---|---|---|---|
| 1 (G1) | Left | Left click | 0 | 1 (only after `EnablePrimaryMouseButtonEvents`) |
| 2 (G2) | Right | Right click | 1 | 2 |
| 3 (G3) | Wheel click | Middle click | 2 | 3 |
| 4 (G4) | Back (thumb rear) | Back | 3 | 4 |
| 5 (G5) | Forward (thumb front) | Forward | 4 | 5 |
| G6 | DPI Shift / "sniper" (thumb, front) | DPI Shift | 5 | 6 |
| G7 | DPI Down (left of left-click) | DPI Down | 6 | 7 |
| G8 | DPI Up (left of left-click) | DPI Up | 7 | 8 |
| G9 | Profile select (behind wheel) | Next (onboard) profile | 8 | 9 |
| — | Wheel tilt right | Scroll right | 9 | 10 (inferred) |
| — | Wheel tilt left | Scroll left | 10 | **11** (confirmed [L10]) |
| (G12) | Wheel-mode shift (free-spin/ratchet) | Mechanical, **not programmable** | — | — |

The setup guide gives no G-number to the tilt directions, calling them only "Scroll left (wheel tilt left)" and "Scroll right" [S2]. Whether the G HUB UI labels them "G10"/"G11" is UNCONFIRMED.

---

## 1. Sensitivity (DPI) tab

The G HUB "Sensitivity (DPI)" tab [S1, pp. 23–25] contains:

- **DPI SPEEDS.** These are levels on a slider. You click the slider to add a level and drag a level off it to delete one. You can have between 1 level plus the DPI SHIFT level and a maximum of 5 DPI levels on the G502 [S1], [S10]. The DPI SHIFT speed cannot be removed [S10]. The underlined value is the current DPI.
  - Range on this mouse: 100–25 600, step 50 (probe; marketing pages variously say 100 or 200 minimum [S5], [S6]). G HUB 2020.8.5950 raised the UI limit from 16 000 to 25 600 [S37], [S6]. Whether the UI lets you type exact values is UNCONFIRMED. The hardware DPI list advertises a 50-DPI step.
  - Each level gets a colour on the DPI indicator. In the 2020 manual these were yellow for the lowest and pink for the highest [S1].
  - Changes save automatically [S1].
- **DPI SHIFT SPEED.** One level is marked with a **yellow diamond** as the DPI SHIFT speed. You click the diamond on another level to move it [S1]. Holding a button assigned to "DPI Shift" switches to that level, and releasing restores the previous one [S1], [S5]. It is momentary.
- **Default DPI.** Onboard profiles store a "default DPI index" (libratbag shows "(default)" per profile; probe). G HUB for newer mice also exposes "Default DPI" [S29]. I could not confirm whether the current G HUB UI shows a separate "default" marker for the G502 HERO, or whether the default is implicitly the active level. This is UNCONFIRMED. On the original G502 (LGS) the default was the level restored after a profile switch, power-up or wake [S28].
- **REPORT RATE.** This is a dropdown, 1000 by default. The manual says "if you see skipping… reducing this might help" [S1]. The values are 125/250/500/1000 (probe).
- **ASSIGN DPI CONTROLS.** This jumps to Assignments, filtered to the DPI commands in SYSTEM [S1].
- **RESTORE DEFAULT SETTINGS** resets the DPI configuration [S1].
- **Per-profile DPI lock (padlock).** It makes the DPI configuration identical across all profiles. Without it, each profile has its own DPI levels [S1], [S10].
- **Profile selector** dropdown: "PER-PROFILE CONFIGURATION" or "PERSISTENT CONFIGURATION" [S1].

These are **not available** for the G502 HERO in G HUB:

- **Per-axis X/Y DPI.** G HUB offers it only for HERO 2 mice [S8], and this mouse lacks HID++ 0x2202 (probe).
- **Lift-off distance (LOD) and surface tuning.** These are for HERO 2 / PRO X Superlight 2 [S8], [S9], and this mouse lacks 0x2240 (probe).
- **Angle snapping.** The G HUB UI has no option for it, and the device has no 0x2230 feature. The onboard profile format does contain an `angle_snapping` byte (libratbag [S30]), but whether this firmware honours it is UNCONFIRMED.
- **Acceleration / pointer speed.** G HUB has no pointer-acceleration setting, and the sensor is marketed as "zero smoothing, filtering or acceleration" [S5]. The old LGS had an "Acceleration (Enhance Pointer Precision)" checkbox, which only drove the Windows setting [S28].
- **Scroll speed / smooth scrolling.** I found no G HUB setting for this on this mouse. Absence is UNCONFIRMED in the sense that no source says so explicitly.
- **Report rates above 1 kHz.** These exist only on HERO 2 / newer mice [S8].

**Storage.** DPI levels, DPI-shift level, default index and report rate: [BOTH]. In software mode G HUB applies them live via 0x2201/0x8060. In onboard mode they are part of each onboard profile (the profile format stores report_rate, default_dpi index, switched_dpi index and dpi[5] [S30]).

---

## 2. Assignments tab

### 2.1 Categories (tabs inside Assignments)

For mice the manual lists **COMMANDS | KEYS | ACTIONS | MACROS | SYSTEM** [S1]. Current Logitech support adds further device-dependent tabs [S3], [S12]:

| Category | Official description | Contents relevant to a mouse |
|---|---|---|
| **COMMANDS** | "Preconfigured system or Game profile commands based on your selected G HUB Profile" [S3]. "Command Lighting and Default Commands (shortcuts and hotkeys)" [S1]. "General inputs such as copy, paste, play, and pause" [S12]. | Desktop profile: generic OS shortcuts (copy/paste/undo…). Game profiles that G HUB detected: built-in per-game command lists in groups, e.g. WoW "Pet / Interface / Movement / Abilities" [S1]. *Command Lighting* (colour per command group) is a keyboard feature [S1]. |
| **KEYS** | "Individual keyboard commands" [S3]. "All the standard keyboard keys. NEW! Including F13 – F24" [S1]. | Any single key. For modifier combinations, use a macro or Commands. A modifier selector on the Keys tab for *mouse* targets is UNCONFIRMED; the Shift/Ctrl/Alt "modifier + event type" remap UI is documented for KEYCONTROL keyboards [S12], [S13]. |
| **ACTIONS** | "Actions for application-specific integrations that work with Logitech G HUB" [S3] | Integrations: **OBS Studio** (e.g. Toggle Streaming, Activate Scene), **Discord** (Mute Self, Deafen Self, join/leave voice; no push-to-talk) [S1], [S15], **Overwolf** (Capture Video / Capture Replay) [S1], **Streamlabs Desktop** (G HUB 2023.2+: Toggle Streaming, Toggle Recording, switch scene, show/hide source, mute/unmute mixer, set mixer volume) [S14]. Litra lights appear as actions too [S14]. **+ CREATE NEW ACTION** builds a parameterised action. G HUB queries the app for scenes and sources, so the app must be running (warning icon otherwise) [S1]. |
| **MACROS** | "Custom programmable commands" [S3] | The list of macros for the current game/app, plus **CREATE NEW MACRO** (§4). |
| **SYSTEM** | "System and device control commands" [S3]. "System commands; Mouse, Media, Editing, Audio hotkeys and Launch Application" [S1]. | See 2.2. |
| Presets / Effects / Samples | Blue VO!CE microphone features [S3] | Shown only if a Blue VO!CE device is connected. |
| Audio | "Audio commands for your Logitech speakers" [S3] | Shown only with a Logitech speaker connected. |

You assign a command by dragging it onto a button, or by clicking the button (it highlights blue) and then clicking the command [S1]. A **search box** filters the command list [S1]. You clear a binding by dragging it off or pressing Delete [S1].

### 2.2 SYSTEM category: known groups and commands

Documented in [S1] and [S17], with label spellings from the manual and support sources:

- **Mouse group:**
  - Mouse functions such as primary/secondary/middle click, back and forward, plus scroll left and right. (The exact label wording is UNCONFIRMED: "Primary Click / Secondary Click / Middle Click / Back / Forward / Scroll Left / Scroll Right / Scroll Up / Scroll Down".)
  - DPI commands: **DPI Up, DPI Down, DPI Cycle(-ing), DPI Shift**. These come from the manual's "DPI buttons (up | down | cycle)" [S1] and [S17], [S29].
  - **Onboard Profile Cycle**, which "will cycle through onboard memory profiles when G HUB is not running" [S1].
  - **G-Shift** (in SYSTEM [S1]; its group is UNCONFIRMED).
- **G HUB group:** **Profile Cycle**, which cycles through the user profiles of the *current application* and is shown in purple as a "special command" [S1].
- **Media:** play/pause, stop, previous, next, volume up/down, mute. The group is documented [S1]; the item list is UNCONFIRMED.
- **Editing:** cut, copy, paste, undo and so on. The group is documented [S1]; the items are UNCONFIRMED.
- **Audio hotkeys** [S1].
- **Launch Application:** **CREATE NEW** browses to an executable. Each entry can be edited for **NAME, PATH and ADD ARGUMENTS** [S1]. Launch shortcuts are reusable across macros [S1].

What the onboard profile format can store for one button. This is the hard limit on what onboard mode can do, decoded by libratbag [S30]:

- Mouse-button bitmask (any of 16 HID buttons).
- Keyboard key plus a modifier byte (Ctrl/Shift/Alt/GUI).
- Consumer-control usage (media keys).
- Macro pointer.
- Disabled.
- "Special" codes: 0x01 tilt-left, 0x02 tilt-right, 0x03 next DPI, 0x04 prev DPI, 0x05 cycle DPI, 0x06 default DPI, 0x07 DPI shift, 0x08 next profile, 0x09 prev profile, 0x0A cycle profile, 0x0B **G-Shift**, 0x0C battery indicator, 0x0D enable profile, 0x0E performance switch, 0x0F host, 0x10 scroll-down, 0x11 scroll-up.

This means there are onboard "Default DPI", "Prev/Next profile" and "scroll up/down" functions, even though G HUB may not surface all of them.

### 2.3 Which buttons are remappable

- All **11** buttons G1–G9 and both tilts are programmable [S2], [S5], including **left click**.
- G HUB asks you to **confirm** before overwriting primary (left) or secondary (right) click [S16]. If you remove left click with no fallback, you can recover through the Windows primary-button swap [S16].
- Per-button context menu [S1], [S11]:
  - **USE DEFAULT** resets the button to factory. The five standard buttons (L/R/M/Back/Fwd) then behave normally, and the others become "non programmed".
  - **DISABLE** makes the button output nothing, even for the five standard buttons.
- Assignments have a **per-profile lock** (padlock): the same assignments in all profiles [S1].
- A **DEFAULT | G-SHIFT** toggle switches which layer you are editing (§3) [S1].
- The **command indicator** shows where a command is bound, with red meaning the G-Shift layer [S1].

**Storage.** Keys, mouse buttons, media/consumer keys, DPI and profile functions, G-Shift and Disable: [BOTH], since they can be written into onboard profiles. Integration **Actions**, **Launch Application**, **Profile Cycle** (G HUB user profiles), **Commands** that map to game-profile features, and anything beyond simple macros: [SOFTWARE].

---

## 3. G-Shift

- G-Shift is "another set of assignments which are all activated when in that mode". Editing happens through the **DEFAULT | G-SHIFT** switch in Assignments [S1].
- To create it, drag the **G-Shift** command from SYSTEM onto any programmable button [S1]. The G502 HERO's factory "Standard" profile puts G-Shift on **G6** (the DPI Shift button) [S2]. That button has no shifted function itself ("N/A") [S2].
- It is **momentary**: the shifted function fires only while the G-Shift key is held. G HUB has **no native toggle or latch**; workarounds use profile switching or Lua [S18], [S19]. On LGS, G-Shift "can't be the default assignment" and is "an alternate state" [S18].
- **It works across devices.** "That G SHIFT key will synchronise on all devices… When pressed your mouse will also enter the G SHIFT mode and vice versa" [S1]. KEYCONTROL keyboards also let a spare mouse button trigger the keyboard's G SHIFT layer [S13].
- **Shifted layer contents.** Any assignment type that works on the base layer: keys, commands, macros, actions, system functions [S1]. The G502 HERO's factory shifted layer is entirely key combos: G3=Ctrl+T, G4=Ctrl+Shift+Tab, G5=Ctrl+Tab, G7=Ctrl+X, G8=Ctrl+Z, tilt-L=Ctrl+F4, tilt-R=Ctrl+Shift+T, G9=Ctrl+0 [S2].
- **Storage: [BOTH].** The onboard format has 16 `alternate_buttons` (the G-Shift layer) per profile, and the descriptor confirms has_g_shift (probe, [S30]). The factory onboard profile with a G-Shift layer proves the hardware executes it with no software running [S2]. On the probed mouse, the active onboard profile has G6 = `second-mode` (G-Shift), G7 = Ctrl+C and G8 = Ctrl+V (probe). Cross-device G-Shift sync is [SOFTWARE].

---

## 4. Macros

### 4.1 Creating

Go to Assignments → MACROS → **CREATE NEW MACRO**, then **Name This Macro**, then "SELECT A TYPE OF MACRO YOU WANT TO CREATE" [S1]. Macros belong to a game/app (shown in that app's MACROS tab in the profile manager) and can be dragged to another app to copy them [S1].

| Type (G HUB label) | Behaviour [S1] |
|---|---|
| **NO REPEAT** | Plays once per press. |
| **REPEAT WHILE HOLDING** | Loops continuously while the button is held ("auto fire"). |
| **TOGGLE** | Loops until the button is pressed again. "Button/key is held down on the first press, and let up on the second press" ("auto running"). |
| **SEQUENCE** | Advanced editor with three sections: **ON PRESS** runs immediately on press, **WHILE HOLDING** repeats while held, and **ON RELEASE** runs on release. Each section holds its own event list. |

The macro type can be changed later from icons in the editor [S16].

### 4.2 Editor: "+ START NOW" offers 6 kinds of step [S1]

1. **RECORD KEYSTROKES** records "all your mouse button and key strokes" (button and key down/up events). **Mouse movement and cursor position are not recorded**: no source documents movement recording, and Lua is the usual route for movement. Treat this as UNCONFIRMED but very likely.
2. **TEXT & EMOJIS** is a typed string with an emoji picker. A text block "will behave like a no repeat macro" [S1].
3. **ACTION** is an integration action (OBS, Discord, Overwolf, Streamlabs…), including **CREATE NEW ACTION** [S1], [S14].
4. **LAUNCH APPLICATION** is a saved launch shortcut with NAME, PATH and ADD ARGUMENTS [S1].
5. **SYSTEM** is any SYSTEM-tab command (media, mouse function and so on) [S1].
6. **DELAY** is an explicit delay step, **default 50 ms**, editable [S1].

You can mix these freely in one macro. Recorded events can be deleted (Delete key) or dragged to re-order [S1].

### 4.3 MACRO OPTIONS (dropdown) [S1]

- **USE STANDARD DELAYS** is on by default at **50 ms** (a global inter-event delay). The value is editable, **minimum 25 ms**. Unticking it gives every event, including the down/up pairs, its own editable delay.
- **SHOW KEY DOWN/KEY UP** shows down and up events separately. It is off by default.
- **MACRO COLOR** is a colour tag, with SELECT/DONE.
- **DELETE THIS MACRO** appears only for saved macros.

Users report that turning off standard delays allows 5–10 ms delays in practice [S24]. The editor's 25 ms minimum applies to the *standard* delay.

### 4.4 Internal representation

This is useful for importing G HUB settings. G HUB stores everything in `%LOCALAPPDATA%\LGHUB\settings.db`, an SQLite database holding one JSON blob; older versions used plain `settings.json` [S25], [S40]. A macro is a `"cards"` entry with `"attribute": "MACRO_PLAYBACK"`, an `applicationId`, and a `macro` object [S25]:

```json
"macro": { "onboardable": true, "type": "SEQUENCE",
  "sequence": { "defaultDelay": 50, "useDefaultDelay": true, "useSimpleActions": true,
    "simpleSequence": { "components": [
        { "keyboard": { "displayName": "F11", "hidUsage": 68, "isDown": true } },
        { "delay": { "durationMs": 50 } },
        { "keyboard": { "displayName": "F11", "hidUsage": 68 } } ] },
    "pressSequence": {}, "heldSequence": {}, "releaseSequence": {}, "toggleSequence": {} } }
```

Notes on this structure:

- Keys are stored as **HID usage IDs**, not Windows scancodes.
- `onboardable` is G HUB's own flag for whether a macro can be written to the mouse.
- The sub-sequence buckets map onto the four types. That mapping is inferred from the field names and is UNCONFIRMED in detail.

### 4.5 Limits and onboard behaviour

- **Onboard memory mode** supports only **No Repeat** macros, including text with modifiers but **not emoji**. **Repeat While Holding, Toggle and Sequence do not work in Onboard Memory mode** [S4]. Actions, Launch Application and other software-side steps cannot run onboard either, since they need the PC.
- Onboard macros live in the 16 × 255-byte sector pool shared with the profiles (probe), so there is a hard size limit. Logitech publishes no number of events.
- The **onboard macro bytecode** (libratbag [S30]) supports more than G HUB uses:
  - key press/release, mouse-button down/up, consumer down/up
  - delay, jump, wheel (roller), AC-pan, **XY pointer movement**
  - "wait for release", "repeat while pressed" and "repeat until cancelled"

  A custom tool could therefore possibly implement onboard repeat or toggle macros that G HUB refuses to write. Firmware support on this model is UNCONFIRMED and needs testing.
- G HUB publishes no limit on the number of macros or on macro length. UNCONFIRMED.
- **Game integrity change.** G HUB **2022.3.242300** "updated how macros are executed… to improve game integrity in multiplayer games". Since then, macros may fail in games running at a different privilege level, and the workaround is to run G HUB at the same elevation as the game [S23]. Some games treat turbo-click macros as cheating; there is an anecdotal Battlefield 6 ban report [S24].

**Storage.** Simple No-Repeat key/button/text macros: [BOTH], since they can be written onboard. Everything else: [SOFTWARE].

---

## 5. Lighting (LIGHTSYNC)

### 5.1 Zones

- There are **two independent RGB zones** (probe).
  - **PRIMARY** is the 3-LED DPI-indicator strip on the left side.
  - **LOGO** is the G logo on the palm.
  - G HUB shows a **PRIMARY | LOGO** zone selector for mice, plus a **SYNC LIGHTING ZONES** button that copies one zone's settings to the other [S1].
  - A third-party extraction of G HUB's device data names the zones `primary` / `branding` [S40].
  - Logitech's spec sheet says "1 zone" [S5], which is wrong in practice.
- **DPI indicator behaviour (firmware).** The 3 LEDs show which of the 5 DPI levels is active. On an onboard profile switch they turn **blue for 3 s** and show the profile number [S2].
  - If software takes LED control through 0x1300, the firmware's DPI/profile indication stops [S40]. This matters for a Linux tool that uses 0x1300.
  - The G HUB DPI-level colours (§1) drive the indicator.
- Which onboard LED slot (0 or 1) maps to which zone is **UNCONFIRMED**, and the hints conflict. HID++ 0x8070 has zone 0 = primary, but one library and Piper draw LED 0 on the logo. Test it on the device.

### 5.2 Effects

From the 2020 manual [S1] for mouse zones, with the hardware capability from the probe.

| G HUB effect | Parameters (G HUB) | Runs where |
|---|---|---|
| **OFF** | none | [BOTH]: hardware effect 0x00 |
| **FIXED** | colour wheel + R/G/B fields + brightness slider; colour swatches | [BOTH]: hardware 0x01 (colour + "ramp" byte; G HUB sends no-fade) [S40] |
| **CYCLE** (colour cycle) | **RATE**, the time for one full cycle ("shorter = quicker"), and **BRIGHTNESS 0–100 %** | [BOTH]: hardware 0x03 (period ms + intensity 1–100) [S30] |
| **BREATHING** | colour, brightness, rate | [BOTH]: hardware 0x0A (colour, period ms, waveform, intensity) [S30] |
| **SCREEN SAMPLER** | **EDIT** opens the sampler editor. Mice get 2 active samplers: by default the top-left sampler → PRIMARY and the bottom-left → LOGO, and you click a zone to reassign. Options: **ADD NEW SAMPLE**, **REFRESH SCREEN**, **SELECT REFERENCE IMAGE**, **ADVANCED SETTINGS → COLOR BOOST** (default 33 %), **SMOOTHING** [S1] | [SOFTWARE]: colours streamed live |
| **AUDIO VISUALIZER** | **COLOR MODE**: FIXED (background + colour) or REACTIVE (background, low colour, high colour). **ADVANCED SETTINGS**: *Pulse on bass only*, *Audio boost* 0–100 % (30 % suggested), *Use adaptive max amplitude*, *Custom max amplitude*, *Bass noise threshold*, *Mid-high noise threshold* [S1] | [SOFTWARE] |
| **ANIMATIONS / FREESTYLE / Starlight / Ripple / Color Wave / Echo Press** | These are documented as *keyboard* features [S1]. Whether the G502 HERO's mouse UI lists any animation preset is **UNCONFIRMED**; the most likely list for this mouse is Off / Fixed / Cycle / Breathing / Screen Sampler / Audio Visualizer [S40]. | [SOFTWARE] if present |

Ranges and capabilities:

- The hardware period range commonly used is about **1 000–20 000 ms**, with intensity 1–100 %. These are third-party limits [S40]; libratbag reads a cycle duration of 8000 ms from the factory profiles (probe).
- G HUB's own slider ranges for mouse Cycle and Breathing are **UNCONFIRMED**. For comparison, Yeti X breathing in G HUB runs 1000–20000 ms [S1].
- There is **no direction parameter**: there is no hardware wave effect, and direction exists only for keyboard Color Wave [S1].

### 5.3 Lighting settings

- **Per-profile lighting** is the default: each G HUB profile, and each onboard profile, has its own effect. The **per-profile LIGHTSYNC lock** (padlock) makes lighting the same across all profiles [S1], [S40].
- **SYNC LIGHTING OPTIONS** syncs the scheme and timing with other LIGHTSYNC gear, with UNSYNC to undo [S1]. It only works between compatible lighting hardware [S40].
- **Startup effect.** The device settings reportedly include "device startup color effects" (TechRepublic on the G502 HERO [S41]). The exact label, and whether it is written to the device, are **UNCONFIRMED**.
- **Inactivity / power-saving.** The global **LIGHTING** setting dims or turns off lighting after inactivity "to help with power saving on wireless devices" [S1]. I found no per-device "turn off after X minutes" control for this wired mouse, and its onboard timeout fields are unset (0xFF) [S40]. This is UNCONFIRMED for the current UI.
- **Game control.** **ALLOW GAMES & APPLICATIONS TO CONTROL MY ILLUMINATION** lets LIGHTSYNC-SDK games (shown as "LED"-type integrations, e.g. bfv.exe [S1]) take over the lighting. The Games beta marks LIGHTSYNC-enabled titles (2026.5) [S37]. How SDK zones map onto this mouse is UNCONFIRMED.
- **Windows Dynamic Lighting.** Since G HUB 2024.1 every LIGHTSYNC RGB device can be driven by Windows 11 Dynamic Lighting (build 22621+) [S37]. While it is active, G HUB's own lighting controls are locked [S40].
- **Stored effects.** A support article says the firmware must always hold at least one stored effect, so G HUB lets you replace it but not delete it [S40].
- **Persistence.** In software mode, even "Off" only holds while the G HUB agent runs [S40].
- **Lighting sharing.** You can share or download lighting effects through the community [S1].
- **Lua** cannot control mouse lighting: `SetBacklightColor` is a stub (§7).

Storage summary:

- **[ONBOARD]:** Off, Fixed, Breathing and Cycle per zone. The profile has 2 LED blocks plus 2 "alt" LED blocks. The alt blocks are probably the power-save or alternate state; libratbag writes copies [S30], [S40], so their purpose is UNCONFIRMED.
- **[SOFTWARE]:** Screen Sampler, Audio Visualizer, animations, device sync, game lighting, Dynamic Lighting.

## 6. Profiles and onboard memory

### 6.1 G HUB software profiles: all [SOFTWARE]

**Structure.** Games & Applications ("apps") each own one or more **user profiles**. Only one is active per app [S1].

- The **DESKTOP** app and its **Default** profile always exist and cannot be deleted [S1].
- In the profile manager [S1]:
  - Tabs: **PROFILES | MACROS | INTEGRATIONS | SETTINGS**.
  - **DETAILS** shows which gear is set up in the profile, with **DELETE**. The default user profile cannot be deleted.
  - **Duplicate User Profile**, **Create a new User Profile**, **Scripting**, **Share**.

**Automatic game and app switching** [S1]:

- G HUB "automatically detects games and sets up profiles", and the profile "will automatically activate when that game is running". Community reports say activation follows focus [S42].
- **SCAN NOW** rescans for installed games. **+ ADD GAME OR APPLICATION** points a new profile at an executable.
- The app **SETTINGS** tab shows NAME and PATH, with **+ ADD CUSTOM PATH** for an extra executable path. **STATUS** is *Installed* (detected) or *Custom Application*.
- The **PROFILE SWITCHING** toggle enables or disables automatic activation. Disabling it is how you blacklist an app.
- **FORGET APP** deletes a user-added app or one marked "uninstalled", along with its profiles and macros [S1].
- Built-in game profiles come with game **Commands** and **integrations** (e.g. LED integrations) [S1].
- Anti-cheat or protected processes can stop detection; the workaround is selecting the profile manually [S42].

**Other controls:**

- **PERSISTENT PROFILE** (global settings) picks one profile that is used for *all* apps and disables switching. It defaults to NONE, and the home screen shows a lock symbol while it is active [S1].
- **Per-feature locks.** Padlocks on the Assignments, Sensitivity and LIGHTSYNC tabs make that part of the configuration identical for all profiles [S1].
- **Profile Cycle** (System → G HUB group) cycles through the user profiles of the current app [S1].
- **Copying.** Drag a profile, or a macro, onto another app to duplicate it [S1].

**Share, import, export and backup:**

- **Share** publishes a profile, private or public, to the G HUB cloud. This needs a Logi ID. You can set NAME, description, TAGs, **INCLUDE ALL MACROS FOR THIS APPLICATION**, **MAKE THIS PROFILE PUBLIC** and **INCLUDE THESE DEVICES**. Public profiles are reviewed [S1]. Downloads come from the in-app profile and lighting galleries [S1], [S20].
- Downloaded profiles land under the Default profile, because app IDs differ between installs [S25].
- **IMPORT ALL PROFILES** migrates from LGS [S1].
- G HUB has **no plain "export profile to file"**. Before 2026.2 the only local backup was copying `settings.db` [S25]. G HUB **2026.2** added a **Local Settings Backup** (save, restore and delete via *Manage Profile*) [S37].
- 2025.4 added an "Improved profiles experience (early access)" toggle in Settings [S37].

### 6.2 On-Board Memory mode

**Enabling it** [S1], [S34]:

1. Open the device's **GEAR SETTINGS** (cog).
2. Turn on the **ON-BOARD MEMORY MODE** toggle. It is OFF by default, which means G HUB software profiles apply.
3. While it is on, "all software control through G HUB will be paused for that device". A blue banner offers **ENABLE** software control, which turns onboard mode off again [S1].

**ON-BOARD MEMORY SLOTS.** This device has **5** slots (probe), one profile per slot. Each slot shows its state: active, cycle-able, or disabled. Each slot has a menu [S1]:

- **DETAILS** shows the slot's LIGHTSYNC, assignments and so on, with **DISABLE FROM MEMORY**.
- **DISABLE** removes the slot from the onboard profile cycle.
- **RESTORE DEFAULT PROFILE**.
- **ENABLE WITH NEW** or **REPLACE WITH** copies one of your G HUB profiles into the slot.
- **RESTORE ALL ON-BOARD PROFILES TO DEFAULT** resets every slot.

**Factory profiles** from the paper guide. The original firmware had 3, and **firmware 127.1.7 (Feb 2019) "enables profiles four and five"** but wipes the onboard profiles [S43], [S2]:

| | Profile 1 "High-DPI gaming" | Profile 2 "Low-DPI gaming" | Profile 3 "Standard" |
|---|---|---|---|
| DPI levels | 1200 / 2400 / 3200 / 6400 | 400 / 800 / 1600 / 2400 | 2400 |
| Default DPI | 2400 | 1600 | 2400 |
| DPI Shift | 1200 | 400 | n/a (G6 = G-Shift) |
| Report rate | 1000 | 1000 | **500** |
| Buttons | standard; G6 DPI Shift, G7/G8 DPI −/+, tilts scroll L/R, G9 next profile | same | G6 G-Shift, G7 Ctrl-C, G8 Ctrl-V, plus a G-Shift layer (§3) |

The probed unit has 5 profiles: 1200/2400/3200/6400, 400/800/1600/2400, 2800 (G-Shift profile, 500 Hz), 3200 and 6400. Each also has its own lighting.

**What one onboard profile stores** (libratbag struct [S30] and OpenGHub [S38]):

- report rate
- 5 DPI values, the default index and the DPI-shift index
- profile colour, power mode, angle-snapping byte, power-save and power-off timeouts
- **16 button bindings + 16 G-Shift bindings**
- a 48-byte UTF-16LE name
- 2 LED effects + 2 alt LED effects
- a CRC-16

Macros live in separate sectors. Factory (ROM) profiles also exist, at sectors 0x0101–0x0105 [S40].

**What onboard mode cannot do** (needs software):

- Repeat-While-Holding, Toggle and Sequence macros; emoji text [S4]
- integration Actions, Launch Application, Lua
- Screen Sampler, Audio Visualizer, game lighting
- per-app automatic switching
- cross-device G-Shift
- on-screen DPI/profile notifications, which are reported but UNCONFIRMED [S40]
- Community sharing

One user reported that G HUB did not keep Shift/Ctrl combos on side buttons in onboard memory [S44]. That is anecdotal.

**DPI-shift caveat.** Onboard, the DPI-shift value must be one of the 5 stored levels: the profile stores a *switched_dpi index* [S30]. The G HUB UI likewise marks one of the levels as the shift speed [S1].

**Switching onboard profiles.** The G9 button runs **Onboard Profile Cycle** by default; it "cycles through onboard memory profiles when G HUB is not running" [S1], [S2]. Special codes also exist for next and prev profile (§2.2).

**Mode persistence: conflicting reports.**

- libratbag users report that if G HUB leaves the mouse in **host mode**, the extra buttons do nothing on Linux. Current libratbag forces onboard mode on start [S40].
- OpenGHub (on a G502 LIGHTSPEED) says host mode is *not* persistent and reverts on reconnect [S38].
- Test this on this unit. The probe read mode `1` (onboard).

**Automatic per-game switching on Windows requires onboard mode OFF** (user report [S40]).


## 7. Lua scripting (G HUB "Scripting")

All of this is **[SOFTWARE]**: scripts run inside the LGHUB Agent process on the PC. Nothing is stored on the mouse, and a community report says scripts do not run with On-Board Memory Mode on [L13].

### 7.1 Documents and runtime

- **Reference documents.**
  - The G HUB doc is *"Logitech G HUB Lua API"*. Versions V2020.11 (46 pp.) and **V2023.5** (45 pp., "Standard Lua 5.4 Libraries" p.42, key table Appendix A p.44) exist [L1–L4].
  - In the app you open it via Script editor → SCRIPT menu → *Scripting API* [S1], [L4].
  - The LGS predecessor is *"G-series Lua API V8.45 Overview and Reference"* (44 pp., Lua 5.1) [L5]. V8.50 exists only on Scribd [L6].
  - I found no doc newer than V2023.5. No release note from 2023 to 2026 changes the API; the latest is G HUB 2026.6.974819 (Sep 2026) [S37].
- **Lua version.** G HUB embeds **Lua 5.4** (`//` works); LGS used 5.1 [L7].
- **Where scripts are attached.** Open the profile manager, select the profile and click the **Scripting** icon. Then pick a script in **ACTIVE LUA SCRIPT** (or NONE), or choose **+ CREATE A NEW LUA SCRIPT**. Each script has a name and a description, and **EDIT SCRIPT** opens the editor. Scripts are not tied to one profile and can be applied to any [S1].
- **Editor.**
  - Menus: **Script** (Save / *Save and Run* Ctrl+S, Import .lua, Export .lua, Close); **Edit** (Undo, Redo, Cut, Copy, Paste, Delete, Find Text, Select All, Clear Output); **View** (line numbers, output, highlighting); **Help** (*Scripting API*, *Lua Online Reference*) [S1].
  - The output pane shows `LOADED` [L4].
  - The editor was restyled in 2021.10, and 2022.2.x fixed create/edit/delete bugs [S37].
- **Storage.** Scripts live at `%LOCALAPPDATA%\LGHUB\scripts\<GUID>\script.lua`. An uncaught `error({table})` can crash-loop the Agent [L4].
- **Lifecycle.** On profile deactivation G HUB waits about 1 s, then force-aborts the script. 2025.2.687008 fixed a crash when a script ran during a profile change or sleep [S37].
- **Threading.** OnEvent calls are serialised, so a long handler blocks later events. The common pattern is a `repeat … Sleep(10) … until not IsMouseButtonPressed(n)` loop. How presses are queued during a long handler is UNCONFIRMED [L8].

### 7.2 Entry point and events

`function OnEvent(event, arg [, family])` is required.

`family` is one of `"kb"` (keyboards), `"lhc"` (left-handed controllers such as the G13) or **`"mouse"`** (this device). It is empty for events that do not come from hardware [L1], [L5].

| event | arg |
|---|---|
| `PROFILE_ACTIVATED` | none. In current G HUB, arg is **nil** (older versions passed 0), so `("%d"):format(arg)` errors [L9]. It fires when the profile becomes active, for example when an application gains focus. |
| `PROFILE_DEACTIVATED` | none |
| `G_PRESSED` / `G_RELEASED` | G-key number (keyboards and left-handed controllers; not used by the G502) |
| `M_PRESSED` / `M_RELEASED` | M-key 1–3 (keyboards) |
| `MOUSE_BUTTON_PRESSED` / `MOUSE_BUTTON_RELEASED` | the mouse button's G-number. **Button 1 (left) is reported only after `EnablePrimaryMouseButtonEvents(true)`.** |

**G502 HERO arg numbers.** arg is the G-number:

- 1 left, 2 right, 3 middle, 4 back, 5 forward
- 6 DPI-Shift (G6), 7 DPI-Down (G7), 8 DPI-Up (G8), 9 profile button (G9)
- **11 = wheel tilt left**, confirmed by a G502 HERO user [L10]
- **10 = wheel tilt right**, inferred. libratbag's index order (9 = right, 10 = left; probe) agrees.
- The wheel-mode toggle is not reported.

Numbering differs by model: the G502 X uses other numbers [L10].

**Gotchas**

- There are two numbering schemes. The event arg uses 2 = right and 3 = middle. `PressMouseButton`, `ReleaseMouseButton`, `PressAndReleaseMouseButton` and `IsMouseButtonPressed` use **1 L, 2 M, 3 R, 4 X1, 5 X2** (only 1–5) [L1], [L11].
- `IsMouseButtonPressed`, `IsModifierPressed` and `IsKeyLockOn` read the **OS-wide logical state**. That is the state of the *assigned output*, coming from any device. Scripts therefore often bind a G-button to "Back" and poll `IsMouseButtonPressed(4)` [L12].
- Ordinary keyboard keys **never** generate events. This is by design, as an anti-keylogger measure. Wheel scrolling cannot be captured either, only generated [L14], [L15].
- No API reports the G-Shift state. The G-Shift button itself still raises a MOUSE_BUTTON event [L16], [S19]. How args are numbered on the shifted layer is UNCONFIRMED.
- Whether a button bound to a DPI or profile function, or set to Disabled, still raises events is UNCONFIRMED.

### 7.3 Function reference

Status key: **OK** = works in G HUB. **STUB** = the name exists but the doc says "not implemented in G HUB". **ABSENT** = not in the G HUB global table [L1], [L2], [L17].

| Function | Notes | Status |
|---|---|---|
| `GetMKeyState([family])` / `SetMKeyState(m,[family])` | Keyboard M-keys (1–3). Meaningless on the G502. | OK |
| `Sleep(ms)` | Uses Windows Sleep, so it has about 10–15.6 ms granularity and `Sleep(1)` is unreliable [L18] | OK |
| `OutputLogMessage(fmt, ...)` | string.format into the editor log. Add `\n` yourself. | OK |
| `OutputDebugMessage(fmt, ...)` | Goes to the Windows debugger (OutputDebugString) | OK |
| `ClearLog()` | | OK |
| `GetRunningTime()` | ms since the script started | OK |
| `GetDate([fmt[, time]])` | Same as `os.date` | OK |
| `PressKey(k, ...)` / `ReleaseKey(k, ...)` / `PressAndReleaseKey(k, ...)` | Key names or scancodes, one or many | OK |
| `IsModifierPressed(name)` | `lalt ralt alt lshift rshift shift lctrl rctrl ctrl` | OK |
| `IsKeyLockOn(name)` | `scrolllock capslock numlock` | OK |
| `PressHidKey` / `ReleaseHidKey` / `PressAndReleaseHidKey` | **Undocumented**, present in the global table. They presumably take HID usage IDs [L17], [L19]. | OK? (UNCONFIRMED semantics) |
| `PressMouseButton(b)` / `ReleaseMouseButton(b)` / `PressAndReleaseMouseButton(b)` | b = 1–5 (L, M, R, X1, X2). 2024.1 fixed "certain mouse buttons were simulated incorrectly" [S37]. | OK |
| `IsMouseButtonPressed(b)` | b = 1–5, logical OS state | OK |
| `MoveMouseTo(x, y)` | Absolute, 0–65535 normalised on the primary monitor | OK |
| `MoveMouseToVirtual(x, y)` | 0–65535 across the whole virtual desktop | OK |
| `GetMousePosition()` | Returns x, y in 0–65535 | OK |
| `MoveMouseRelative(dx, dy)` | +x right, +y down. **Limited to −127…+127 per call**, so split bigger moves. Affected by Windows "Enhance pointer precision". [L20] | OK |
| `MoveMouseWheel(n)` | + up, − down | OK |
| `EnablePrimaryMouseButtonEvents(bool)` | Enables arg = 1 events | OK |
| `PlayMacro(name)` | Plays a G HUB macro (by name, from this profile's macro list) by simulating a virtual macro key held for 100 ms. Only one script macro plays at a time: a different one is ignored, the same one is queued. | OK |
| `PressMacro(name)` / `ReleaseMacro(name)` | **G HUB-only.** Separate press and release, which allows Sequence or hold macros. | OK |
| `AbortMacro()` | Stops script-started macros and releases their keys | OK |
| `SetMouseDPITable(tbl[, idx])` / `SetMouseDPITableIndex(i)` | **DPI cannot be changed from Lua in G HUB.** The workaround is `PlayMacro` on a macro containing a DPI system command [L21]. | **STUB** |
| `SetBacklightColor(r, g, b[, family])` | Lighting cannot be controlled from Lua | **STUB** |
| `SetMouseSpeed` / `GetMouseSpeed` / `IncrementMouseSpeed` / `DecrementMouseSpeed` | G13 joystick (LGS) | **STUB** |
| `OutputLCDMessage`, `ClearLCD`, `SetSteeringWheelProperty` | LGS only. Calling them gives "attempt to call a nil value". | **ABSENT** |

### 7.4 Sandbox

- The G HUB `_G` holds **66 names**: the Logitech functions above, plus `type dofile loadfile load warn error pcall xpcall rawset rawget rawequal rawlen select assert print collectgarbage next pairs ipairs setmetatable getmetatable tostring tonumber _G _VERSION`, plus the tables `string table math debug` [L17].
- **Absent:** `os`, `io`, `package`/`require`, `utf8`, and (per the dump) `coroutine`. One 2022 answer used `coroutine.wrap` in G HUB [L22], so coroutine availability is UNCONFIRMED.
- `dofile` and `loadfile` **work**, so scripts can load .lua files from disk. Scripts cannot write files or launch programs; the workaround is `PlayMacro` on a Launch-Application macro.
- String literals must be ASCII (use escapes otherwise). Globals are lost between profile activations [L1].
- Libraries listed in V2023.5:
  - math: `abs acos asin atan ceil cos deg exp floor fmod huge log max maxinteger min mininteger modf pi rad random randomseed sin sqrt tan tointeger type ult`
  - string: `byte char dump find format gmatch gsub len lower match pack packsize rep reverse sub unpack upper`
  - table: `insert move pack remove sort unpack`. `concat` is probably present but missing from the transcription.

### 7.5 Key names (Appendix A)

There are 116 names. Values are **PS/2 set-1 scancodes**, with 0x1xx meaning E0-extended. The table is identical in LGS 8.45 and G HUB [L1], [L5].

- **Function keys:** `escape`=0x01, `f1`–`f10`=0x3b–0x44, `f11`=0x57, `f12`=0x58, `f13`–`f23`=0x64–0x6e, `f24`=0x76.
- **System keys:** `printscreen`=0x137, `scrolllock`=0x46, `pause`=0x146.
- **Number row:** `tilde`=0x29, `1`–`0`=0x02–0x0b, `minus`=0x0c, `equal`=0x0d, `backspace`=0x0e, `tab`=0x0f.
- **Letter rows:**
  - `q`–`p`=0x10–0x19, `lbracket`=0x1a, `rbracket`=0x1b, `backslash`=0x2b
  - `capslock`=0x3a, `a`–`l`=0x1e–0x26, `semicolon`=0x27, `quote`=0x28, `enter`=0x1c
  - `lshift`=0x2a, `non_us_slash`=0x56, `z`–`m`=0x2c–0x32, `comma`=0x33, `period`=0x34, `slash`=0x35, `rshift`=0x36
- **Bottom row:** `lctrl`=0x1d, `lgui`=0x15b, `lalt`=0x38, `spacebar`=0x39, `ralt`=0x138, `rgui`=0x15c, `appkey`=0x15d, `rctrl`=0x11d.
- **Navigation:** `insert`=0x152, `home`=0x147, `pageup`=0x149, `delete`=0x153, `end`=0x14f, `pagedown`=0x151, `up`=0x148, `left`=0x14b, `down`=0x150, `right`=0x14d.
- **Numpad:** `numlock`=0x45, `numslash`=0x135, `numminus`=0x4a, `num7`–`num9`=0x47–0x49, `numplus`=0x4e, `num4`–`num6`=0x4b–0x4d, `num1`–`num3`=0x4f–0x51, `numenter`=0x11c, `num0`=0x52, `numperiod`=0x53.
- `numstar` (0x37) is missing from the table, but the number works. There are no media keys.
- **Linux tip:** non-extended set-1 codes equal evdev `KEY_*` codes (KEY_A = 30). Extended codes need a lookup, for example 0x11d → KEY_RIGHTCTRL.

### 7.6 Anti-cheat and fair-play context

- G HUB 2022.3.242300 changed macro execution "to improve game integrity". G HUB and the game must run at the same privilege level [S23].
- FACEIT explicitly bans "no-recoil scripts" [L23].
- I found no evidence that Logitech blocks Lua in particular games.

## 8. Other features and settings

### 8.1 G HUB app (global) settings: all [SOFTWARE]

From the 2020 manual [S1]. Since then the settings screen has been "refreshed" (2025.2) and device settings moved to the bottom left of the app (2023.2) [S37].

- **START UP** runs G HUB at login. Without it, "profiles [won't] activate", because automatic switching needs G HUB running.
- **LIGHTING** is on by default. It is a power-saving lighting timeout for inactivity, "to help with power saving on Wireless devices". Untick it to keep lighting on. See §5 for details.
- **ALLOW GAMES & APPLICATIONS TO CONTROL MY ILLUMINATION** lets LIGHTSYNC-SDK games override effects.
- **ANALYTICS** is off by default.
- **PERSISTENT PROFILE** selects one profile that overrides all automatic switching (§6).
- **LANGUAGE**, **DESKTOP NOTIFICATIONS** and **SHOW TUTORIAL AGAIN**.
- **IMPORT ALL PROFILES** migrates from Logitech Gaming Software.
- **CHECK FOR UPDATE**, **VERSION** (Year.Version.Build) and **SEND FEEDBACK**.
- **ARX CONTROL** was a phone and tablet companion (DPI on the fly, macro list). It was **removed in G HUB 2022.7**; the app was pulled 24 Aug 2022 [S36].
- **Beta Features:**
  - "Games" library tab: launch and organise games from Steam, GoG, WeGame and others [S21]. Beta on Windows in 2025.9, enabled by default in 2026.2, Riot launcher added in 2026.6 [S37].
  - "Improved profiles experience (early access)" in 2025.4 [S37].
- **Local Settings Backup** (2026.2) saves, restores and deletes copies of device settings via *Manage Profile*. Before that, the only backup was copying `settings.db` [S37], [S25].
- **Windows "reinstall keeping user settings"** after a failed update (2024.6) [S37].

### 8.2 Assignable OS commands added recently

- **Windows Copilot** as an assignable command (2024.2) [S37].
- 2026.6 fixed "OS-specific shortcuts" in the commands panel [S37].

### 8.3 Firmware: [SOFTWARE]

- The Gear settings (cog) page shows the firmware version and offers updates [S20], [S1].
- Updates use the signed DFU feature 0x00C2 (probe). During an update the mouse re-enumerates as `046d:aae6`, the bootloader PID (probe, [S39]).
- Known G502 HERO firmware history:
  - **127.1.7** (Feb 2019) enables onboard profiles 4 and 5 and wipes the onboard profiles [S43].
  - **127.3.10**, "Improved click debouncing", shipped with G HUB 2020.4 and 2020.7 [S37].
  - **25 600 DPI was enabled for the G502 HERO in G HUB 2020.8.5950** (15 Sep 2020) [S37], [S6].
  - No later G502 HERO firmware appears in the 2023–2026 release notes. The only 2023–2026 G502 HERO item is new Pink & Purple colourways in 2025.8 [S37].
- I found no Linux tool that flashes this mouse's firmware (UNCONFIRMED; I did not look at fwupd in detail).

### 8.4 Not applicable to the G502 HERO

These G HUB features exist but **not for this mouse**:

- **Game Mode** and "disable keys" are keyboard-only [S1]. On a mouse, use per-button **DISABLE**.
- **KEYCONTROL** (15 functions per key with modifiers and event types) is for keyboards only [S13].
- **Battery, power mode and sleep timers** apply to wireless mice; G304/G305 have a "Power mode" [S37]. The onboard profile format has `powersave_timeout`/`poweroff_timeout` fields [S30], but they are irrelevant when wired.
- **HERO 2 features** (X/Y DPI, LOD, mouse-feet calibration, sensitivity matching, 2/4/8 kHz) [S8].
- **"BHOP mode"** for the scroll wheel exists only on PRO X SUPERLIGHT 2 and PRO 2 [S37].
- **"Smart" features** (Smart Actions, SmartShift, app-specific gestures) belong to **Logi Options+**, not G HUB. G HUB has no "Smart" mouse features for the G502 HERO.
- **"Disable G-keys"** is not a G HUB mouse option.

---

## 9. Onboard vs software summary

| Feature | Onboard (no software) | Needs G HUB running |
|---|---|---|
| DPI levels (up to 5), DPI-shift level, default level | ✔ per onboard profile | live edit |
| Report rate 125–1000 Hz | ✔ per onboard profile | live edit |
| Remap to mouse buttons, single key + modifiers, media/consumer keys | ✔ | |
| DPI up/down/cycle/shift/default, onboard-profile next/prev/cycle | ✔ | |
| Disable button | ✔ | |
| G-Shift layer (same mouse) | ✔ (16 alternate bindings per profile) | |
| G-Shift synchronised across devices | | ✔ |
| No-Repeat macro: keys, mouse buttons, delays, plain text with modifiers | ✔ | |
| Repeat-While-Holding / Toggle / Sequence macros; emoji text | ✘ (G HUB refuses; the bytecode may allow repeat, untested) | ✔ |
| Macro steps: Action (OBS/Discord/Streamlabs…), Launch Application, G HUB Profile Cycle | ✘ | ✔ |
| Lua scripts | ✘ | ✔ |
| Lighting: Off / Fixed / Breathing / Cycle per zone | ✔ (2 zones, also an alt-LED block) | live edit |
| Lighting: Screen Sampler, Audio Visualizer, Animations, game LIGHTSYNC, Windows Dynamic Lighting, sync across devices | ✘ | ✔ |
| Automatic per-app profile switching, persistent profile, user profiles | ✘ | ✔ |
| Onboard profile switching by button | ✔ (Onboard Profile Cycle / G9) | |
| Firmware update | n/a | ✔ (signed DFU, 0x00C2) |

(Lighting and onboard details are expanded in §5/§6.)

---

## 10. Implementation notes for a Linux replacement

- **Two device modes.**
  - Onboard (0x8100 mode `1`): the probed mouse is currently in this mode.
  - Host (0x8100 mode `2`): software control.
  - Per OpenGHub's work on a G502 LIGHTSPEED, in onboard mode `setSensorDpi` and `setReportRate` are refused with error 0x02, and 0x8070 lighting writes are *accepted but ignored*. Host mode **does not persist** across reconnects [S38]. libratbag users report the opposite on G502 HERO units (see §6.2), so test this.
  - Either way, an "onboard memory mode = off" emulation should re-assert host mode on every hot-plug, resume and so on. On exit it should restore onboard mode, so the mouse is never left with dead extra buttons.
- **Software-mode button handling.**
  - This mouse has no 0x1B04. G HUB-style software remapping uses **0x8110 Mouse Button Spy**: divert the buttons, receive HID++ button notifications, synthesise output.
  - G HUB synthesises through virtual keyboard and mouse devices [S27]; on Linux that would be uinput.
  - The G-Shift layer in software mode is just a second remap table, active while the shift button is held [S38].
- **Onboard writes.**
  - Memory is 16 sectors × **255 bytes**. Each sector ends with a **CRC-16/CCITT** (poly 0x1021, init 0xFFFF) [S38]. Sector 0 is a profile directory [S38].
  - The profile format ID is 2 on this mouse (probe). OpenGHub documents format 3 on a G502 LIGHTSPEED, so verify offsets against libratbag's `hidpp20_internal_profile` [S30]. That struct holds:
    - report_rate, default_dpi idx, switched_dpi idx, dpi[5], profile_color, power_mode, angle_snapping
    - powersave and poweroff timeouts
    - 16 buttons + 16 alternate (G-Shift) buttons, a 48-byte name
    - 2 LEDs + 2 alt-LEDs, CRC
  - **Back up all sectors before writing**, as OpenGHub does [S38].
  - libratbag/Piper (installed here, v0.18) already reads and writes this mouse's 5 profiles, 5 DPI slots, 11 buttons and 2 LEDs. Its `.device` file uses `Driver=hidpp20`, `Quirk=INDEX_OFFSET` [S30].
- **Importing G HUB data.**
  - `settings.db` is SQLite with a JSON blob. Macros are `cards[]` with `attribute: MACRO_PLAYBACK`, and key events use HID usage IDs [S25].
  - Lua scripts are plain `.lua` files.
  - Lua key names are set-1 scancodes (see §7.5).
- **Prior art.**
  - **OpenGHub** (MIT, Rust/Tauri/Svelte, started around Sep 2026) is an open-source "G HUB for Linux" over hidraw. It covers DPI, report rate, lighting, assignments, G-Shift, macros, onboard profiles, settings.db import and a G HUB-compatible Lua subset. It was developed against a G502 LIGHTSPEED; G502 HERO support depends on its generic HID++ path [S38].
  - OpenGHub's device registry lists `0xc08b` as "G502 HERO" (`src-tauri/src/hidpp/registry.rs`) [S38].
  - **HolyJoey/Lghub** ("G HUB reverse-engineered for Linux") was created 2026-10-17. It has 0 stars and is unverified, but it has a protocol write-up [S45].
  - libratbag/Piper [S30] supports this mouse's 5 profiles, DPI, report rate, buttons and LEDs. It does **not** support the G-Shift layer (issue #598), and it writes "disabled" buttons incorrectly (issue #1898) [S40].
  - Solaar lists the device and its features [S39]. mhub-go is a G HUB Lua re-implementation in Go, for Windows [L24].
- **0x8110 notification format.** Notifications are a 16-bit pressed-button bitmap (libratbag issue #1831) [S40]. The bit-to-button order reported there (0 L, 1 R, 2 M, …, 9 tilt-right, 10 tilt-left) should be verified on this unit.
- **Lua compatibility target.** Implement the "OK" set in §7.3, including the undocumented `*HidKey` functions and `PressMacro`/`ReleaseMacro`. Treat the DPI and backlight setters as no-ops, which matches G HUB. Use Lua 5.4. Drop `os`, `io` and `require`, but keep `dofile`/`loadfile`.
- **App-detection profile switching.** G HUB activates a profile when the associated executable runs or is focused (§6). On Linux this needs X11 `_NET_ACTIVE_WINDOW`, compositor-specific Wayland protocols (KDE: KWin scripting/D-Bus), or `/proc` process scanning.
- **Lua `MOUSE_BUTTON_*` emulation.** Map the 0x8110 bits to G-numbers 1–11 (§7.2). Wheel events are never delivered to scripts.

---

## 11. Unconfirmed items and open questions

1. **Exact current SYSTEM-tab labels.** These include "DPI Cycle" vs "DPI Cycling", the mouse-click entry names, the full Media/Editing/Audio item lists, and whether "DPI Default" or prev/next onboard profile are exposed. The only screen-by-screen manual is from 2020, and Reddit (the usual source for screenshots) was not reachable.
2. **Whether the current Sensitivity tab shows a separate "Default DPI" marker** for the G502 HERO, as opposed to only the DPI-Shift diamond.
3. **Wheel-tilt G-numbers.** Lua arg 11 = tilt left is confirmed by one user; arg 10 = tilt right is inferred. Whether the G HUB UI labels them "G10/G11" is unknown.
4. **The exact effect list G HUB shows for this mouse** (are any Animations presets offered for mice?) and G HUB's Cycle/Breathing rate slider ranges.
5. **The "startup effect" option** (label and storage) and any per-device lighting inactivity timeout on this wired model.
6. **Onboard LED slot 0/1 ↔ PRIMARY/LOGO mapping**, and the purpose of the "alt LED" blocks.
7. **Host vs onboard mode persistence** across replug and reboot on *this* unit (reports conflict).
8. **This unit's firmware (U1 69.00.B0009 / BL2 40.00.B0009) and profile format 2** differ from the commonly documented G502 HERO (U1 27.03.B0010, 127.x.y). It is unknown whether G HUB shows this as "169.0.9" and whether onboard layouts differ.
9. **Whether onboard repeat/toggle macro opcodes** (present in the format) actually execute on this firmware.
10. **Whether the onboard `angle_snapping` profile byte has any effect** on this sensor.
11. **G HUB macro limits** (events per macro, number of macros) and whether macro recording ever captures mouse movement (believed not).
12. **Lua details:** coroutine availability; what `PressHidKey` & co. do; whether DPI-bound, profile-bound or disabled buttons still raise `MOUSE_BUTTON_*`; G-Shift-layer arg numbering; how events queue during a long handler.
13. **The current integration list** (Discord, OBS, Streamlabs, Overwolf, Litra…) and each one's complete action set. Overwolf may no longer be offered.
14. **Profile-switching trigger semantics**: process running vs foreground focus.
15. **Whether a modifier selector exists on the KEYS tab for mouse buttons.** For keyboards it is documented as KEYCONTROL.

---

## Sources

**Logitech official**

- [S1] *G HUB Manual*, Logitech, 114 pp., 2019–2020: https://m.media-amazon.com/images/I/C1R-DLHU0bS.pdf (the earlier *G HUB Early Access Manual*, 47 pp., is at https://images-eu.ssl-images-amazon.com/images/I/B19YbRens5S.pdf)
- [S2] G502 HERO Setup Guide: https://www.logitech.com/assets/65517/5/g502-hero.pdf
- [S3] G-Keys in Logitech G HUB: https://support.logi.com/hc/en-us/articles/4412850686231
- [S4] Some macros do not work when in Onboard Memory mode: https://support.logi.com/hc/en-us/articles/22102343233943
- [S5] G502 HERO product and store pages:
  - https://www.logitechg.com/en-us/products/gaming-mice/g502-hero-gaming-mouse.910-005469.html
  - https://logitech.com/en-kw/shop/p/g502-hero-gaming-mouse (spec lines "Up to 5 profiles (requires firmware 127.1.7)", "LIGHTSYNC RGB: 1 zone", "100 – 25,600 dpi")
- [S6] Logitech blog, HERO 25K (2020-09-15): https://www.logitech.com/blog/2020/09/15/logitech-g-introduces-hero-25k-sensor-the-industrys-highest-performing-dpi-offering/
- [S8] HERO 2 sensor guide: https://www.logitechg.com/en-us/software/guides/hero-2-sensor
- [S9] HERO 2 lift-off distance (PRO X SUPERLIGHT 2): https://support.logi.com/hc/en-gb/articles/16193588399511
- [S10] G HUB: Remove and create DPI speeds: https://support.logi.com/hc/en-us/articles/360023371613
- [S11] G HUB: Assign keyboard key commands and reset or disable buttons: https://support.logi.com/hc/en-001/articles/360023204494
- [S12] How do I remap keys on my gaming keyboard using G HUB: https://support.logi.com/hc/en-gb/articles/22045914815895
- [S13] KEYCONTROL guide: https://www.logitechg.com/en-us/software/guides/keycontrol
- [S18] G600 G-Shift (LGS): https://support.logi.com/hc/en-ca/articles/360023248894
- [S20] G HUB basics: https://www.logitechg.com/en-us/software/guides/g-hub-basics
- [S21] G HUB Games guide: https://www.logitechg.com/en-us/software/guides/ghub-games
- [S23] My G HUB macros do not work in some games: https://support.logi.com/hc/en-us/articles/5299965548055
- [S28] G502 pointer settings (LGS, original G502): https://support.logi.com/hc/en-gb/articles/360023420373
- [S29] G502 X setup guide (G HUB-era onboard table with "Default DPI"): https://www.logitech.com/assets/66240/g502-x-corded-gaming-mice-artanis.pdf
- [S34] Enable On-Board Memory mode with G HUB: https://support.logi.com/hc/en-gb/articles/6505257646743
- [S36] G HUB release page noting Arx Control removal (2022.7): https://support.logi.com/hc/en-au/articles/7721736744343-Logitech-G-HUB
- [S37] G HUB Update Release Notes (2020–2026.6): https://support.logi.com/hc/en-us/articles/360048967733-G-HUB-Update-Release-Notes. For the current download page (2025.8 era) see also https://support.logi.com/hc/en-au/articles/35798083776919
- [S43] G502 HERO Firmware Update 127.1.7: https://support.logi.com/hc/en-001/articles/360025289793-G502-HERO-Gaming-Mouse-Firmware-Update
- Further Logitech articles on persistent profile, locks, blacklist, Dynamic Lighting and stored effects are listed under [S40].

**Code, protocol and community**

- [S7] Gaming Nexus on HERO 25K: https://www.gamingnexus.com/News/44989/Logitech-is-upgrading-the-HERO-sensor-and-some-of-you-might-have-it-right-now
- [S14] Streamlabs × G HUB integration guide: https://streamlabs.com/content-hub/post/g-hub-x-streamlabs-integration-guide
- [S15] Discord community thread on the G HUB integration: https://support.discord.com/hc/nl/community/posts/360057980211-Logitech-G-HUB-integration
- [S16] SlurpTech G HUB macro guide (primary-click overwrite confirmation, macro editor): https://slurptech.com/logitech-g-hub-macro/ and the iFixit answer on swapping primary buttons: https://www.ifixit.com/Answers/View/732861/My+Primary+and+Secondary+Click's+Were+Switched!
- [S17] How-To Geek, repurposing G502 DPI buttons ("Onboard Profile Cycle" → "DPI Cycle"): https://www.howtogeek.com/logitech-gaming-mouse-repurpose-the-dpi-buttons-as-universal-buttons/
- [S19] GHub-ShiftKey-Extra (Lua modifier layers, G-Shift button events): https://github.com/terminatorul/GHub-ShiftKey-Extra
- [S22] G502 SE HERO = same HERO 25K, 100–25 600 DPI (retail and Rtings):
  - https://www.bestbuy.com/site/product/6455869.p
  - https://www.rtings.com/mouse/tools/compare/logitech-g502-hero-logitech-g-pro-hero/1612/14863
- [S24] EA forum, G HUB turbo macro with "Use Standard Delays" off and a ban anecdote: https://forums.ea.com/discussions/battlefield-6-general-discussion-en/battlefield-6-was-wrongly-banned-please-help-me/13518357/replies/13697369
- [S25] G HUB settings.db migration gist (cards / MACRO_PLAYBACK JSON): https://gist.github.com/TheoKondak/5e98dc6bed63ed0490d968f929244609. The extractor tool is https://github.com/gabfv/logitech-g-hub-settings-extractor
- [S27] reWASD forum, "G Hub uses virtual mouse and keyboard devices to generate macro inputs": https://forum.rewasd.com/forum/rewasd/technical-questions-aa/226557-logitech-g502-macro-not-working-with-rewasd
- [S30] libratbag source:
  - src/hidpp20.h and src/hidpp20.c (onboard profile struct, button and special codes, macro opcodes, LED effects, sector CRC)
  - data/devices/logitech-g502-hero.device
  - https://github.com/libratbag/libratbag
- [S38] OpenGHub:
  - repository: https://github.com/Slyvan25/OpenGHub
  - docs/hidpp.md (host/onboard mode, sectors, CRC, G-Shift table, 0x8110)
  - src-tauri/src/hidpp/registry.rs
- [S39] Solaar device listing for C08B: https://github.com/pwr-Solaar/Solaar/blob/master/docs/devices/G502%20SE%20Hero%20Gaming%20Mouse%20C08B.txt
- [S40] Other sources found by the lighting and onboard research:
  - libratbag issues #1181 (raw HID++ dump of this mouse), #598 (G-Shift), #1286 / #1405 / #1125 (host-mode dead buttons), #1831 (0x8110 bitmap), #1898 (disabled bug)
  - cvuchener/hidpp profile_format.md: https://github.com/cvuchener/hidpp
  - OpenRGB Logitech controller sources
  - Roritharr/logitech-g502-led-off: https://github.com/Roritharr/logitech-g502-led-off
  - Logitech support articles (each at `support.logi.com/hc/articles/<id>`): 360023371013 (persistent profile), 360023371653 (assignment lock), 360023205674 (LIGHTSYNC lock), 360023370953 (duplicate), 360023206094 (blacklist), 360023205194 (forget app), 1500005396981 (settings location), 20684663312279, 20684693000471 and 20684861191575 (Dynamic Lighting), 35914460788887 (lighting sync compatibility), 36580165753367 (effects stored on device)
  - LIGHTSYNC guide: https://www.logitechg.com/en-gb/software/guides/lightsync-rgb
- [S41] TechRepublic, configuring G HUB (G502 HERO "device startup color effects"): https://www.techrepublic.com/article/how-to-configure-logitech-g-hub-software-mac/
- [S42] Profile-switching reports:
  - focus-based activation: https://community.adobe.com/t5/photoshop-ecosystem-discussions/logitech-gaming-hardware/m-p/10251125/highlight/true
  - detection blocked: https://steamcommunity.com/app/2183900/discussions/0/4763208113394319211
- [S44] Steam thread (onboard modifier bindings not kept): https://steamcommunity.com/discussions/forum/11/4298194337941583566
- [S45] HolyJoey/Lghub: https://github.com/HolyJoey/Lghub

**Lua**

- [L1] *Logitech G HUB Lua API V2023.5*, Lua 5.4 libs p.42, key table p.44. Copies and transcriptions:
  - https://www.scribd.com/document/676323350
  - https://gitcode.csdn.net/6aa0d5e41a35784c8420553e.html
  - https://github.com/userfn-git/MOUSE-GHUB
  - https://github.com/Noket/G-HUB-API-Wrappers (around lines 400 and 738–797 for Sleep and PlayMacro remarks)
- [L2] *G HUB Lua API V2020.11*: https://www.scribd.com/document/508273540
- [L3] Page map of the G HUB Lua API PDF: https://github.com/nora77zz/VXE-R1-SE-PLUS-NORA/blob/main/docs/lua-compatibility.md
- [L4] Script storage path, Agent crash loop and localized editor screenshots (SCRIPT/EDIT/VIEW, Save and Run, `LOADED`):
  - https://github.com/UserNameUnavailableIsUnavailable/blog/blob/main/Gaming/CSOL-Utilities/Executor/error.rmd
  - assets `lghub_scripts.avif` and `LGHUB_API_specs.avif` in the same folder
- [L5] *G-series Lua API V8.45* (LGS): https://douile.com/logitech-toggle-keys/APIDocs.pdf (PlayMacro p.29, Sleep/abort p.9)
- [L6] *G-series Lua API V8.50* (Scribd): https://www.scribd.com/document/230786227/G-SeriesLuaAPI
- [L7] Stack Overflow answers:
  - Lua 5.4 in G HUB: https://stackoverflow.com/a/70961682
  - [L9] PROFILE_ACTIVATED arg nil: https://stackoverflow.com/a/77193880
  - [L10] G502 tilt = 11: https://stackoverflow.com/a/71629866
  - [L11] button numbering: https://stackoverflow.com/a/58852677
  - [L12] IsMouseButtonPressed logical state: https://stackoverflow.com/a/76474762
  - [L14] no keyboard events: https://stackoverflow.com/a/75529478
  - [L15] wheel not capturable: https://stackoverflow.com/a/70789229
  - [L16] no G-Shift API: https://stackoverflow.com/q/78094530
  - [L18] Sleep precision: https://stackoverflow.com/a/64575146
  - [L20] MoveMouseRelative ±127: https://stackoverflow.com/a/65155090 and https://github.com/Egor-Skriptunoff/LGS_extension
  - [L21] DPI via PlayMacro: https://stackoverflow.com/a/69957890
  - [L22] coroutine use: https://stackoverflow.com/a/73523020
- [L8] Event queuing discussion: https://www.cyberforum.ru/lua/thread3184403/post17437846.html
- [L13] Scripts not running in onboard mode (low-reliability vendor page): https://pro-macro.com/instructions/logitech-g-hub-issues-and-solutions/
- [L17] G HUB `_G` dump screenshot (66 names; committed 2025-11-07):
  - image: https://github.com/UserNameUnavailableIsUnavailable/blog/blob/main/Gaming/CSOL-Utilities/Executor/assets/_G.avif
  - context: module.rmd in the same folder
- [L19] Revenant macro framework (uses PressHidKey): https://github.com/Thertzlor/Revenant
- [L23] FACEIT on no-recoil scripts: https://support.faceit.com/hc/en-us/articles/360015788779
- [L24] mhub-go: https://github.com/Miuzarte/mhub-go

**Local measurements ("probe")**

- `ratbagctl` 0.18 `info` / `dpi get-all` / `rate get-all` / `led capabilities` on the connected mouse.
- A read-only HID++ 2.0 probe script at `/tmp/claude-1000/-home-fantazy/aa26a306-21fe-4ba8-b2d9-41a32dff4e10/scratchpad/scripts/hidpp_probe.py`. It runs against `/dev/hidraw1` and issues only get-functions: FeatureSet, DeviceName, FwInfo, getSensorDpiList and getSensorDpi, getReportRateList, OnboardProfiles getDescription/getMode/getCurrentProfile, ColorLEDEffects getInfo/getZoneInfo/getZoneEffectInfo, and MouseButtonSpy getNbButtons.
