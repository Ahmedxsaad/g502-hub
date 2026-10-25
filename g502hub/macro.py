"""Onboard macro format 1 (docs/protocol.md §3.8).

A macro is a list of steps such as ("key-down", mods, usage) or ("delay", ms).
The operand length of an opcode is implied by `opcode & 0xE0`.
"""

from . import keys

OPCODES = {
    0x00: "noop", 0x01: "wait-release", 0x02: "repeat-while-pressed",
    0x03: "repeat-forever", 0x20: "wheel", 0x21: "hwheel", 0x40: "delay",
    0x41: "button-down", 0x42: "button-up", 0x43: "key-down", 0x44: "key-up",
    0x45: "consumer-down", 0x46: "consumer-up", 0x60: "jump", 0x61: "move",
    0xFF: "end",
}
NAMES = {name: op for op, name in OPCODES.items()}
_LENGTHS = {0x00: 1, 0x20: 2, 0x40: 3, 0x60: 5}
MAX_STEPS = 4096


def step_length(op):
    return 1 if op == 0xFF else _LENGTHS[op & 0xE0]


def _signed(value, bits):
    return value - (1 << bits) if value >= 1 << (bits - 1) else value


def decode_step(data):
    op = data[0]
    name = OPCODES.get(op)
    if name is None:
        raise ValueError(f"unknown macro opcode 0x{op:02X}")
    a = data[1:step_length(op)]
    if op in (0x20, 0x21):
        return (name, _signed(a[0], 8))
    if op in (0x40, 0x41, 0x42, 0x45, 0x46):
        return (name, int.from_bytes(a, "big"))
    if op in (0x43, 0x44):
        return (name, a[0], a[1])
    if op == 0x60:
        return (name, a[0], a[1], int.from_bytes(a[2:4], "big"))
    if op == 0x61:
        return (name, _signed(int.from_bytes(a[0:2], "big"), 16),
                _signed(int.from_bytes(a[2:4], "big"), 16))
    return (name,)


def encode_step(step):
    name, *args = step
    op = NAMES[name]
    if op in (0x20, 0x21):
        return bytes([op, args[0] & 0xFF])
    if op in (0x40, 0x41, 0x42, 0x45, 0x46):
        return bytes([op]) + args[0].to_bytes(2, "big")
    if op in (0x43, 0x44):
        return bytes([op, args[0], args[1]])
    if op == 0x60:
        return bytes([op, args[0], args[1]]) + args[2].to_bytes(2, "big")
    if op == 0x61:
        return bytes([op]) + (args[0] & 0xFFFF).to_bytes(2, "big") + (args[1] & 0xFFFF).to_bytes(2, "big")
    return bytes([op])


def encode(steps):
    """Encode steps into one contiguous byte string, appending END if missing."""
    steps = list(steps)
    if not steps or steps[-1][0] != "end":
        steps.append(("end",))
    return b"".join(encode_step(s) for s in steps)


def decode(read_sector, page, offset):
    """Decode a macro starting at (page, offset), following jumps across sectors.

    `read_sector(page)` returns the bytes of a flash sector.
    """
    steps, cache = [], {}
    while len(steps) < MAX_STEPS:
        if page not in cache:
            cache[page] = read_sector(page)
        data = cache[page]
        step = decode_step(data[offset:offset + 5])
        if step[0] == "jump":
            _, _mem, page, offset = step
            continue
        steps.append(step)
        if step[0] == "end":
            return steps
        offset += step_length(NAMES[step[0]])
    raise ValueError("macro does not terminate")


def describe(step):
    name, *args = step
    if name in ("key-down", "key-up"):
        return f"{name} {keys.combo_name(args[0], args[1])}"
    if name in ("consumer-down", "consumer-up"):
        return f"{name} {keys.consumer_name(args[0])}"
    if name == "delay":
        return f"delay {args[0]} ms"
    return " ".join([name] + [str(a) for a in args])
