#!/usr/bin/env python3
"""Ask a Logitech HID++ 2.0 device which features it supports and dump them."""

import argparse
import glob
import json
import os
import select
import sys
import time

SHORT, LONG = 0x10, 0x11
SIZES = {SHORT: 7, LONG: 20}
SW_ID = 0x0A  # arbitrary, echoed back so we can match replies to requests

FEATURE_NAMES = {
    0x0000: "Root", 0x0001: "FeatureSet", 0x0002: "FeatureInfo",
    0x0003: "DeviceFwVersion", 0x0004: "DeviceUnitId", 0x0005: "DeviceName",
    0x0006: "DeviceGroups", 0x0007: "DeviceFriendlyName", 0x0008: "KeepAlive",
    0x0011: "PropertyAccess", 0x0020: "ConfigChange", 0x0021: "CryptoId",
    0x0030: "TargetSoftware", 0x00C0: "DfuControlLegacy",
    0x00C1: "DfuControlUnsigned", 0x00C2: "DfuControlSigned",
    0x00C3: "DfuControl", 0x00D0: "Dfu", 0x1000: "BatteryStatus",
    0x1001: "BatteryVoltage", 0x1004: "UnifiedBattery", 0x1300: "LedControl",
    0x1802: "DeviceReset", 0x1803: "Gpio", 0x1805: "OobState",
    0x1806: "ConfigurableDeviceProperties", 0x1811: "?0x1811",
    0x1814: "ChangeHost", 0x1815: "HostsInfo", 0x1890: "?RfTest",
    0x18A1: "?LedTest", 0x1B00: "ReprogControls", 0x1B04: "ReprogControlsV4",
    0x1BC0: "ReportHidUsage", 0x1C00: "PersistentRemappableAction",
    0x1D4B: "WirelessDeviceStatus", 0x1DF3: "?EquadDjDebug",
    0x1E00: "EnableHiddenFeatures", 0x1E22: "?SpiDirectAccess",
    0x1EB0: "?TdeAccess", 0x1F20: "AdcMeasurement", 0x2001: "LeftRightSwap",
    0x2100: "VerticalScrolling", 0x2110: "SmartShift", 0x2120: "HiResScrolling",
    0x2121: "HiResWheel", 0x2130: "LowResWheel", 0x2200: "MousePointer",
    0x2201: "AdjustableDpi", 0x2202: "ExtendedAdjustableDpi",
    0x2205: "PointerSpeed", 0x2230: "AngleSnapping", 0x2240: "SurfaceTuning",
    0x2250: "XyStats", 0x2251: "WheelStats", 0x2400: "HybridTracking",
    0x8010: "GKey", 0x8020: "MKeys", 0x8030: "MacroRecord",
    0x8040: "BrightnessControl", 0x8060: "AdjustableReportRate",
    0x8061: "ExtendedAdjustableReportRate", 0x8070: "ColorLedEffects",
    0x8071: "RgbEffects", 0x8080: "PerKeyLighting", 0x8081: "PerKeyLightingV2",
    0x8090: "ModeStatus", 0x8100: "OnboardProfiles", 0x8110: "MouseButtonSpy",
    0x8111: "LatencyMonitoring", 0x8120: "GamingAttachments",
}

# Bits of the feature "type" byte returned by FeatureSet.getFeatureID
TYPE_FLAGS = {0x80: "obsolete", 0x40: "hidden", 0x20: "engineering",
              0x10: "manuf-deactivatable", 0x08: "compliance-deactivatable"}


class HidppError(Exception):
    pass


def find_hidpp_hidraw(vid, pid):
    """Return the hidraw node of the interface that carries HID++ reports."""
    want = f"{vid:08X}:{pid:08X}"
    for node in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        with open(f"{node}/device/uevent") as f:
            if want not in f.read().upper():
                continue
        with open(f"{node}/device/report_descriptor", "rb") as f:
            desc = f.read()
        # Vendor usage page 0xFF00 with report id 0x11 = HID++ long reports
        if b"\x06\x00\xff" in desc and b"\x85\x11" in desc:
            return "/dev/" + os.path.basename(node)
    return None


