# Logitech G502 HERO (USB 046d:c08b): HID++ 2.0 wire protocol reference

Compiled on 2026-10-25 from open-source reverse-engineering work. This is a documentation
artifact only. Nothing here was measured on hardware by the author of this file. Every
claim cites its source. Wire captures quoted as "observed on C08B" come from other people's
public logs of the same USB ID (mostly Solaar issue #2313).

## Legend

| Tag | Meaning |
|---|---|
| **[PROBE]** | Measured on *this project's* mouse with a read-only probe (2026-10-25): HID++ 4.2, fw U1 69.00.B0009, BL2 40.00. See §0.4. |
| **[C08B]** | Seen in a published wire trace or dump from a real 046d:c08b. |
| **[FAM]** | Seen on hardware from the same family (G502 LIGHTSPEED 407f/c08d, G502 X c099/c098/409f, G502 X PLUS 4099), but not on c08b. |
| **[SRC]** | Read from source code that drives the feature. No capture confirms the byte layout on c08b. |
| **[?]** | Uncertain, conflicting between sources, or inferred. Verify before you depend on it. |

## Pinned sources

All links point at fixed commits so line numbers stay valid.

| Short name | Repository / commit | Main files |
|---|---|---|
| **libratbag** | [libratbag/libratbag @ 8235b5bb](https://github.com/libratbag/libratbag/tree/8235b5bb6032dea15901ab58a8218956f4494d08) (2026-09-17) | `src/hidpp20.c`, `src/hidpp20.h`, `src/hidpp-generic.{c,h}`, `src/driver-hidpp20.c`, `data/devices/logitech-g502-hero.device`, `tools/hidpp20-reset.c` |
| **Solaar** | [pwr-Solaar/Solaar @ e7304c4c](https://github.com/pwr-Solaar/Solaar/tree/e7304c4c451cc9bb4f206a914844525e67856a28) (2026-08-18) | `lib/logitech_receiver/{hidpp20.py,hidpp20_constants.py,hidpp10_constants.py,settings_templates.py,special_keys.py,base.py,notifications.py,diversion.py,common.py,rgb_power.py}`, `docs/capabilities.md`, `docs/devices/G502 SE Hero Gaming Mouse C08B.txt` |
| **cvuchener/hidpp** | [cvuchener/hidpp @ 474ac10d](https://github.com/cvuchener/hidpp/tree/474ac10db5673da8f2f1c8911414d394c0eb6d12) | `src/libhidpp/hidpp20/{IOnboardProfiles,IMouseButtonSpy,MacroFormat,ProfileFormat,ProfileDirectoryFormat,MemoryMapping}.*`, `src/libhidpp/misc/CRC.cpp`, `profile_format.md` |
| **OpenRGB** | [CalcProgrammer1/OpenRGB @ c43424b4](https://gitlab.com/CalcProgrammer1/OpenRGB/-/tree/c43424b4ba94748b913a6551c274251a5211510c/Controllers/LogitechController) (2026-10-23) | `LogitechProtocolCommon.h`, `LogitechHIDPP20Controller/LogitechHIDPP20Controller.cpp`, `LogitechGLightsyncController/LogitechGLightsyncController.cpp`, `LogitechControllerDetect.cpp` |
| **OpenLogi** | [AprilNEA/OpenLogi @ 7aaa4f14](https://github.com/AprilNEA/OpenLogi/tree/7aaa4f1408a998006f17c53945ef71fa8d3dd5c4) | `crates/openlogi-hidpp/src/feature/{color_led_effects*,device_information,adjustable_dpi,report_rate,extended_report_rate,led_control}.rs` |
| **OpenLogi PR #1002** | [Trukitro/OpenLogi @ 8fb63e4b](https://github.com/Trukitro/OpenLogi/tree/8fb63e4b7e9fec8af6f51caa3d892b31dff06ca6) | `crates/openlogi-hidpp/src/feature/onboard_profiles{.rs,/tests.rs}`: real G502 LIGHTSPEED and G502 X LIGHTSPEED sector dumps |
| **OpenLogi fork (spy)** | [CharlieMc0/OpenLogi @ 4e835ed2](https://github.com/CharlieMc0/OpenLogi/tree/4e835ed2258cdad104e094205462b44299eaa78b) | `crates/openlogi-hidpp/src/feature/mouse_button_spy{.rs,/event.rs}`, `crates/openlogi-device/src/session/gesture/spy.rs` |
| **omalogi** | [elberacasa/omalogi @ 382dea7c](https://github.com/elberacasa/omalogi/tree/382dea7c1c81531fe286f03b32bd1c33acb904ae) | `src/onboard/{format,feature}.rs`, `docs/hardware-tests.md`. This is the only project with a byte-for-byte verified write and restore on c08b. |
| **Linux kernel** | [torvalds/linux @ 6fba3312](https://github.com/torvalds/linux/blob/6fba331225f5040e93d0947d1027e9712238291f/drivers/hid/hid-logitech-hidpp.c) | `drivers/hid/hid-logitech-hidpp.c` |
| **Logitech cpg-docs** | [Logitech/cpg-docs @ f9107a4e](https://github.com/Logitech/cpg-docs/tree/f9107a4e3190d798f9be8c5d596f255f5e5741d2/hidpp20) | The official public docs. They only cover framing and IRoot. |

Key issues and PRs that are cited:
- libratbag [#1831](https://github.com/libratbag/libratbag/issues/1831): someone reverse-engineered 0x8110 on c08b.
- libratbag [#1898](https://github.com/libratbag/libratbag/issues/1898): the "disabled" button bug, with c08b byte dumps.
- libratbag [#1799](https://github.com/libratbag/libratbag/pull/1799): the INDEX_OFFSET quirk.
- libratbag [#598](https://github.com/libratbag/libratbag/issues/598): G-Shift support.
- libratbag [#1473](https://github.com/libratbag/libratbag/issues/1473): c08b default button map.
- libratbag [#1910](https://github.com/libratbag/libratbag/pull/1910): button layers.
- Solaar [#2313](https://github.com/pwr-Solaar/Solaar/issues/2313): full `-ddd` wire traces from a c08b.
- Solaar [#3250](https://github.com/pwr-Solaar/Solaar/issues/3250) and [#2914](https://github.com/pwr-Solaar/Solaar/issues/2914): c08b feature tables.
- OpenLogi [#392](https://github.com/AprilNEA/OpenLogi/issues/392): USB descriptors.
- omalogi [#17](https://github.com/elberacasa/omalogi/issues/17): c08b self-test.

---

## 0. Device facts for 046d:c08b

### 0.1 USB / HID
**[C08B]** From `lsusb -v` in [OpenLogi #392](https://github.com/AprilNEA/OpenLogi/issues/392):

- `bcdDevice 27.03`, `iProduct "G502 HERO Gaming Mouse"`, `iConfiguration "U127.03_B0010"`.
- **Interface 0** is a HID boot mouse. EP 0x81 IN carries 8-byte packets. The normal pointer and wheel reports go here.
- **Interface 1** is a vendor-specific HID interface. EP 0x82 IN carries 20-byte packets. Its report descriptor is 151 bytes. HID++ lives on this interface, on usage page 0xFF00: report 0x10 is usage 1 (short) and report 0x11 is usage 2 (long). The same interface also holds a keyboard/consumer collection, which onboard keyboard bindings and macros use. On Linux this shows up as a separate "kbd" evdev node ([#1831](https://github.com/libratbag/libratbag/issues/1831)).
- OpenRGB opens c08b on interface 1, usage page 0xFF00, usage 2 ([`LogitechControllerDetect.cpp` L1754](https://gitlab.com/CalcProgrammer1/OpenRGB/-/blob/c43424b4ba94748b913a6551c274251a5211510c/Controllers/LogitechController/LogitechControllerDetect.cpp#L1754)).
- **Kernel driver:** `hid-generic`. Solaar's c08b log shows `driver='hid-generic', interface=1, hidpp_short=True, hidpp_long=True`. `hid-logitech-hidpp.c` has no c08b entry. This means no kernel HID++ traffic competes with you, and the kernel's sw-id 0x01 is never in use on this device.

### 0.2 Feature table
**[C08B]** Two firmware versions are known: `U1 27.03.B0010` / `BOT 81.00.B0002`, and `U1 69.00.B0009` / `BL2 40.00.B0009`. Protocol is **HID++ 4.2**.

Sources: [Solaar docs/devices/G502 SE Hero Gaming Mouse C08B.txt](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/docs/devices/G502%20SE%20Hero%20Gaming%20Mouse%20C08B.txt), [Solaar #3250](https://github.com/pwr-Solaar/Solaar/issues/3250), [#2914](https://github.com/pwr-Solaar/Solaar/issues/2914).

| idx | Feature | Ver | Notes |
|---|---|---|---|
| 0 | 0x0000 Root | 0 | |
| 1 | 0x0001 FeatureSet | 0/1 | |
| 2 | 0x8070 ColorLedEffects | 3 | 2 zones |
| 3 | 0x0003 DeviceFwVersion | 2 | 2 entities |
| 4 | 0x0005 DeviceName | 0 | `"G502 HERO Gaming Mouse"`, type 3 (mouse) |
| 5 | 0x1300 LedControl (non-RGB LED sw control) | 0 | |
| 6 | 0x18A1 | 0 | internal, hidden |
| 7 | 0x1E00 EnableHiddenFeatures | 0 | hidden |
| 8 | 0x1E22 | 0 | internal, hidden |
| 9 | 0x1EB0 | 0 | internal, hidden |
| 10 | 0x2201 AdjustableDPI | 1 | |
| 11 | 0x8060 AdjustableReportRate | 0 | |
| 12 | 0x8100 OnboardProfiles | 0 | |
| 13 | 0x8110 MouseButtonSpy ("Mouse Button Filter" in Logitech's list) | 0 | |
| 14 | 0x00C2 DFU control (signed) | 0 | **never touch** |
| 15 | 0x1801 | 0 | internal, hidden |
| 16 | 0x1802 DeviceReset | 0 | internal, hidden |
| 17 | 0x1806 ConfigDeviceProps | 0 | internal, hidden |
| 18 | 0x18B1 | 0 | internal, hidden |
| (19) | one more internal feature on fw 69.00 | | |

What this table means for you:
- **0x1B04 (Reprogrammable Controls V4) is absent**, and so are 0x1B00 to 0x1B03, 0x2202 and 0x8061. Button handling on this mouse is only possible through 0x8100 (onboard bindings) and 0x8110 (spy/remap). See §7.
- The indices are the same on both firmware versions, but **always resolve them at runtime** with Root.getFeature.

### 0.3 Known values on c08b

| Item | Value | Source |
|---|---|---|
| DPI range | 100 to 25600, step 50. Raw list `0064 E032 6400 0000`. | **[C08B]** Solaar #2313 trace, see §6 |
| Report rates | bitmap `0x8B`, meaning 1, 2, 4, 8 ms (1000/500/250/125 Hz) | **[C08B]** Solaar #2313 trace |
| Onboard layout | memory model 1, profile format 2, macro format 1, 5 profiles, 5 ROM profiles, 11 buttons | **[PROBE]** getDescription `01 02 01 05 05 0B 10 00 FF 0A 01`. Also reported by omalogi [docs/hardware-tests.md L52-55](https://github.com/elberacasa/omalogi/blob/382dea7c1c81531fe286f03b32bd1c33acb904ae/docs/hardware-tests.md#L52-L55). |
| ROM profiles | 5 (`0x0101` to `0x0105`). Reading `0x0106` and above returns error 0x02. | **[PROBE]**, plus the **[C08B]** ROM directory trace in §3.5 |
| Sector size | **255 (`0x00FF`)**, so the CRC sits at bytes 253-254 | **[PROBE]**. Matches G502 X, G502 X LS and G502 LIGHTSPEED **[FAM]**. omalogi's "256 bytes" remark is wrong for this unit. |
| Sector count | **16** (`0x10`) | **[PROBE]** |
| Mode at power-on | onboard (getMode = `01`) | **[PROBE]** |
| LED zones | zone 0 = location 0x0001 "Primary", zone 1 = 0x0002 "Logo". 4 effects each: idx0 Disabled, idx1 Fixed, idx2 Breathing (0x0A), idx3 Cycle (0x03). | **[C08B]** §4 |
| libratbag quirk | `Quirk=INDEX_OFFSET` | [data/devices/logitech-g502-hero.device](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/data/devices/logitech-g502-hero.device) |

### 0.4 Probe of this project's mouse, and how it compares with the sources
**[PROBE]** Read-only probe on 2026-10-25. HID++ 4.2, firmware `U1 69.00.B0009`, bootloader `BL2 40.00`.

| Item | Probe result | Agrees with sources? |
|---|---|---|
| Feature indexes | 1 0x0001, 2 0x8070 v3, 3 0x0003, 4 0x0005, 5 0x1300, 10 0x2201 v1, 11 0x8060, 12 0x8100, 13 0x8110, 14 0x00C2. No 0x1B04. | Yes, matches §0.2 |
| 0x8100 getDescription | `01 02 01 05 05 0B 10 00 FF 0A 01` | Yes. It fills the gaps: 16 sectors of 255 bytes, layout 0x0A (G-Shift and DPI-shift both present), various_info 0x01 (corded). |
| 0x8100 getMode | `01` (onboard) | — |
| 0x8100 getCurrentProfile | `00 02`. The live rate (1 ms) and DPI (1600) match sector `0x0002`. | Yes, the reply is `[memType, page]`, i.e. the **sector number (1-based)**. See the libratbag note below. |
| Directory `0x0000` | `00 01 01 00 \| 00 02 01 00 \| 00 03 01 00 \| 00 04 01 00 \| 00 05 01 00 \| FF FF 00 00` | **Partly.** See the mismatch note below. |
| ROM directory `0x0100` | `01 01 01 FF …`, then `FF FF`, then an ASCII firmware string | Yes, same shape as the 27.03 unit's trace (§3.5) |
| ROM sectors `0x0106`+ | error 0x02 INVALID_ARGUMENT | Consistent with 5 ROM profiles |
| Profile `0x0001` | starts `01 01 00 B0 04 60 09 80 0C 00 19 00 00` | **Yes.** Rate 1 ms, default DPI idx 1, shift idx 0, then DPI LE16: 1200, 2400, 3200, 6400, 0 (unused). This confirms the §3.6 offsets and little-endian DPI. |
| 0x2201 DPI list | 100 to 25600, step 50 | Yes (§6) |
| 0x8060 rate list | `0x8B` (1/2/4/8 ms) | Yes (§5) |
| 0x8070 getInfo | `02 00 03 …`: 2 zones, locations 0x0001 and 0x0002, each with effect idx 0→0x0000, 1→0x0001, 2→0x000A, 3→0x0003 | Yes, identical to the 27.03 trace (§4.1) |
| 0x8110 getMouseButtonCount / getMouseButtonMapping | 11 / `01 … 0B` | Yes (§7.2) |

Two places where this mouse differs from what some sources say:

1. **Directory reserved byte and terminator.**
   - This mouse stores the 4th byte of each entry as `0x00` and terminates with `FF FF 00 00`. That is libratbag's and Solaar's writer format (§3.5).
   - The ROM directory, the G502 X LS user directory and the 27.03 unit's ROM directory use `0xFF` there, with `FF FF` and then FF fill.
   - So the user directory was most likely last written by libratbag or Solaar, not G HUB. The firmware accepts both forms.
   - When you rewrite it, keep whatever is there.
2. **libratbag active profile shows one slot off.** getCurrentProfile returns the 1-based page (`00 02` means sector 2). libratbag only subtracts 1 when `HIDPP20_QUIRK_INDEX_OFFSET` is set.
   - That quirk was added to `logitech-g502-hero.device` in [PR #1799](https://github.com/libratbag/libratbag/pull/1799), merged 2026-01-11.
   - The off-by-one on this system means the installed libratbag predates that commit, or its data file lacks the quirk. **[?]** This is inferred; the installed version was not checked.
   - Your daemon should treat byte 1 as the sector/page number directly.

---

## 1. HID++ 2.0 framing

### 1.1 Report layout
Sources: Logitech [cpg-docs hidpp20/README.rst](https://github.com/Logitech/cpg-docs/blob/f9107a4e3190d798f9be8c5d596f255f5e5741d2/hidpp20/README.rst), libratbag [`hidpp20.h` L36-47](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.h#L36-L47), [`hidpp-generic.h` L37-44](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp-generic.h#L37-L44).

```
byte:   0          1             2              3                       4 ...
      +----------+-------------+--------------+-----------------------+-----------------------+
      | ReportID | DeviceIndex | FeatureIndex | Function<<4 | SwId    | Parameters            |
      +----------+-------------+--------------+-----------------------+-----------------------+
short: 0x10, total 7 bytes  -> 3 parameter bytes
long:  0x11, total 20 bytes -> 16 parameter bytes
(very long 0x12 = 64 bytes exists on some devices, not c08b)
```

- **DeviceIndex = 0xFF** for a corded device like c08b. cpg-docs says "0xff is reserved for corded devices and receivers". libratbag uses 0xFF by default ([`driver-hidpp20.c` L1682-1705](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/driver-hidpp20.c#L1682-L1705)). Solaar accepts a reply whose device number is `devnumber` or `devnumber ^ 0xFF`, because Bluetooth devices reply with 0x00 ([`base.py` L729](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/base.py#L729)).
- **Byte 3** holds the function number in the high nibble and the software ID in the low nibble. Function N is written as `N<<4 | swid`: getDescription is `0x0?`, setMode `0x1?`, and so on.
- **Software ID:** 0 is reserved for device-originated events, so requests use 1 to 15. The device echoes the swid in the reply. Known users:
  - kernel 0x01 ([`hid-logitech-hidpp.c` L42](https://github.com/torvalds/linux/blob/6fba331225f5040e93d0947d1027e9712238291f/drivers/hid/hid-logitech-hidpp.c#L42))
  - OpenRGB 0x07, LGSTrayEx 0x0A, Solaar 0x0B, Logitech G HUB 0x0D, firmware self-enumeration 0x0F ([`base.py` L897-915](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/base.py#L897-L915))
  - libratbag 0x08 ([`hidpp20.c` L129-137](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L129-L137))

  Pick an unused value such as 0x3, 0x5, 0x6, 0x9, 0xC or 0xE.
- A request may be sent short when it has 3 or fewer parameter bytes. Long is always accepted. Solaar sends everything long to this device, and c08b answers in long reports (#2313 traces). libratbag upgrades short requests to long when the descriptor lacks short support ([`hidpp20.c` L139-147](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L139-L147)).
- **hidraw I/O:** `write()` the whole report, with the report ID as byte 0, as 7 or 20 bytes. `read()` returns the report ID in byte 0. libratbag polls with a 1000 ms timeout and retries once after 10 ms on timeout ([`hidpp-generic.c` L234-279](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp-generic.c#L234-L279), [`hidpp20.c` L160-198](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L160-L198)). The kernel waits up to 5 s.

### 1.2 Matching a response
A reply matches its request when the report is 0x10 or 0x11 **and** byte2 equals the request's byte2 **and** byte3 equals the request's byte3 (function plus swid). Sources: libratbag [`hidpp20.c` L173-176](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L173-L176), kernel `hidpp_match_answer` [L471-476](https://github.com/torvalds/linux/blob/6fba331225f5040e93d0947d1027e9712238291f/drivers/hid/hid-logitech-hidpp.c#L471-L476).

While you wait, keep consuming other reports. They may be events from swid 0, or replies to other software that share the hidraw node.

### 1.3 HID++ 2.0 error response (feature index 0xFF)
```
11 FF FF <req.featIdx> <req.fn|swid> <errCode> 00 ...      (long report)
```
The error frame shifts the request's header one byte to the right. Sources: libratbag [`hidpp20.c` L178-197](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L178-L197), kernel `hidpp_match_error` [L478-485](https://github.com/torvalds/linux/blob/6fba331225f5040e93d0947d1027e9712238291f/drivers/hid/hid-logitech-hidpp.c#L478-L485). The kernel only looks for this frame in long or very-long reports ([L334-340](https://github.com/torvalds/linux/blob/6fba331225f5040e93d0947d1027e9712238291f/drivers/hid/hid-logitech-hidpp.c#L334-L340)). cvuchener also extracts optional error data from byte 6 onward ([`Report.cpp` L255-283](https://github.com/cvuchener/hidpp/blob/474ac10db5673da8f2f1c8911414d394c0eb6d12/src/libhidpp/hidpp/Report.cpp#L255-L283)).

Error codes come from libratbag [`hidpp-generic.h` L70-79](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp-generic.h#L70-L79), Solaar [`hidpp20_constants.py` L281-290](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/hidpp20_constants.py#L281-L290), the kernel [L236-246](https://github.com/torvalds/linux/blob/6fba331225f5040e93d0947d1027e9712238291f/drivers/hid/hid-logitech-hidpp.c#L236-L246) and cvuchener [`Error.h`](https://github.com/cvuchener/hidpp/blob/474ac10db5673da8f2f1c8911414d394c0eb6d12/src/libhidpp/hidpp20/Error.h):

| Code | Name | Typical cause on 0x8100 and others |
|---|---|---|
| 0x00 | NO_ERROR | |
| 0x01 | UNKNOWN | |
| 0x02 | INVALID_ARGUMENT | memoryRead past `sector_size-16`; setCurrentProfile or setCurrentDpiIndex in host mode; an unsupported report rate |
| 0x03 | OUT_OF_RANGE | |
| 0x04 | HARDWARE_ERROR | **memoryWriteEnd when the sector CRC is wrong. The data is still stored.** See §3.4. |
| 0x05 | LOGITECH_INTERNAL (the kernel calls it NOT_ALLOWED) | |
| 0x06 | INVALID_FEATURE_INDEX | |
| 0x07 | INVALID_FUNCTION_ID | |
| 0x08 | BUSY | retry (Solaar's `rgb_power.feature_request_acked` retries) |
| 0x09 | UNSUPPORTED | |
| 0x0A | UNKNOWN_DEVICE | only in cvuchener |

### 1.4 HID++ 1.0 error (sub-id 0x8F)
```
10 FF 8F <req.subId(byte2)> <req.address(byte3)> <errCode> 00     (short report)
```
Sources: libratbag `__ERROR_MSG 0x8F` [`hidpp-generic.h` L54-68](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp-generic.h#L54-L68), Solaar [`base.py` L730-746](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/base.py#L730-L746) and [`hidpp10_constants.py` L129-141](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/hidpp10_constants.py#L129-L141), cvuchener `checkErrorMessage10`.

You only see this frame for HID++ 1.0 register requests (sub-ids 0x80 to 0x83), or when you ping a 1.0 device. libratbag's ping treats `INVALID_SUBID` (0x01) as "this is a HID++ 1.0 device" ([`hidpp20.c` L299-305](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L299-L305)).

| Code | Name |
|---|---|
| 0x01 | INVALID_SUBID |
| 0x02 | INVALID_ADDRESS |
| 0x03 | INVALID_VALUE |
| 0x04 | CONNECT_FAIL |
| 0x05 | TOO_MANY_DEVICES |
| 0x06 | ALREADY_EXISTS |
| 0x07 | BUSY |
| 0x08 | UNKNOWN_DEVICE |
| 0x09 | RESOURCE_ERROR |
| 0x0A | REQUEST_UNAVAILABLE |
| 0x0B | INVALID_PARAM_VALUE |
| 0x0C | WRONG_PIN_CODE |

### 1.5 Events / notifications
An event looks like `1x FF <featIdx> <eventId<<4 | 0> <params>`, with **swid = 0**. Solaar classifies a frame as a 2.0 notification when `address & 0x0F == 0`. It ignores sub-id 0 with function 0 as a "no-op" notification. It skips frames whose sub-id has bit 7 set, because those are 1.0 register replies or errors ([`base.py` L601-633](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/base.py#L601-L633)).

Root event 0, `NoOperation`, keeps the device awake and can be ignored (cpg-docs [0x0000-IRoot.rst](https://github.com/Logitech/cpg-docs/blob/f9107a4e3190d798f9be8c5d596f255f5e5741d2/hidpp20/features/0x0000-IRoot.rst)).

Events that matter on c08b:

| Feature | Event | Payload | Source |
|---|---|---|---|
| 0x8100 | 0 currentProfileChanged | `[memType, page]`. Solaar reads this as a BE16 sector. | cvuchener `IOnboardProfiles.cpp`, Solaar [`notifications.py` L397-415](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/notifications.py#L397-L415) |
| 0x8100 | 1 currentDpiIndexChanged | `[dpiIndex]` | same |
| 0x8110 | 0 mouseButtonEvent | `[maskHi, maskLo]`: a BE16 bitmap of the buttons currently pressed | §7 |
| 0x8070 | 0 syncEffect (v1+, only when sync events are enabled) | `[zone, counterHi, counterLo]` | OpenLogi [`color_led_effects/event.rs`](https://github.com/AprilNEA/OpenLogi/blob/7aaa4f1408a998006f17c53945ef71fa8d3dd5c4/crates/openlogi-hidpp/src/feature/color_led_effects/event.rs) |

---

## 2. Root (0x0000), FeatureSet (0x0001), DeviceFwVersion (0x0003), DeviceName (0x0005)

### 2.1 Root, always at index 0
Sources: cpg-docs IRoot, libratbag [`hidpp20.c` L229-313](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L229-L313).

| fn | Name | Request params | Reply params |
|---|---|---|---|
| 0 (0x0?) | getFeature | `featIdHi featIdLo` | `featIndex featType featVersion`. Index 0 means "not present". featType bit7 = obsolete, bit6 = hidden, bit5 = internal (the last one per Solaar [`FeatureFlag` L243-248](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/hidpp20_constants.py#L243-L248)). |
| 1 (0x1?) | getProtocolVersion / ping | `00 00 pingByte` | `major minor pingByte`. `0x8F` means HID++ 1.0. |

**[C08B]** Observed in Solaar #2313:
```
w 11 FF 00 0F 00 01 00..    getFeature(0x0001)
r 11 FF 00 0F 01 00 01..    -> FeatureSet at idx 1, type 0, version 1
w 11 FF 00 1F 00 00 67..    ping, pingByte 0x67
r 11 FF 00 1F 04 02 67..    -> HID++ 4.2, ping echoed
```

### 2.2 FeatureSet (0x0001)
Source: libratbag [`hidpp20.c` L319-419](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L319-L419), Solaar [`FeaturesArray` L151-330](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/hidpp20.py#L151-L330).

| fn | Name | Request | Reply |
|---|---|---|---|
| 0 | getCount | none | `count`. The count **excludes Root**, so the total is count + 1. |
| 1 | getFeatureID | `index` | `featIdHi featIdLo featType featVersion` |

**[C08B]** `getCount` returns `0x12` (18), so 19 features (#2313).

### 2.3 DeviceFwVersion / Device Information (0x0003)
Sources: Solaar `get_firmware`/`get_ids` [`hidpp20.py` L1771-1834](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/hidpp20.py#L1771-L1834), OpenLogi [`device_information.rs` L54-100, L266-292](https://github.com/AprilNEA/OpenLogi/blob/7aaa4f1408a998006f17c53945ef71fa8d3dd5c4/crates/openlogi-hidpp/src/feature/device_information.rs#L266-L292). libratbag does not implement this feature.

**fn0 getDeviceInfo** returns:

| Byte | Field | Version |
|---|---|---|
| 0 | entityCount | |
| 1-4 | unitId | v1+ |
| 5-6 | transport, BE. bit0 BT, bit1 BTLE, bit2 eQuad, bit3 USB. | v1+ |
| 7-12 | modelId: one 16-bit PID per transport | v1+ |
| 13 | extendedModelId | v2+ |
| 14 | capabilities. bit0 = serial number supported. | v4+ |

**fn1 getFwInfo(entityIdx)** returns:

| Byte | Field |
|---|---|
| 0 | type, low nibble: 0 main app, 1 bootloader, 2 hardware, 3+ other |
| 1-3 | prefix, ASCII, e.g. `"U1 "` or `"BOT"` |
| 4 | number, BCD |
| 5 | revision, BCD |
| 6-7 | build, BCD BE. Some firmware sends binary here. |
| 8 | flags. bit0 = active entity. |
| 9-10 | transport PID (BE). Only valid for the active main app. |
| 11-15 | extra |

**fn2 getSerialNumber** (v4+) returns 12 ASCII bytes.

**[C08B]** `getDeviceInfo` returns `02 | <unitId 4B> | 00 08 | C0 8B 00 00 00 00 | 00 | 00`. That is 2 entities, transport USB, model C08B. The firmware strings are `U1 27.03.B0010` (main) and `BOT 81.00.B0002` (bootloader). The newer unit reports `U1 69.00.B0009` and `BL2 40.00.B0009`.

### 2.4 DeviceName (0x0005)
Sources: Solaar `get_name`/`get_kind` [`hidpp20.py` L1836-1870](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/hidpp20.py#L1836-L1870), OpenLogi [`device_type_and_name.rs`](https://github.com/AprilNEA/OpenLogi/blob/7aaa4f1408a998006f17c53945ef71fa8d3dd5c4/crates/openlogi-hidpp/src/feature/device_type_and_name.rs), OpenRGB [`LogitechProtocolCommon.h` L43-46](https://gitlab.com/CalcProgrammer1/OpenRGB/-/blob/c43424b4ba94748b913a6551c274251a5211510c/Controllers/LogitechController/LogitechProtocolCommon.h#L43-L46).

| fn | Name | Request | Reply |
|---|---|---|---|
| 0 | getDeviceNameCount | none | `len` |
| 1 | getDeviceName | `charIndex` | name bytes starting at `charIndex`: up to 16 in a long reply, 3 in a short one. Loop until you have `len` bytes. |
| 2 | getDeviceType | none | `type`: 0 keyboard, 1 remote, 2 numpad, **3 mouse**, 4 touchpad, 5 trackball, 6 presenter, 7 receiver |

---

## 3. Onboard Profiles (0x8100)

### 3.1 Functions
Function numbers come from libratbag [`hidpp20.c` L1783-1814](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L1783-L1814) and cvuchener [`IOnboardProfiles.h`](https://github.com/cvuchener/hidpp/blob/474ac10db5673da8f2f1c8911414d394c0eb6d12/src/libhidpp/hidpp20/IOnboardProfiles.h) / [`.cpp`](https://github.com/cvuchener/hidpp/blob/474ac10db5673da8f2f1c8911414d394c0eb6d12/src/libhidpp/hidpp20/IOnboardProfiles.cpp). They agree with each other.

| fn (byte3) | Name | Request params | Reply params | Report |
|---|---|---|---|---|
| 0 (0x0?) | getDescription / getInfo | none | 16 bytes, see §3.2 | short request, long reply |
| 1 (0x1?) | setMode | `mode`: 0 no change, **1 onboard**, **2 host** | none | short |
| 2 (0x2?) | getMode | none | `mode` | short |
| 3 (0x3?) | setCurrentProfile | `memType page`. `00 01` is user profile 1. `01 01` is ROM profile 1 (Solaar sends a BE16 sector). | none | short |
| 4 (0x4?) | getCurrentProfile | none | `memType page`. **The page is 1-based.** This is the reason for libratbag's INDEX_OFFSET quirk. | short |
| 5 (0x5?) | memoryRead | `sectorHi sectorLo offsetHi offsetLo` | 16 data bytes | long |
| 6 (0x6?) | memoryAddrWrite | `sectorHi sectorLo offsetHi offsetLo lenHi lenLo` | none | long |
| 7 (0x7?) | memoryWrite | 16 data bytes | none | long |
| 8 (0x8?) | memoryWriteEnd | none | none, or an error (0x04 on bad CRC) | short |
| 9, 10 | unknown | | | **[?]** No source documents them. |
| 11 (0xB?) | getCurrentDpiIndex | none | `index` (0-4) | short |
| 12 (0xC?) | setCurrentDpiIndex | `index` (0-4). libratbag rejects values above 4. | none | short |

**Sector addressing.** A 16-bit sector is `memType<<8 | page`. memType 0 is writeable flash and memType 1 is ROM ([`IOnboardProfiles.h` "MemoryType"](https://github.com/cvuchener/hidpp/blob/474ac10db5673da8f2f1c8911414d394c0eb6d12/src/libhidpp/hidpp20/IOnboardProfiles.h)). libratbag uses `HIDPP20_USER_PROFILES_G402 0x0000` and `HIDPP20_ROM_PROFILES_G402 0x0100`. memoryAddrWrite can only target memType 0.

**Mode semantics** (cvuchener, `IOnboardProfiles.h`):
- **Onboard (1):** "The mouse uses the profiles from its on-board memory. Current profile and DPI index can be read and written and event are sent when they are changed."
- **Host (2):** "Only generic button events are sent according to the mapping from IMouseButtonSpy. Current profile or DPI index cannot be set (invalid argument error) and events will not be sent."

**[C08B]** Solaar wrote `setMode(2)` as `11 FF 0C 1F 02` and got an empty ack. Solaar's "Onboard Profiles = Disabled" choice sends `0x10 02`. Selecting a profile sends `0x10 01` and then `0x30 <sector BE16>` ([`settings_templates.py` L547-590](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/settings_templates.py#L547-L590)).

**[?]** No source says whether host mode survives a power cycle or USB replug. A Solaar c08b dump shows "Device Mode: Host" after Solaar had set it, but that does not settle the question. Re-assert the mode on every (re)connect.

### 3.2 getDescription reply
libratbag `struct hidpp20_onboard_profiles_info` ([`hidpp20.h` L894-907](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.h#L894-L907)):

```c
struct hidpp20_onboard_profiles_info {
	uint8_t memory_model_id;     // [0]  only 1 known
	uint8_t profile_format_id;   // [1]  1..5 supported by libratbag
	uint8_t macro_format_id;     // [2]  only 1 known
	uint8_t profile_count;       // [3]
	uint8_t profile_count_oob;   // [4]  number of ROM ("out of box") profiles
	uint8_t button_count;        // [5]
	uint8_t sector_count;        // [6]
	uint16_t sector_size;        // [7..8] BIG endian
	uint8_t mechanical_layout;   // [9]
	uint8_t various_info;        // [10]
	uint8_t reserved[5];         // [11..15]
} __attribute__((packed));
```

**Profile format IDs** (libratbag [L1802-1808](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L1802-L1808), cvuchener and omalogi comments):

| ID | Used by |
|---|---|
| 1 | G402, G502 Proteus Core |
| 2 | G303, G502 Proteus Spectrum, **G502 HERO c08b [C08B]** |
| 3 | G900, G502 X LIGHTSPEED (via receiver) |
| 4 | G915, G502 X wired c099 |
| 5 | G502 X PLUS |

libratbag refuses memory model ≠ 1 and macro format ≠ 1 ([L2213-2243](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L2213-L2243)).

**mechanical_layout** (libratbag [L2294-2295](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L2294-L2295), cvuchener):
- G-Shift is supported when `(ml & 0x03) == 2`.
- DPI-shift is supported when `((ml & 0x0C) >> 2) == 2`.
- Solaar sets `gbuttons = buttons if (ml & 3) == 2 else 0` ([`hidpp20.py` L1669-1670](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/hidpp20.py#L1669-L1670)).

**various_info & 0x07:** 1 corded, 2 wireless, 4 corded+wireless. cvuchener treats power modes as present only when this is not "corded only".

**[FAM]** Real reply from a G502 X wired (c099), via omalogi `tests/fixtures/g502x-c099.json`:
```
01 04 01 05 02 0B 10 00 FF 0A 01 00 00 00 00 00
model 1, format 4, macro 1, 5 profiles, 2 ROM profiles, 11 buttons,
16 sectors, sector_size 0x00FF = 255, layout 0x0A (G-Shift and DPI-shift), corded
```
**[PROBE]** The c08b reply is `01 02 01 05 05 0B 10 00 FF 0A 01`:

| Field | Value |
|---|---|
| memory model | 1 |
| profile format | 2 |
| macro format | 1 |
| profiles | 5 |
| ROM profiles | 5 |
| buttons | 11 |
| sectors | 16 |
| sector_size | 255 |
| mechanical_layout | 0x0A (G-Shift and DPI-shift) |
| various_info | 0x01 (corded) |

Still read these at runtime rather than hard-coding them.

### 3.3 Reading memory
- Read in 16-byte chunks: `memoryRead(sector, offset)`.
- **The firmware returns ERR_INVALID_ARGUMENT if `offset > sector_size - 16`.** The last chunk must be re-aligned to `sector_size - 16` and overlap the previous one. See libratbag [`hidpp20.c` L1874-1918](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L1874-L1918), Solaar `read_sector` [L1699-1715](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/hidpp20.py#L1699-L1715), omalogi `read_sector` [L104-125](https://github.com/elberacasa/omalogi/blob/382dea7c1c81531fe286f03b32bd1c33acb904ae/src/onboard/feature.rs#L104-L125).
- For a 255-byte sector the offsets are `0, 16, …, 224, 239`.
- ROM sectors (`0x01pp`) can be read the same way. libratbag's `tools/hidpp20-dump-page.c` dumps `(rom<<8)|page`.
- An unwritten user sector reads back **without error**: all 0x00 on the c08b in Solaar #2313, all 0xFF on a G502 X LS in omalogi.

### 3.4 Writing memory, chunking and CRC
Sequence, from libratbag `hidpp20_onboard_profiles_write_sector` [L2003-2044](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L2003-L2044), Solaar `write_sector` [L1718-1728](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/hidpp20.py#L1718-L1728), cvuchener `MemoryMapping::writePage` and omalogi `write_sector` [L136-166](https://github.com/elberacasa/omalogi/blob/382dea7c1c81531fe286f03b32bd1c33acb904ae/src/onboard/feature.rs#L136-L166):

```
1. build the full sector image (sector_size bytes)
2. crc = CRC16(image[0 .. sector_size-2]);  image[sector_size-2] = crc>>8; image[sector_size-1] = crc&0xFF   (BIG endian)
3. 11 FF <idx> 6s  sectorHi sectorLo 00 00 lenHi lenLo  00…      memoryAddrWrite(sector, offset 0, len=sector_size)
4. for each 16-byte slice: 11 FF <idx> 7s  d0 … d15                memoryWrite. Pad the last slice; omalogi pads with 0xFF.
5. 10 FF <idx> 8s 00 00 00                                         memoryWriteEnd
6. read the sector back and compare. omalogi always does this.
```

- cvuchener: "If the length passed to memoryAddrWrite is not a multiple of LineSize, the extra data at the end of the last memoryWrite call is ignored."
- **memoryWriteEnd validates the CRC.** On a mismatch it returns HID++ error **0x04 HARDWARE_ERROR, but the bytes are still stored.** omalogi [docs/hardware-tests.md L290-302](https://github.com/elberacasa/omalogi/blob/382dea7c1c81531fe286f03b32bd1c33acb904ae/docs/hardware-tests.md#L290-L302): "The firmware checks the checksum when a write ends but keeps a sector that fails it."
- libratbag's factory-reset tool relies on exactly this. It writes all-zero sectors 1 to 30 and then 0, without a CRC, and treats error 4 as expected ([`tools/hidpp20-reset.c`](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/tools/hidpp20-reset.c)). The firmware then ignores the invalid sectors and falls back to ROM.
- Solaar only writes sectors that differ from what the device holds (`write_sector` compares first). It refuses `sector >= sector_count` ("not a writable sector", [L1736-1743](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/hidpp20.py#L1736-L1743)). omalogi refuses any sector `>= 0x0100`.
- libratbag minor bug: for a 255-byte sector it sends 16 slices of 16 bytes from a 255-byte buffer, a one-byte over-read. This is harmless because the device ignores bytes past `len`.

**CRC algorithm: CRC-16/CCITT-FALSE.** Polynomial 0x1021, init 0xFFFF, no reflection, no final XOR. The check value for `"123456789"` is `0x29B1`. It covers `sector[0 .. size-2)` and is stored big-endian in the last 2 bytes. Logitech's own reference implementation, as copied by libratbag [`hidpp-generic.c` L379-404](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp-generic.c#L379-L404):
```c
#define CRC_CCITT_SEED	0xFFFF
uint16_t hidpp_crc_ccitt(uint8_t *data, unsigned int length) {
	uint16_t crc = CRC_CCITT_SEED, temp, quick;
	for (unsigned i = 0; i < length; i++) {
		temp = (crc >> 8) ^ (*data++);
		crc <<= 8;
		quick = temp ^ (temp >> 4);
		crc ^= quick;  quick <<= 5;
		crc ^= quick;  quick <<= 7;
		crc ^= quick;
	}
	return crc;
}
```
The same algorithm appears in cvuchener [`misc/CRC.cpp`](https://github.com/cvuchener/hidpp/blob/474ac10db5673da8f2f1c8911414d394c0eb6d12/src/libhidpp/misc/CRC.cpp), Solaar `common.crc16` (table-driven, [`common.py` L40](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/common.py#L40)) and omalogi [`format.rs` L127-137](https://github.com/elberacasa/omalogi/blob/382dea7c1c81531fe286f03b32bd1c33acb904ae/src/onboard/format.rs#L127-L137).

**[FAM]** For this document, the CRC was recomputed over the real 255-byte sector dumps in [OpenLogi PR #1002 tests.rs](https://github.com/Trukitro/OpenLogi/blob/8fb63e4b7e9fec8af6f51caa3d892b31dff06ca6/crates/openlogi-hidpp/src/feature/onboard_profiles/tests.rs):

| Dump | Stored CRC | Computed CRC |
|---|---|---|
| G502 LIGHTSPEED profile 1 | `3E23` | `3E23` |
| G502 X LS profile 1 | `EE21` | `EE21` |
| G502 X LS directory | `7B69` | `7B69` |

omalogi notes that **factory (ROM) sectors on the G502 X carry `0000` or `FFFF` instead of a CRC** ([`format.rs` L139-147](https://github.com/elberacasa/omalogi/blob/382dea7c1c81531fe286f03b32bd1c33acb904ae/src/onboard/format.rs#L139-L147)). Do not reject ROM sectors on CRC.

### 3.5 Profile directory (sector 0x0000)
The directory is a list of 4-byte entries, then a terminator, then 0xFF fill, then the CRC at the end:

```
+0  sectorHi sectorLo enabled reserved     entry 0
+4  sectorHi sectorLo enabled reserved     entry 1
...
    FF FF                                   terminator (sector 0xFFFF)
    FF … FF                                 fill
    crcHi crcLo                             at sector_size-2
```

- **enabled**: 0 or 1. Disabled profiles are skipped by next/prev/cycle-profile.
- **reserved**: The ROM directories and the G502 X LS user directory hold **0xFF**. libratbag and Solaar write 0x00. **[PROBE]** This mouse's user directory holds 0x00 with an `FF FF 00 00` terminator (§0.4). cvuchener calls the byte "dir_unknown". Preserve it.
- libratbag reads `enabled = !!d[HIDPP20_PROFILE_DIR_ENABLED]` with index 2 ([L2816-2839](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L2816-L2839)). It writes `00 (i+1) enabled 00`, then `FF FF 00 00`, then 0xFF fill, then the CRC ([`write_dict` L2512-2553](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L2512-L2553)).
- Solaar writes `sector(2) enabled 00`, then `FF FF 00 00`, then fill and CRC ([L1686-1696](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/hidpp20.py#L1686-L1696)).
- cvuchener stops parsing at `mem_type == 0xFF` ([`ProfileDirectoryFormat.cpp`](https://github.com/cvuchener/hidpp/blob/474ac10db5673da8f2f1c8911414d394c0eb6d12/src/libhidpp/hidpp20/ProfileDirectoryFormat.cpp)).
- By convention, profile N lives in sector N (`0x0001` to `0x0005`). libratbag logs a warning when an address is not `i+1`.

**[FAM]** G502 X LS directory:
```
00 01 01 FF  00 02 01 FF  00 03 01 FF  00 04 00 FF  00 05 00 FF  FF FF FF …  7B 69
```

**[C08B]** ROM directory (sector 0x0100), assembled from the Solaar #2313 reads at offsets 0x00, 0x04, …, 0x14:
```
01 01 01 FF  01 02 01 FF  01 03 01 FF  01 04 01 FF   (0x00-0x0F)
01 05 01 FF  FF FF 55 31 32 37 2E 30 33 5F 42 30 30 31 30 00   (0x10-0x23)
                   "U127.03_B0010\0"   <- the firmware string is stored after the terminator
```
On the same c08b, user sector 0x0000 read at offset 0 returned 16 zero bytes. Solaar treats `00000000` or `FFFFFFFF` as "no user directory" and falls back to the ROM directory ([`get_profile_headers` L1639-1659](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/hidpp20.py#L1639-L1659)).

**Fallback logic** (libratbag `hidpp20_onboard_profiles_initialize` [L2780-2879](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L2780-L2879)):
- If the directory CRC is invalid, all profiles come from ROM.
- If a single profile CRC is invalid, that profile falls back to ROM profile `0x0100+i+1`. If there are fewer ROM profiles than slots, it uses `0x0101`.
- ROM profiles are parsed without a CRC check.

The firmware does the same: with no valid user directory "the mouse runs its factory profiles" (omalogi [L436-458](https://github.com/elberacasa/omalogi/blob/382dea7c1c81531fe286f03b32bd1c33acb904ae/docs/hardware-tests.md#L436-L458)).

**Initialising a never-written mouse safely** (omalogi "profiles repair"):
1. Copy the ROM profiles into `0x0001` to `0x0005` with fresh CRCs.
2. Write the directory `0x0000` **last**.
3. Verify each sector by reading it back.

### 3.6 Profile sector layout
The layout is shared by profile formats 1 to 5. Field offsets are identical across formats and only the LED area differs.

libratbag `union hidpp20_internal_profile` ([`hidpp20.c` L1816-1842](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L1816-L1842)):
```c
union hidpp20_internal_profile {
	uint8_t data[HIDPP20_PROFILE_SIZE];          /* 256 */
	struct {
		uint8_t report_rate;                     /* 0   */
		uint8_t default_dpi;                     /* 1   */
		uint8_t switched_dpi;                    /* 2   */
		uint16_t dpi[5];                         /* 3   LITTLE endian */
		struct hidpp20_color profile_color;      /* 13  */
		uint8_t power_mode;                      /* 16  */
		uint8_t angle_snapping;                  /* 17  */
		uint8_t reserved[10];                    /* 18  */
		uint16_t powersave_timeout;              /* 28  */
		uint16_t poweroff_timeout;               /* 30  */
		union hidpp20_button_binding buttons[16];           /* 32  */
		union hidpp20_button_binding alternate_buttons[16]; /* 96  G-Shift layer */
		union { char txt[16 * 3]; uint8_t raw[16 * 3]; } name; /* 160 */
		struct hidpp20_internal_led leds[2];     /* 208 */
		struct hidpp20_internal_led alt_leds[2]; /* 230 */
		uint8_t custom_animation_index;          /* 252 G502X Plus, G705 */
		uint8_t free;                            /* 253 */
		uint16_t crc;                            /* 254 -- but see note */
	} __attribute__((packed)) profile;
};
```
Solaar `OnboardProfile.from_bytes/to_bytes` ([`hidpp20.py` L1549-1598](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/hidpp20.py#L1549-L1598)) and cvuchener `Fields` ([`ProfileFormat.cpp` L33-74](https://github.com/cvuchener/hidpp/blob/474ac10db5673da8f2f1c8911414d394c0eb6d12/src/libhidpp/hidpp20/ProfileFormat.cpp#L33-L74)) agree on every field.

| Offset | Size | Field | Encoding / notes |
|---|---|---|---|
| 0 | 1 | report_rate | **Interval in ms** (1 = 1000 Hz, 2, 4, 8). libratbag converts with `1000/rate`. |
| 1 | 1 | default DPI index | 0-4. The index selected when the profile loads. |
| 2 | 1 | shift ("switched") DPI index | 0-4. Used while a `90 07` DPI-shift button is held. |
| 3 | 10 | DPI[0..4] | **u16 little-endian.** 0 or 0xFFFF means unused or disabled. LGS/G HUB write 0 (cvuchener). libratbag shows 0 as "disabled". |
| 13 | 3 | profile color R,G,B | cvuchener: "Unused on G502 (profile format 2)" |
| 16 | 1 | power_mode | 0xFF (n/a) on corded mice |
| 17 | 1 | angle_snapping | 0 off, 1 on |
| 18 | 2 | "revision" / "write_count", u16 LE | Purpose unknown. Solaar and cvuchener read it. **Preserve it.** |
| 20 | 8 | reserved | 0xFF |
| 28 | 2 | power-save timeout, u16 LE | Solaar's docs say ms. **[?]** A G502 X LS stores `3C 00` (60) and `2C 01` (300), which look like seconds. 0xFFFF on c08b-class corded mice **[FAM]**. |
| 30 | 2 | power-off timeout, u16 LE | same as above |
| 32 | 64 | buttons[16] × 4 | normal layer, §3.7 |
| 96 | 64 | G-Shift buttons[16] × 4 | used while a `90 0B` button is held |
| 160 | 48 | name | **UTF-16LE, 24 code units, NUL-padded.** All 0xFF means "default name". libratbag wrongly treats it as `char[48]`, so names look truncated (libratbag #680). |
| 208 | 11 | LED block 0 | §3.9 |
| 219 | 11 | LED block 1 | |
| 230 | 11 | alt LED block 0 | Solaar: "then for power saving mode". libratbag copies block 0 here on write. |
| 241 | 11 | alt LED block 1 | |
| 252 | 1 | custom_animation_index | G502 X PLUS and G705 only. Otherwise 0xFF. |
| size-2 | 2 | CRC16, BE | For a 255-byte sector the CRC sits at **253-254**, overlapping libratbag's `free` and `crc[0]`. libratbag computes it at `sector_size-2`, so it is still correct. |

cvuchener `ProfileLength` gives 208 for format 1, 230 for formats 2 and 3, and 4 LED blocks are read by Solaar and libratbag. **[?]** Format 2 (c08b) may only use the first two LED blocks.

**[FAM]** Real G502 LIGHTSPEED profile 1 (255 B, [tests.rs L28-48](https://github.com/Trukitro/OpenLogi/blob/8fb63e4b7e9fec8af6f51caa3d892b31dff06ca6/crates/openlogi-hidpp/src/feature/onboard_profiles/tests.rs#L28-L48)), decoded:
```
00: 01 01 00 | 90 01 20 03 40 06 80 0C 00 19 | FF FF FF      1 ms; default idx 1; shift idx 0; DPI 400,800,1600,3200,6400; color FFFFFF
10: FF 00 FF FF | FF×8 | FF FF FF FF                          power n/a; snap off; rev FFFF; timeouts FFFF
20: 80 01 00 01  80 01 00 02  80 01 00 04  80 01 00 08        slot0..3: L, R, M, Back
30: 80 01 00 10  90 07 00 00  90 04 00 00  90 03 00 00        slot4 Fwd, slot5 DPI-shift, slot6 DPI-, slot7 DPI+
40: 90 0C 00 00  90 02 00 00  90 01 00 00  FF FF FF FF        slot8 battery (wireless model), slot9 tilt R, slot10 tilt L, slots11-15 FF
60..9F: all FF                                                G-Shift layer not configured
A0..CF: all FF                                                default name
D0: 03 00 00 00 00 00 1F 40 00 00 00 | 03 00 00 00 00 00 1F 40 00 00 00   LED blocks 0 and 1: cycle, 8000 ms, intensity 0 (=100%)
E6..FC: FF                                                    alt blocks, custom index
FD: 3E 23                                                     CRC
```
**[PROBE]** This mouse's profile `0x0001` begins `01 01 00 B0 04 60 09 80 0C 00 19 00 00`:
- 1 ms report rate;
- default DPI index 1;
- shift DPI index 0;
- DPI 1200 / 2400 / 3200 / 6400 / 0 (unused).

That matches the table above byte for byte.

**[C08B]** omalogi reports that c08b *factory* profiles store slots 5-10 as:

| Slot | Bytes | Action |
|---|---|---|
| 5 | `90 07 FF FF` | DPI shift |
| 6 | `90 04 FF FF` | DPI − |
| 7 | `90 03 FF FF` | DPI + |
| 8 | `90 0A FF FF` | cycle profile |
| 9 | `90 02 FF FF` | tilt right |
| 10 | `90 01 FF FF` | tilt left |

A profile the owner edited in G HUB stored `90 0B 00 00` (G-Shift on slot 5), `90 0A 00 00`, and so on ([omalogi #17](https://github.com/elberacasa/omalogi/issues/17), [docs L390-417](https://github.com/elberacasa/omalogi/blob/382dea7c1c81531fe286f03b32bd1c33acb904ae/docs/hardware-tests.md#L390-L417)). omalogi also says the G-Shift layer of the c08b factory profiles "spells all 11 slots", so it is populated.

### 3.7 Button binding encoding (4 bytes per slot)
libratbag `union hidpp20_button_binding` ([`hidpp20.h` L583-665](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.h#L583-L665)), Solaar `Button` ([`hidpp20.py` L1404-1529](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/hidpp20.py#L1404-L1529)), cvuchener `readButton/writeButton`, omalogi `Binding::decode` ([`format.rs` L280-298](https://github.com/elberacasa/omalogi/blob/382dea7c1c81531fe286f03b32bd1c33acb904ae/src/onboard/format.rs#L280-L298)).

| byte0 | byte1 | byte2 | byte3 | Meaning |
|---|---|---|---|---|
| `0x80` | `0x00` | `FF` | `FF` | HID "no action". Solaar writes `80 00 FF FF`. This is the correct "disabled" for libratbag's reader (#1898). |
| `0x80` | `0x01` | maskHi | maskLo | **Mouse button(s).** BE16 bitmap: bit0 = button 1 (left), bit1 = right, bit2 = middle, bit3 = back (4), bit4 = forward (5), …, bit15 = button 16. libratbag converts with `ffs()`, so it supports one button only. |
| `0x80` | `0x02` | modifiers | key | **Keyboard key.** modifiers is the HID modifier bitmap: 0x01 LCtrl, 0x02 LShift, 0x04 LAlt, 0x08 LGUI, 0x10 RCtrl, 0x20 RShift, 0x40 RAlt, 0x80 RGUI ([`driver-hidpp20.c` L117-132](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/driver-hidpp20.c#L117-L132)). key is a HID Keyboard-page usage. Example: `80 02 01 1C` = Ctrl+Y (#1898). |
| `0x80` | `0x03` | usageHi | usageLo | **Consumer control**, a HID page 0x0C usage, BE16. For example 0x00E9 Vol+, 0x00EA Vol−, 0x00CD Play/Pause. |
| `0x90` | func | rsv | data | **Firmware special function**, see the next table. Factory c08b profiles store `rsv data = FF FF`, G HUB-written ones `00 00`, and the G502 X LS factory `FF 00`. **Preserve these bytes verbatim.** data = target profile for 0x0D. |
| `0x0?` | … | … | … | **Macro pointer.** cvuchener: byte0 = memType (0 = flash), byte1 = page, byte2-3 = offset BE16. Solaar: high nibble = behaviour (0 execute, 1 "stop", 2 "stop all" **[?]**), low nibble with byte1 = 12-bit sector, byte2-3 = address. libratbag: page = byte1, offset = byte3 only, so it supports offset < 256. |
| `0xFF` | `FF` | `FF` | `FF` | **Disabled / unassigned.** Every unused slot from 11 to 15 is FF. |

**Special function codes (byte0 = 0x90).** Sources: libratbag `HIDPP20_BUTTON_SPECIAL_*` [`hidpp20.h` L593-612](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.h#L593-L612), Solaar `ButtonFunctions` [L1419-1437](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/hidpp20.py#L1419-L1437) and [docs/capabilities.md](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/docs/capabilities.md).

| Code | libratbag name | Solaar name | Notes |
|---|---|---|---|
| 0x00 | NOOP | NO_ACTION | |
| 0x01 | TILT_LEFT | TILT_LEFT | horizontal scroll left |
| 0x02 | TILT_RIGHT | TILT_RIGHT | |
| 0x03 | NEXT_DPI | NEXT_DPI | no wrap |
| 0x04 | PREV_DPI | PREVIOUS_DPI | |
| 0x05 | CYCLE_DPI | CYCLE_DPI | wraps |
| 0x06 | DEFAULT_DPI | DEFAULT_DPI | |
| 0x07 | SHIFT_DPI | SHIFT_DPI | "sniper": uses byte 2 of the profile while held |
| 0x08 | NEXT_PROFILE | NEXT_PROFILE | |
| 0x09 | PREV_PROFILE | PREVIOUS_PROFILE | |
| 0x0A | CYCLE_PROFILE | CYCLE_PROFILE | |
| 0x0B | GSHIFT | G_SHIFT | uses the alternate table at +96 while held |
| 0x0C | BATTERY_INDICATOR | BATTERY_STATUS | "memory model ≥ 3" comment in libratbag |
| 0x0D | ENABLE_PROFILE | PROFILE_SELECT | data = profile number |
| 0x0E | PERFORMANCE_SWITCH | MODE_SWITCH | |
| 0x0F | HOST | HOST_BUTTON | |
| 0x10 | SCROLL_DOWN | SCROLL_DOWN | |
| 0x11 | SCROLL_UP | SCROLL_UP | |

libratbag only *maps* codes 0x00 to 0x0B to ratbag actions ([`hidpp20.c` L3029-3044](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L3029-L3044)). It shows 0x0B as `second-mode`.

**c08b physical button to slot map**, inferred:

| Slot | Physical button | Default binding | Spy bit (§7) |
|---|---|---|---|
| 0 | Left | `80 01 00 01` | 0 |
| 1 | Right | `80 01 00 02` | 1 |
| 2 | Middle / wheel click | `80 01 00 04` | 2 |
| 3 | Back (G4) | `80 01 00 08` | 3 |
| 4 | Forward (G5) | `80 01 00 10` | 4 |
| 5 | Sniper / DPI-shift (G6) | `90 07 ..` | 5 |
| 6 | G7 | `90 04 ..` DPI − | 6 |
| 7 | G8 | `90 03 ..` DPI + | 7 |
| 8 | G9, behind the wheel | `90 0A ..` cycle profile | 8 |
| 9 | Wheel tilt right | `90 02 ..` | 9 |
| 10 | Wheel tilt left | `90 01 ..` | 10 |

Evidence: the libratbag [#1473](https://github.com/libratbag/libratbag/issues/1473) c08b dump (`5 resolution-alternate, 6 resolution-down, 7 resolution-up, 8 profile-cycle-up, 9 wheel-right, 10 wheel-left`), the [#1831](https://github.com/libratbag/libratbag/issues/1831) spy capture (bits 0-10, with tilt R at bit 9 and L at bit 10), and the G502 LIGHTSPEED fixture. **[?]** #1831 labels bits 3/4 as "thumb back/forward (small)" and bits 6/7 as "Back/Forward". That is almost certainly a mislabel of G7/G8, but verify physically.

### 3.8 Macro memory format (macro format 1)
Opcodes come from libratbag [`hidpp20.h` L826-875](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.h#L826-L875) and cvuchener [`hidpp20/MacroFormat.cpp`](https://github.com/cvuchener/hidpp/blob/474ac10db5673da8f2f1c8911414d394c0eb6d12/src/libhidpp/hidpp20/MacroFormat.cpp). cvuchener's is the complete encoder/decoder. **The instruction length is implied by `opcode & 0xE0`:** 0x00 means 1 byte, 0x20 means 2, 0x40 means 3, 0x60 means 5.

| Op | Len | libratbag name | cvuchener name | Operands |
|---|---|---|---|---|
| 0x00 | 1 | NOOP | NoOp | none. "wait the duration of a macro step" |
| 0x01 | 1 | WAIT_FOR_RELEASE | WaitRelease | none |
| 0x02 | 1 | REPEAT_WHILE_PRESSED | RepeatUntilRelease | none |
| 0x03 | 1 | REPEAT_UNTIL_CANCELED | RepeatForever | none |
| 0x20 | 2 | ROLLER | MouseWheel | int8 |
| 0x21 | 2 | ACPAN | MouseHWheel | int8 |
| 0x40 | 3 | DELAY | Delay | u16 BE, ms |
| 0x41 | 3 | BUTTON_DOWN | MouseButtonPress | u16 BE button bitmap |
| 0x42 | 3 | BUTTON_UP | MouseButtonRelease | u16 BE |
| 0x43 | 3 | KEY_PRESS | ModifiersKeyPress | modifiers, key. A modifier-only or key-only press uses key=0 or mods=0. |
| 0x44 | 3 | KEY_RELEASE | ModifiersKeyRelease | modifiers, key |
| 0x45 | 3 | CONS_DOWN | ConsumerControlPress | u16 BE usage |
| 0x46 | 3 | CONS_UP | ConsumerControlRelease | u16 BE usage |
| 0x60 | 5 | JUMP | Jump | **memType, page, offset u16 BE** (cvuchener). **[?]** libratbag's struct says `type, offset, page` (3 bytes). That contradicts the length rule. libratbag never writes macros, so trust cvuchener. |
| 0x61 | 5 | XY | MousePointer | int16 BE dx, int16 BE dy |
| 0xFF | 1 | END | End | none. **Every macro must end with END**, or the firmware runs whatever follows. |

Placement rules:
- cvuchener writes macros into flash pages *after* the last profile page ([`hidpp-persistent-profiles.cpp` L172-183](https://github.com/cvuchener/hidpp/blob/474ac10db5673da8f2f1c8911414d394c0eb6d12/src/tools/hidpp-persistent-profiles.cpp#L172-L183)).
- Macro pages also end with a 2-byte CRC.
- When an instruction plus a JUMP plus the CRC no longer fits, a JUMP to offset 0 of the next page is inserted ([`Macro.cpp` L293-380](https://github.com/cvuchener/hidpp/blob/474ac10db5673da8f2f1c8911414d394c0eb6d12/src/libhidpp/hidpp/Macro.cpp#L293-L380)).
- Jump destinations must be addressable, so cvuchener pads with NoOp.
- HID++ 2.0 macro format 1 has no conditional jumps (cvuchener [`profile_format.md`](https://github.com/cvuchener/hidpp/blob/474ac10db5673da8f2f1c8911414d394c0eb6d12/profile_format.md)).

**[C08B]** G HUB-made macros on c08b decode through libratbag as delay and key sequences, for example `↓KEY_2 300ms ↑KEY_2 1000ms …` ([#1862](https://github.com/libratbag/libratbag/issues/1862)). So macro pages exist in user flash on configured mice.

### 3.9 LED effect blocks inside a profile (11 bytes each)
libratbag `struct hidpp20_internal_led` ([`hidpp20.h` L743-813](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.h#L743-L813)), `read_led`/`write_led` ([`hidpp20.c` L2667-2710, L2881-2926](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L2881-L2926)), Solaar `LEDEffects` ([`hidpp20.py` L1205-1269](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/hidpp20.py#L1205-L1269)), cvuchener `RGBEffect` fields.

The block is `[effectId][10 parameter bytes]`. **These are effect IDs, not zone-effect indices.** In the table, `b[n]` is a byte offset inside the 11-byte block.

| ID | Effect | Layout |
|---|---|---|
| 0x00 | Off | all 0 |
| 0x01 | Fixed | b[1..3] = R,G,B. b[4] = ramp: 0 default, 1 ramp, 2 no ramp (Solaar). libratbag writes 0 there. |
| 0x02 | Pulse (legacy) | Solaar: color b[1..3], speed b[4] |
| 0x03 | Cycle | b[1..5] unused. b[6..7] = period **BE16 ms**. b[8] = intensity 1-100, where 0 means 100. |
| 0x04 | Color wave | **[?]** Conflicting layouts in Solaar (`period@b[7..8]`, `direction@b[10]`) and OpenRGB (§4) |
| 0x05 | Starlight | sky RGB b[1..3], star RGB b[4..6] |
| 0x0A | Breathing | RGB b[1..3], period BE16 b[4..5], waveform b[6] (0 default, 1 sine, 2 square, 3 triangle, 4 sawtooth, 5 sharkfin, 6 exponential), intensity b[7] (0 means 100) |
| 0x0B | Ripple | RGB b[1..3], b[4] reserved, period BE16 b[5..6] |
| 0x0C | Custom | slot b[1], init_frame BE16, length BE16, frame_period BE16, intensity (G502X Plus style) |

Block *i* is the LED for 0x8070 zone *i*: libratbag uses `profile->leds[led->index]` ([`driver-hidpp20.c` L329-361](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/driver-hidpp20.c#L329-L361)). On c08b, zone 0 is "Primary" and zone 1 is "Logo". **[?]** cvuchener names 208 "logo_effect" and 219 "side_effect", and Solaar says "first usually for the logo LEDs". So it is unverified which physical LED block 0 drives on c08b. Test it.

### 3.10 Current profile and DPI index
- **getCurrentProfile** returns `[memType, page]`. libratbag reads `params[1]` and, with `HIDPP20_QUIRK_INDEX_OFFSET`, decrements it ([`hidpp20.c` L2098-2129, L2275-2283](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L2275-L2283); [`hidpp20.h` L55-61](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.h#L55-L61)). The quirk was added for G502 HERO, HERO Wireless, Proteus Spectrum and G604 in [PR #1799](https://github.com/libratbag/libratbag/pull/1799), which fixed #1323/#1606 ("active profile index skips one forward"). In plain terms, **the byte is the 1-based page number**. **[PROBE]** This mouse returned `00 02` while its live settings matched sector `0x0002`. libratbag on this system shows the active profile one slot off, i.e. it ran without the quirk (§0.4).
- **setCurrentProfile:** libratbag sends `[0x00, index+1]` ([L2186-2211](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L2186-L2211)). Solaar sends the BE16 sector (`00 01`, or `01 01` for ROM profile 1). omalogi sends `[0x00, n]` ([`feature.rs` L95-98](https://github.com/elberacasa/omalogi/blob/382dea7c1c81531fe286f03b32bd1c33acb904ae/src/onboard/feature.rs#L95-L98)). Activating a profile writes nothing to flash.
- **[?] Firmware quirk** (omalogi, G502 X LS, [docs L40-49](https://github.com/elberacasa/omalogi/blob/382dea7c1c81531fe286f03b32bd1c33acb904ae/docs/hardware-tests.md#L40-L49)): "turning on a profile placed before the active one moves the mouse's current profile back by one position without loading it". After any directory write, re-select the intended profile.
- **get/setCurrentDpiIndex** (0xB?/0xC?): 0-based index into the 5 DPI slots. They only work in onboard mode. libratbag calls set after every commit for the active resolution ([`driver-hidpp20.c` L1542-1550](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/driver-hidpp20.c#L1542-L1550)).

---

## 4. LEDs: 0x8070 Color LED Effects (present on c08b), 0x8071 RGB Effects (absent), 0x1300 (present)

### 4.1 0x8070 functions
OpenLogi [`color_led_effects.rs`](https://github.com/AprilNEA/OpenLogi/blob/7aaa4f1408a998006f17c53945ef71fa8d3dd5c4/crates/openlogi-hidpp/src/feature/color_led_effects.rs) is the most complete source. It is cross-checked with OpenRGB `LOGITECH_FP8070` ([`LogitechProtocolCommon.h` L95-113](https://gitlab.com/CalcProgrammer1/OpenRGB/-/blob/c43424b4ba94748b913a6551c274251a5211510c/Controllers/LogitechController/LogitechProtocolCommon.h#L95-L113)), libratbag [`hidpp20.c` L871-1093](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L871-L1093) and Solaar.

| fn | byte3 | Name | Request | Reply |
|---|---|---|---|---|
| 0 | 0x0? | getInfo | none | `zoneCount, nvCaps BE16, extCaps BE16`. extCaps bits: b0 getZoneEffect supported, b1 *no* getEffectSettings, b2 setLedBinInfo, b3 monochrome only, b4 *no* sync |
| 1 | 0x1? | getZoneInfo | `zone` | `zone, location BE16, numEffects, persistencyCaps`. location: 1 Primary, 2 Logo, 3 Left, 4 Right, 5 Combined, 6-11 Primary1-6. persistencyCaps: b0 always on, b1 always off, b2 on then off. |
| 2 | 0x2? | getZoneEffectInfo | `zone, effectIdx` | `zone, effectIdx, effectId BE16, caps BE16, period BE16` |
| 3 | 0x3? | **setZoneEffect** | `zone, effectIdx, p0..p9, persistence` (13 bytes, long report) | none |
| 4 | 0x4? | getNvConfig (v1+) | `capHi capLo` | `cap, state, p1, p2` |
| 5 | 0x5? | setNvConfig (v1+) | `capHi capLo state p1 p2` | EEPROM write, use sparingly |
| 6 | 0x6? | getLedBinInfo | `zone, binIdx` | |
| 7 | 0x7? | getSwControl (v1+) | none | `control (0 firmware, 1 software), syncEvents` |
| 8 | 0x8? | **setSwControl** (v1+) | `control, syncEvents` | none |
| 9 | 0x9? | getEffectSettings | `zone, source (0 RAM, 1 EEPROM)` | |
| 10 | 0xA? | clearEffectSettings, i.e. revert the zone to its default | `zone` | |
| 11 | 0xB? | setCycleDirection | `0 clockwise / 1 anti` | |
| 12 | 0xC? | getZoneColor | `zone` | `zone, R, G, B` |
| 13 | 0xD? | synchronizeEffect (v1+) | `zone, 0, driftHi, driftLo` | |
| 14 | 0xE? | getZoneEffect | `zone, source` | `zone, effectIdx, params…` (needs extCaps b0) |
| 15 | 0xF? | setLedBinInfo | | |

**persistence** (byte 12 of setZoneEffect): **0 volatile (RAM only)**, 1 RAM + EEPROM, 2 EEPROM only ([`types.rs` L89-101](https://github.com/AprilNEA/OpenLogi/blob/7aaa4f1408a998006f17c53945ef71fa8d3dd5c4/crates/openlogi-hidpp/src/feature/color_led_effects/types.rs#L89-L101)). OpenRGB documents the byte as "Persistence bits 1-0, Power bits 2-3" and sets 0x01 only on Save ([`LogitechHIDPP20Controller.cpp` L5819-5827](https://gitlab.com/CalcProgrammer1/OpenRGB/-/blob/c43424b4ba94748b913a6551c274251a5211510c/Controllers/LogitechController/LogitechHIDPP20Controller/LogitechHIDPP20Controller.cpp#L5819-L5827)). libratbag always sends 1, with the comment "write to RAM and flash" ([L1027-1033](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L1027-L1033)). Solaar sends nothing there, i.e. 0.

**The effect index matters.** setZoneEffect byte 1 is the zone's **effect index** from the getZoneEffectInfo enumeration, *not* the effect ID:
- Solaar `LEDZoneInfo.to_command` emits `zone, i, params` ([`hidpp20.py` L1364-1369](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/hidpp20.py#L1364-L1369)).
- OpenRGB and OpenLogi do the same.
- libratbag's direct path puts the effect *ID* there. That is a latent bug, but the path is only used when 0x8100 is absent, so it never runs on c08b.
- The legacy OpenRGB GLightsync controller hard-codes idx 0 off, 1 static, 2 cycle, 3 breathing. **This does not match c08b**, where idx 2 is breathing and idx 3 is cycle. Always enumerate.

The 10 parameter bytes p0..p9 equal bytes 1..10 of the profile LED block (§3.9). Layouts from OpenRGB `SetZoneEffect` ([L5608-5827](https://gitlab.com/CalcProgrammer1/OpenRGB/-/blob/c43424b4ba94748b913a6551c274251a5211510c/Controllers/LogitechController/LogitechHIDPP20Controller/LogitechHIDPP20Controller.cpp#L5608-L5827)). In this table, "data[n]" is the position in the full parameter block, where data[0] = zone and data[1] = idx:

| Effect ID | Name | Parameters |
|---|---|---|
| 0x0001 | Static | data[2..4] = R,G,B. data[5] = 0x02 when a color is set (Solaar's "ramp = no ramp"). |
| 0x000A | Breathing | data[2..4] = RGB, data[5..6] = period BE ms, data[7] = waveform 0, data[8] = brightness 0-100 |
| 0x0003 | Cycle | data[7..8] = period BE ms, data[9] = brightness |
| 0x0004 | Wave | data[8] = period lo, data[9] = direction 1-8, data[10] = brightness, data[11] = period hi. **[?]** Solaar differs. |
| 0x000B | Ripple | data[2..4] = RGB, data[6..7] = period BE |
| 0x0007 | Audio visualizer | data[2] = control (0 fixed, 1 cycle), data[3..5] = RGB, data[7..8] = period |

**[C08B]** Trace in Solaar #2313:
```
getInfo                -> 02 0003 0000            2 zones, nvCaps 0x0003, extCaps 0x0000
getZoneInfo(0)         -> 00 0001 04 00           zone0 Primary, 4 effects, no persistency caps
getZoneInfo(1)         -> 01 0002 04 00           zone1 Logo,    4 effects
getZoneEffectInfo(z,0) -> zz 00 0000 0000 0000    Disabled
getZoneEffectInfo(z,1) -> zz 01 0001 0005 0000    Fixed      caps 0x0005
getZoneEffectInfo(z,2) -> zz 02 000A C005 03E0    Breathing  caps 0xC005, period field 0x03E0 [?]
getZoneEffectInfo(z,3) -> zz 03 0003 C005 03E0    Cycle      caps 0xC005, period field 0x03E0 [?]
setSwControl(0)        -> (ack)                   0x02 0x8? 00 : firmware owns the LEDs
getZoneEffect(0)       -> 00 01 FF FF FF 00..     zone0 effect idx 1 (Fixed), white
```
getZoneEffect (0xE?) answers even though extCaps bit 0 is clear. Solaar uses that bit as "readable" ([`hidpp20.py` L1375-1383](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/hidpp20.py#L1375-L1383)), which explains why it shows "LEDs Primary: None" for c08b.

### 4.2 Software control and per-frame color (screen sampler, audio visualizer)
- **Claim.** 0x8070 `setSwControl` = fn 8, params `01 01`. Release with `00 00`. OpenRGB comments: "0x8070: simple [enabled, persist]. the official app/legacy send [1,1] to claim and [0,0] to release" ([L3925-3963](https://gitlab.com/CalcProgrammer1/OpenRGB/-/blob/c43424b4ba94748b913a6551c274251a5211510c/Controllers/LogitechController/LogitechHIDPP20Controller/LogitechHIDPP20Controller.cpp#L3925-L3963)). OpenLogi names the second byte `syncEvents`. The legacy OpenRGB controller sends `10 FF <idx> 8A 01 01` "If direct, disable save to flash" ([`LogitechGLightsyncController.cpp` L139-160](https://gitlab.com/CalcProgrammer1/OpenRGB/-/blob/c43424b4ba94748b913a6551c274251a5211510c/Controllers/LogitechController/LogitechGLightsyncController/LogitechGLightsyncController.cpp#L139-L160)). For "0x8070 ZONE-ONLY devices (… 0x8070 mice) the claim is just SetSWControl(1,1) … with no power/host-mode tail" ([L4057-4078](https://gitlab.com/CalcProgrammer1/OpenRGB/-/blob/c43424b4ba94748b913a6551c274251a5211510c/Controllers/LogitechController/LogitechHIDPP20Controller/LogitechHIDPP20Controller.cpp#L4057-L4078)). Solaar's "LED Control" setting reads fn7 and writes fn8 with 1 meaning Solaar control ([`settings_templates.py` L3204-3221](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/settings_templates.py#L3204-L3221)).
- **Per frame.** For each zone, send setZoneEffect `zone, idxOfFixed, R, G, B, 0x02, 00×6, persistence=00` as a long report: `11 FF <idx> 3s zone idx R G B 02 00 00 00 00 00 00 00 00 00 00`. Persistence 0 keeps EEPROM untouched. Ramp 0x02 avoids the firmware fade.
- **[?]** The achievable frame rate is undocumented. Each frame is one round trip per zone. Throttle to roughly 30-60 Hz and watch for BUSY (0x08).
- In onboard mode, a profile switch or replug restores the profile's LED blocks. The live state is volatile.
- Solaar's RGB claim for 0x8071 devices also switches 0x8100 to host mode (`0x10 02`) to stop firmware power management. OpenRGB does this for 0x8071 but not for 0x8070.

### 4.3 0x8071 RGB Effects (not on c08b, for reference)
Sources: libratbag `CMD_RGB_EFFECTS_*` ([`hidpp20.c` L1099-1107](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L1099-L1107)), OpenRGB `LOGITECH_FP8071` ([`LogitechProtocolCommon.h` L115-137](https://gitlab.com/CalcProgrammer1/OpenRGB/-/blob/c43424b4ba94748b913a6551c274251a5211510c/Controllers/LogitechController/LogitechProtocolCommon.h#L115-L137)), Solaar [`rgb_power.py`](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/rgb_power.py).

| fn | Name | Notes |
|---|---|---|
| 0 | getInfo | `[clusterIdx, effectIdx, typeOfInfo]`. Use `FF FF 00` for device info, `c FF 00` for cluster info, `c e 00` for effect info. |
| 1 | setRgbClusterEffect | `cluster, effectIdx, p0..p9, persist` |
| 2 | setMultiLedRgbClusterPattern | |
| 3 | manageNvConfig | |
| 4 | manageRgbLedBinInfo | |
| 5 | manageSwControl | `01 mode flags`. Solaar SW_ACTIVE = `01 03 04`, SW_IDLE = `01 03 02`, release = `01 00 00`. Flags: b0 effect, b1 power, b2 NV config. |
| 6 | setEffectSyncCorrection | |
| 7 | manageRgbPowerModeConfig | `01 00 00 idleHi idleLo sleepHi sleepLo` |
| 8 | manageRgbPowerMode | |
| 9 | shutdown | |

Event fn1 is onUserActivity.

### 4.4 0x1300 LED SW control (present on c08b, purpose there unknown **[?]**)
Sources: libratbag [`hidpp20.c` L497-759](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L497-L759), [`hidpp20.h` L177-299](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.h#L177-L299), OpenLogi [`led_control.rs`](https://github.com/AprilNEA/OpenLogi/blob/7aaa4f1408a998006f17c53945ef71fa8d3dd5c4/crates/openlogi-hidpp/src/feature/led_control.rs).

| fn | Name | Request | Reply / notes |
|---|---|---|---|
| 0 | getLedCount | none | |
| 1 | getLedInfo | `idx` | `idx, type (1 battery, 2 DPI, 3 profile, 4 logo, 5 cosmetic), physicalCount, caps BE16, nvCaps` |
| 2 | getSwCtrl | none | |
| 3 | setSwCtrl | `1` software / `0` firmware | |
| 4 | getLedState | `idx` | |
| 5 | setLedState | `idx, mode BE16, 6 param bytes` | Long report. Modes: 0x01 off, 0x02 on, 0x04 blink, 0x08 travel, 0x10 ramp up, 0x20 ramp down, 0x40 heartbeat, 0x80 breathing. |
| 6 | getNvConfig | | |

On c08b this probably drives the DPI-level indicator LEDs. libratbag #1181 reports "can't control DPI leds". Unverified.

---

## 5. Report rate: 0x8060 (present on c08b) and 0x8061 (absent)

### 5.1 0x8060
Sources: libratbag [`hidpp20.c` L1694-1777](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L1694-L1777), Solaar `ReportRate` ([`settings_templates.py` L592-623](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/settings_templates.py#L592-L623)), OpenLogi [`report_rate.rs`](https://github.com/AprilNEA/OpenLogi/blob/7aaa4f1408a998006f17c53945ef71fa8d3dd5c4/crates/openlogi-hidpp/src/feature/report_rate.rs).

| fn | Name | Request | Reply |
|---|---|---|---|
| 0 | getReportRateList | none | `bitmap`: bit n means (n+1) ms is supported |
| 1 | getReportRate | none | `ms` |
| 2 | setReportRate | `ms` | none. An unsupported value gives INVALID_ARGUMENT. |

**[C08B]** The list is `0x8B` = 1000 1011b, so 1, 2, 4 and 8 ms are supported. libratbag only exposes 125, 250, 500 and 1000 Hz and rounds 3, 5, 6 and 7 ms ([`driver-hidpp20.c` L821-883](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/driver-hidpp20.c#L821-L883)). Solaar's description says "May need Onboard Profiles set to Disable to be effective". In onboard mode the profile's byte 0 is authoritative. libratbag, when 0x8100 is present, never calls setReportRate and writes profile byte 0 instead ([L1052-1073](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/driver-hidpp20.c#L1052-L1073)).

### 5.2 0x8061 Extended (not on c08b)
Sources: Solaar `ExtendedReportRate` ([L625-653](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/settings_templates.py#L625-L653)), OpenLogi [`extended_report_rate.rs`](https://github.com/AprilNEA/OpenLogi/blob/7aaa4f1408a998006f17c53945ef71fa8d3dd5c4/crates/openlogi-hidpp/src/feature/extended_report_rate.rs).

| fn | Name | Request | Reply |
|---|---|---|---|
| 0 | getDeviceCapabilities | `connType` (0 wired, 1 gaming wireless) | rate mask in byte 1 |
| 1 | getActualReportRateList | none | byte 1 mask: b0 125 Hz, b1 250, b2 500, b3 1000, b4 2000, b5 4000, b6 8000 |
| 2 | getReportRate | `connType` | `rateIdx`: 0 = 125 Hz … 6 = 8 kHz |
| 3 | setReportRate | `rateIdx` | |

Event 0 is a "rate changed" broadcast.

---

## 6. DPI: 0x2201 Adjustable DPI (present on c08b) and 0x2202 Extended (absent)

### 6.1 0x2201
Sources: libratbag [`hidpp20.c` L1497-1688](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L1497-L1688), Solaar `produce_dpi_list` / `AdjustableDpi` ([`settings_templates.py` L1035-1086](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/settings_templates.py#L1035-L1086)), OpenLogi [`adjustable_dpi.rs` L21-160](https://github.com/AprilNEA/OpenLogi/blob/7aaa4f1408a998006f17c53945ef71fa8d3dd5c4/crates/openlogi-hidpp/src/feature/adjustable_dpi.rs#L21-L160).

| fn | Name | Request | Reply |
|---|---|---|---|
| 0 | getSensorCount | none | `count` |
| 1 | getSensorDpiList | `sensor` | `sensor, v0 BE16, v1 BE16, …`, terminated by `0000` or end of payload |
| 2 | getSensorDpi | `sensor` | `sensor, dpi BE16, defaultDpi BE16`. defaultDpi exists from v1. If dpi is 0, use the default (Solaar). |
| 3 | setSensorDpi | `sensor, dpi BE16` | Echo `sensor, dpi`. Version 0 does not echo, and libratbag accepts a 0 echo. **[C08B]** replies with zeros. |

**DPI list range encoding.** A value whose top 3 bits are `111` (`0xE000 | step`) is a range marker. The range starts at the *previous* explicit value and ends at the *next* value, with step `value & 0x1FFF`. Solaar and OpenLogi implement it this way, and OpenLogi always includes the high endpoint. libratbag interprets it more loosely: any value > 0xE000 sets a global step, and min and max are taken over the explicit values.

**[C08B]** Observed:
```
w 11 FF 0A 1E 00 …                getSensorDpiList(0)
r 11 FF 0A 1E 00 0064 E032 6400 0000…    -> 100 .. 25600 step 50
w 11 FF 0A 3D 00 09 60 …          setSensorDpi(0, 2400)
r 11 FF 0A 3D 00 00 00 …          ack, no echo
```
In onboard mode a setSensorDpi is temporary. The next profile load or DPI button press re-applies the profile's DPI table (Solaar docs, [capabilities.md §Onboard Profiles](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/docs/capabilities.md)). libratbag never calls setSensorDpi when 0x8100 exists. It edits profile bytes 3-12 instead.

### 6.2 0x2202 Extended (not on c08b)
Source: Solaar `ExtendedAdjustableDpi` ([L1088-1167](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/settings_templates.py#L1088-L1167)).

| fn | byte3 | Name | Request | Reply |
|---|---|---|---|---|
| 1 | 0x1? | getSensorCapabilities | `sensor` | reply[2]: b0 = separate Y, b1 = LOD |
| 2 | 0x2? | getSensorDpiRanges | `sensor, direction (0 X, 1 Y), page` | 3 header bytes, then the same BE16 list and range encoding as 0x2201, paged until `0000` |
| 5 | 0x5? | getSensorDpiParameters | `sensor` | `sensor, dpiX, defX, dpiY, defY, lod` |
| 6 | 0x6? | setSensorDpiParameters | `sensor, dpiX BE16, dpiY BE16, lod` | |

**[?]** The function 0 name is inferred.

---

## 7. Buttons in software: 0x8110 Mouse Button Spy (c08b) vs 0x1B04 Reprog Controls V4 (absent)

### 7.1 Which feature the G502 HERO uses
c08b exposes **0x8110 and no 0x1B0x**. The same holds for G502 LIGHTSPEED, G502 X and G502 X PLUS, as OpenLogi #392 shows: "the G502 exposes no ReprogControls feature at all … G-series keep their button map in onboard profile flash". Solaar can therefore only "rebind" c08b buttons through onboard-profile YAML (Solaar #2914, #3316, #3182). libratbag only logs "device has configurable mouse button spy" ([`driver-hidpp20.c` L1466-1469](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/driver-hidpp20.c#L1466-L1469)).

### 7.2 0x8110 functions
cvuchener [`IMouseButtonSpy.h`](https://github.com/cvuchener/hidpp/blob/474ac10db5673da8f2f1c8911414d394c0eb6d12/src/libhidpp/hidpp20/IMouseButtonSpy.h) / [`.cpp`](https://github.com/cvuchener/hidpp/blob/474ac10db5673da8f2f1c8911414d394c0eb6d12/src/libhidpp/hidpp20/IMouseButtonSpy.cpp), confirmed by OpenLogi fork [`mouse_button_spy.rs`](https://github.com/CharlieMc0/OpenLogi/blob/4e835ed2258cdad104e094205462b44299eaa78b/crates/openlogi-hidpp/src/feature/mouse_button_spy.rs) on G502 X PLUS hardware.

| fn | byte3 | Name | Request | Reply |
|---|---|---|---|---|
| 0 | 0x0? | getMouseButtonCount | none | `count`. **[C08B]** = `0x0B` (11) per #1831. |
| 1 | 0x1? | startMouseButtonSpy | none | none |
| 2 | 0x2? | stopMouseButtonSpy | none | none |
| 3 | 0x3? | getMouseButtonMapping | none | `m0 … m(n-1)`: one byte per physical button. 0 = disabled, 1-16 = HID button number. **[C08B]** = `01 02 … 0B`. |
| 4 | 0x4? | setMouseButtonMapping | `m0 … m(n-1)` (≤ 16) | none. **[?]** The byte layout comes from cvuchener's docs and has not been verified on hardware. |

**Event 0 (mouseButtonEvent):** `11 FF <spyIdx> 00 maskHi maskLo 00…`. The mask is a BE16 bitmap of *currently held* physical buttons, where bit i means slot i (1-based ordinal i+1). Diff successive masks to get press and release. Several simultaneous changes can arrive in one report.

Wheel rotation is not included, because REL_WHEEL comes from interface 0 ([#1831](https://github.com/libratbag/libratbag/issues/1831); OpenLogi fork [`event.rs`](https://github.com/CharlieMc0/OpenLogi/blob/4e835ed2258cdad104e094205462b44299eaa78b/crates/openlogi-hidpp/src/feature/mouse_button_spy/event.rs)). c08b bit assignments are in the table in §3.7.

Semantics, quoted from cvuchener's header:
> MouseButtonSpy can send events with raw button events independent of any remapping or profile settings… Button can be remapped or disabled for standard HID reports but it does not affect how they are reported in MouseButtonSpy event. **If an on-board profile is used, the remapping does not apply. For using the remapping from this feature, on-board profiles must be disabled by setting HostMode** in the OnboardProfiles feature. Button mapping is reset with the mouse.

- **Do you have to call start?** #1831 (c08b) claims events "arrive automatically… no explicit start spy call is required" and calls fn1 "getSpyMode". pfps' MX518 does *not* report automatically. **[?] Likely explanation:** #1831's probe of fn 1 *was* startMouseButtonSpy, since it returns an empty payload. **Always call fn1 to start and fn2 on exit.** The OpenLogi fork registers its listener before start, then stops on every exit path and offers `--stop` to recover a stuck spy.
- **Onboard mode:** "the spy streams cleanly in the device's default Onboard mode (no mode switch needed)", and "The firmware still acts on [DPI shift / profile cycle / DPI up / DPI down] itself… the spy tap cannot suppress it (that needs Host mode)". This was verified on G502 X PLUS ([CharlieMc0/OpenLogi PR #1](https://github.com/CharlieMc0/OpenLogi/pull/1), [`spy.rs` L28-50](https://github.com/CharlieMc0/OpenLogi/blob/4e835ed2258cdad104e094205462b44299eaa78b/crates/openlogi-device/src/session/gesture/spy.rs#L28-L50)).
- **Gotcha** reported in #1831: an `EVIOCGRAB` on the *kbd* evdev node that shares interface 1 made hidraw reads on that interface return stale or empty data. **[?]** This has not been explained.

### 7.3 How to build "G HUB-style software mode" on c08b
None of the projects implements full host mode. The options below are derived from the semantics above, so treat them as a design proposal, not a recipe anyone has verified.

**A. Stay in onboard mode and use spy as a tap.** Proven to work on G502 X PLUS, and lowest risk.
1. In the active profile, bind each button you want handled in software to `80 00 FF FF` (HID no-op) or `FF FF FF FF`. The firmware then produces no native report for it. A `90 xx` binding would keep its firmware behaviour, such as a DPI change.
2. Call startMouseButtonSpy and act on the mask edges. Synthesize output through uinput.
3. Native buttons you leave bound, such as L/R, keep working with zero added latency.
4. G-Shift can be done in software. Track the state of whichever slot you treat as "shift" in the spy mask. The firmware's own `90 0B` G-Shift layer only works for firmware-encodable actions.

**B. Host mode (setMode 2).** This matches cvuchener's description of what Host mode is for.
1. The profile DPI table, report rate, LED blocks and button bindings stop applying.
2. Drive DPI with 0x2201 setSensorDpi and the rate with 0x8060 setReportRate.
3. Drive LEDs with 0x8070, using setSwControl and volatile setZoneEffect.
4. Native button reports follow the 0x8110 mapping. Use setMouseButtonMapping with 0 to silence a button, then read spy events.
5. setCurrentProfile and setCurrentDpiIndex return INVALID_ARGUMENT, and 0x8100 events stop.
6. Re-apply everything on each reconnect, because the mapping "is reset with the mouse".

**[?]** Unknowns for B:
- whether the mode persists across replug;
- what DPI and rate the mouse uses right after entering host mode (probably the last 0x2201/0x8060 values);
- what native HID button numbers G6-G9 and the tilts produce by default under the identity mapping `01..0B`.

### 7.4 0x1B04 Reprogrammable Controls V4 (absent on c08b, for reference)
Sources: libratbag [`hidpp20.c` L1269-1455](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L1269-L1455), Solaar `ReprogrammableKeyV4` / `KeyFlag` / `MappingFlag` ([`hidpp20.py` L91-131, L445-613, L761-779](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/hidpp20.py#L445-L613)), events in [`notifications.py` L364-377](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/notifications.py#L364-L377) and [`diversion.py` L1444-1458](https://github.com/pwr-Solaar/Solaar/blob/e7304c4c451cc9bb4f206a914844525e67856a28/lib/logitech_receiver/diversion.py#L1444-L1458).

| fn | Name | Request | Reply |
|---|---|---|---|
| 0 | getCount | none | `n` |
| 1 | getCidInfo | `index` | `cid BE16, tid BE16, flags1, pos, group, gmask, flags2`. Flags: 0x01 mouse, 0x02 fn, 0x04 nonstandard, 0x08 fn-sensitive, 0x10 reprogrammable, 0x20 divertable, 0x40 persistently divertable, 0x80 virtual, 0x100 rawXY, 0x200 force rawXY, 0x400 analytics, 0x800 raw wheel. |
| 2 | getCidReporting | `cid BE16` | `cid BE16, flags, remap BE16, [flags2]` |
| 3 | setCidReporting | `cid BE16, flags, remap BE16` | Long report. Flags: b0 divert, b1 divert-valid, b2 persist, b3 persist-valid, b4 rawXY, b5 rawXY-valid. libratbag always sets the valid bits. remap 0 means unchanged. |

Events:
- 0 divertedButtons: up to 4 pressed CIDs as BE16 each.
- 1 divertedRawXY: dx, dy as int16 BE.
- 2 analyticsKeyEvents.

---

## 8. How libratbag handles modes and G-Shift, plus pitfalls

### 8.1 libratbag behaviour on 0x8100 devices
1. **It forces onboard mode at startup.** `hidpp20_onboard_profiles_allocate` calls `set_onboard_mode(HIDPP20_ONBOARD_MODE)` if the mode is not onboard ([`hidpp20.c` L2260-2273](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L2260-L2273)). **A running ratbagd, which is D-Bus activated (for example by Piper), will kick your daemon out of host mode.** Mask or stop it.
2. It never uses host mode, 0x2201 set or 0x8060 set while 0x8100 exists. Everything goes into profile sectors. LED changes also go only into profile blocks, with no live setZoneEffect ([`driver-hidpp20.c` L690-740](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/driver-hidpp20.c#L690-L740)).
3. **Commit rewrites every enabled profile plus the directory**, dirty or not ([`hidpp20.c` L2992-3027](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L2992-L3027)). That causes needless flash wear. Solaar, by contrast, writes only changed sectors.
4. **Writes are not read-modify-write.** `write_profile` starts from `memset(data, 0xff)` and fills in only report rate, DPI indices, DPI, timeouts, LEDs, the normal button table and the name ([L2928-2990](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L2928-L2990)). As a result:
   - **the G-Shift table (+96..159) is wiped to 0xFF**;
   - profile color, power mode, angle snapping, the revision counter and the reserved bytes become 0xFF;
   - the alt LED blocks are overwritten with the normal LEDs;
   - a default (all-FF) name is written back as zeros.

   This is the long-standing "Piper messed up my G-Shift binds" problem in [#598](https://github.com/libratbag/libratbag/issues/598). [PR #988](https://github.com/libratbag/libratbag/pull/988) only preserves unknown button *types* in the normal table.
5. **G-Shift ("second mode").** libratbag exposes special 0x0B as `RATBAG_BUTTON_ACTION_SPECIAL_SECOND_MODE` but does not parse or write the alternate table. It reports `min(button_count, 16)` buttons, which is 11 on c08b. Open [PR #1910](https://github.com/libratbag/libratbag/pull/1910) (2026-10-23) adds a button-layer API, but only for the G600 and Kone EMP, not hidpp20.
6. **"Disabled" bug** ([#1898](https://github.com/libratbag/libratbag/issues/1898), reproduced on c08b). `RATBAG_BUTTON_ACTION_TYPE_NONE` writes `disabled.type = HIDPP20_BUTTON_HID_TYPE_NOOP` (0x00) into the **type** byte ([`driver-hidpp20.c` L602-604](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/driver-hidpp20.c#L602-L604)). Type 0x00 is a macro pointer, so a button that held `80 02 01 1C` becomes `00 01 00 1C`, a garbage macro, and every start logs "error while parsing macro". Write `80 00 FF FF` or `FF FF FF FF` instead.
7. Other libratbag defects:
   - `HIDPP20_COLOR_LED_ZONE_EFFECT_DEMO_MODE = 8` duplicates BOOT_UP. It should be 9 ([`hidpp20.h` L550-551](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.h#L550-L551)).
   - The macro JUMP struct is 3 bytes, but should be 5.
   - The button-macro offset uses only byte 3.
   - The `G305` quirk exists because some firmware returns INVALID_ARGUMENT when reading an unwritten sector 0 ([L2805-2811](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/hidpp20.c#L2805-L2811)). c08b returned zeros instead.
8. **Active profile** is handled with `INDEX_OFFSET`, see §3.10. Setting the active profile enables it first and commits if it was disabled ([`driver-hidpp20.c` L759-781](https://github.com/libratbag/libratbag/blob/8235b5bb6032dea15901ab58a8218956f4494d08/src/driver-hidpp20.c#L759-L781)).

### 8.2 Pitfalls checklist for a c08b daemon
- **Resolve feature indices** through Root.getFeature. Do not trust the table in §0.2.
- **Use a unique swid** and match `(featIdx, byte3)`. Expect interleaved reports from Solaar, OpenRGB, ratbagd or G HUB-in-a-VM. Only one program should own the mode and LEDs at a time. Specifically:
  - ratbagd forces onboard mode;
  - Solaar's settings may set host mode (Onboard Profiles = Disabled) or setSwControl;
  - OpenRGB sends setSwControl(1,1).
- **Memory reads:** re-align the last chunk to `size-16`. Never read past it.
- **Never write ROM** (≥ 0x0100) or past `sector_count`. Write the directory last. Read back and compare every write.
- **CRC:** CRC-16/CCITT-FALSE, BE, over `size-2` bytes. memoryWriteEnd returning 0x04 means the CRC was wrong **but the data was stored**. The firmware will then ignore that sector and use ROM. This is how resets work, so the mouse is recoverable, not bricked. Rewrite with a correct CRC to recover.
- **Read-modify-write.** Keep unknown bytes verbatim. That covers:
  - `90 xx FF FF` vs `00 00` tails;
  - the directory's reserved byte;
  - the revision counter;
  - reserved bytes 20-27;
  - alt LED blocks;
  - `custom_animation_index`.

  omalogi's self-test failed until it stopped normalising `90 xx FF FF`.
- **A fresh mouse may have no user directory.** All zeros or all 0xFF means it runs ROM profiles `0x0101..0x0105`. Bootstrap it by copying ROM into `0x0001..0x0005`, then writing `0x0000`.
- **Directory writes** can shift the "current profile" pointer (§3.10). Re-select the profile afterwards.
- **In onboard mode,** 0x2201, 0x8060 and LED changes are temporary. In host mode, profile and DPI-index functions fail with 0x02.
- **LED persistence:** use 0 for live and per-frame effects. 1 and 2 write EEPROM.
- **setZoneEffect takes the effect index, not the ID.** Enumerate per zone.
- **Spy:** start it explicitly, stop it on exit, and diff the masks. Remember it reports *every* button, including left click, while active.
- **Avoid** 0x00C2 (DFU), 0x1802 (reset), 0x1E00 (hidden features) and the internal 0x18xx/0x1Exx features.
- **Retry on BUSY (0x08) and on timeouts.** libratbag retries once after 10 ms.

---

## 9. Gaps and open questions (verify on hardware with read-only calls first)

1. ~~c08b getDescription bytes~~ Resolved by the probe: 16 sectors × 255 bytes, 5 ROM profiles, layout 0x0A, corded (§0.4).
2. **0x8100 functions 9 and 10:** unknown. Do not probe them on a device you care about.
3. **LED block to zone mapping on c08b:** whether block 0 is the "Primary" (DPI indicator) zone or the logo. What the "period" field `0x03E0` in getZoneEffectInfo means. What 0x1300 controls on this mouse.
4. **0x8110 setMouseButtonMapping:** the byte format is unverified. It is also unknown whether start is required (pfps vs #1831), and what native HID buttons G6-G9 emit in host mode.
5. **Host mode:** whether it persists across replug or power cycle. What DPI and rate apply on entry.
6. **Macro pointer high nibble** (Solaar's MACRO_STOP 0x1 and MACRO_STOP_ALL 0x2): only Solaar documents it.
7. **Profile bytes 16-31 on c08b**, the power and timeouts area: their meaning on a corded mouse. They are probably 0xFF and unused.
8. **Color wave (0x04) parameter layout:** Solaar and OpenRGB disagree. c08b does not list wave anyway.
9. **The G7/G8 physical labels for slots 6 and 7,** and the #1831 mislabelling of bits 3/4 vs 6/7.
10. **No public Logitech spec exists for 0x8100, 0x8070 or 0x8110.** cpg-docs only covers framing and IRoot. Everything above is reverse-engineered.