class Device:
    def __init__(self, path, index=0xFF):
        self.fd = os.open(path, os.O_RDWR)
        self.index = index

    def request(self, feature_index, function, params=b"", timeout=1.0):
        params = bytes(params)
        report = SHORT if len(params) <= 3 else LONG
        func_sw = (function << 4) | SW_ID
        msg = bytes([report, self.index, feature_index, func_sw]) + params
        os.write(self.fd, msg.ljust(SIZES[report], b"\0"))

        deadline = time.monotonic() + timeout
        while (left := deadline - time.monotonic()) > 0:
            ready, _, _ = select.select([self.fd], [], [], left)
            if not ready:
                break
            data = os.read(self.fd, 64)
            if len(data) < 5 or data[0] not in SIZES or data[1] != self.index:
                continue
            if data[2] in (0xFF, 0x8F) and data[3] == feature_index and data[4] == func_sw:
                raise HidppError(f"error 0x{data[5]:02X} on feature index "
                                 f"{feature_index} function {function}")
            if data[2] == feature_index and data[3] == func_sw:
                return data[4:]
        raise TimeoutError(f"no reply for feature index {feature_index} function {function}")

    def feature_index(self, feature_id):
        reply = self.request(0, 0, feature_id.to_bytes(2, "big"))
        return reply[0] or None  # 0 means "not supported" (except Root itself)


def read_name(dev, idx):
    length = dev.request(idx, 0)[0]
    name = b""
    while len(name) < length:
        name += dev.request(idx, 1, [len(name)])
    return name[:length].decode(errors="replace")


def read_firmware(dev, idx):
    entities = []
    for e in range(dev.request(idx, 0)[0]):
        r = dev.request(idx, 1, [e])
        kind = {0: "main", 1: "bootloader", 2: "hardware", 3: "?", 4: "sensor"}.get(r[0], f"type{r[0]}")
        prefix = r[1:4].decode(errors="replace").strip("\0")
        entities.append({"type": kind, "name": prefix, "version": f"{r[4]:02X}.{r[5]:02X}",
                         "build": f"{int.from_bytes(r[6:8], 'big'):04X}"})
    return entities


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vid", type=lambda s: int(s, 16), default=0x046D)
    ap.add_argument("--pid", type=lambda s: int(s, 16), default=0xC08B)
    ap.add_argument("--hidraw", help="hidraw node (default: autodetect)")
    ap.add_argument("--json", help="also write the result to this JSON file")
    args = ap.parse_args()

    path = args.hidraw or find_hidpp_hidraw(args.vid, args.pid)
    if not path:
        sys.exit("No HID++ interface found for that device.")
    try:
        dev = Device(path)
    except PermissionError:
        sys.exit(f"Permission denied on {path}: install udev/70-g502-hub.rules first.")

    proto = dev.request(0, 1, [0, 0, 0x5A])
    print(f"{path}: HID++ {proto[0]}.{proto[1]}")

    fs = dev.feature_index(0x0001)
    count = dev.request(fs, 0)[0]
    features = [{"index": 0, "id": "0x0000", "name": "Root", "version": 0, "flags": []}]
    for i in range(1, count + 1):
        r = dev.request(fs, 1, [i])
        fid = int.from_bytes(r[0:2], "big")
        flags = [name for bit, name in TYPE_FLAGS.items() if r[2] & bit]
        features.append({"index": i, "id": f"0x{fid:04X}",
                         "name": FEATURE_NAMES.get(fid, "unknown"),
                         "version": r[3], "flags": flags})

    result = {"hidraw": path, "protocol": f"{proto[0]}.{proto[1]}", "features": features}
    ids = {int(f["id"], 16): f["index"] for f in features}
    if 0x0005 in ids:
        result["name"] = read_name(dev, ids[0x0005])
    if 0x0003 in ids:
        result["firmware"] = read_firmware(dev, ids[0x0003])

    print(f"Name: {result.get('name', '?')}")
    for fw in result.get("firmware", []):
        print(f"Firmware: {fw['type']:<10} {fw['name']} {fw['version']} build {fw['build']}")
    print(f"\n{'idx':>3}  {'id':<6}  {'ver':>3}  name")
    for f in features:
        flags = f" [{', '.join(f['flags'])}]" if f["flags"] else ""
        print(f"{f['index']:>3}  {f['id']:<6}  {f['version']:>3}  {f['name']}{flags}")

    if args.json:
        with open(args.json, "w") as out:
            json.dump(result, out, indent=2)


if __name__ == "__main__":
    main()
