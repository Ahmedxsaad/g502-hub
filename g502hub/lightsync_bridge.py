"""Install the LIGHTSYNC bridge (our LogitechLed.dll) into Wine/Proton prefixes.

Games find Logitech's LED SDK through the registry value
HKCR\\CLSID\\{a6519e67-7632-4375-afdf-caa889744403}\\ServerBinary, and 32-bit
games through the same key in the 32-bit view. In a prefix HKCR is
HKLM\\Software\\Classes, which Wine keeps in pfx/system.reg, so installing is:
copy the DLLs into drive_c and add those keys to system.reg (as text, leaving
every other byte alone). Uninstalling removes exactly that again.
"""

import json
import os
import re
import shutil
import time
from pathlib import Path

CLSID = "{a6519e67-7632-4375-afdf-caa889744403}"
BIN_DIR = Path(__file__).with_name("bridge_bin")
DLL = "LogitechLed.dll"
FOLDER = "G502 Hub"
MARKER = "g502hub-lightsync.json"
BACKUP_SUFFIX = ".g502hub.bak"

# Steam's own tools also get compatdata folders; they aren't games
TOOLS = re.compile(r"^(Proton\b|Steam Linux Runtime|Steamworks Common Redistributables)")

STEAM_ROOTS = ["~/.local/share/Steam", "~/.steam/steam", "~/.steam/root",
               "~/.var/app/com.valvesoftware.Steam/.local/share/Steam",
               "~/.var/app/com.valvesoftware.Steam/data/Steam"]


class PrefixInUse(RuntimeError):
    pass


# ------------------------------------------------------------ Steam prefixes

def _vdf_values(text, key):
    return [m.group(1).replace("\\\\", "\\") for m in re.finditer(rf'"{key}"\s+"((?:[^"\\]|\\.)*)"', text)]


def _read(path):
    try:
        return Path(path).read_text(errors="replace")
    except OSError:
        return ""


def steam_libraries(roots=None):
    """Every Steam library folder, from each Steam install's libraryfolders.vdf."""
    seen, out = set(), []
    for root in roots if roots is not None else STEAM_ROOTS:
        root = Path(os.path.expanduser(root))
        if not (root / "steamapps").is_dir():
            continue
        candidates = [root] + [Path(p) for f in ("steamapps/libraryfolders.vdf", "config/libraryfolders.vdf")
                               for p in _vdf_values(_read(root / f), "path")]
        for lib in candidates:
            real = os.path.realpath(lib)
            if real not in seen and (lib / "steamapps").is_dir():
                seen.add(real)
                out.append(lib)
    return out


def steam_prefixes(roots=None):
    """[(appid, name, pfx path)] for every Proton prefix, sorted by name."""
    libraries = steam_libraries(roots)
    names = {}
    for lib in libraries:
        for manifest in (lib / "steamapps").glob("appmanifest_*.acf"):
            found = _vdf_values(_read(manifest), "name")
            if found:
                names[manifest.stem.split("_", 1)[1]] = found[0]
    out = []
    for lib in libraries:
        compat = lib / "steamapps" / "compatdata"
        if not compat.is_dir():
            continue
        for entry in compat.iterdir():
            pfx = entry / "pfx"
            name = names.get(entry.name, f"Non-Steam game {entry.name}")
            if entry.name.isdigit() and (pfx / "system.reg").is_file() and not TOOLS.match(name):
                out.append((int(entry.name), name, pfx))
    return sorted(out, key=lambda e: (e[1].lower(), e[0]))


# ------------------------------------------------------------ is the prefix running?

def _environ(pid):
    try:
        return dict(item.split("=", 1) for item in
                    Path(f"/proc/{pid}/environ").read_bytes().decode(errors="replace").split("\0") if "=" in item)
    except OSError:
        return {}


def _locked_inodes():
    """{(major, minor, inode)} of files with a POSIX lock held, from /proc/locks."""
    out = set()
    for line in _read("/proc/locks").splitlines():
        for field in line.split():
            parts = field.split(":")
            if len(parts) == 3 and all(parts):
                try:
                    out.add((int(parts[0], 16), int(parts[1], 16), int(parts[2])))
                except ValueError:
                    pass
    return out


def prefix_in_use(pfx):
    """True while any Wine process (including wineserver) runs in this prefix."""
    pfx = os.path.realpath(pfx)
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        env = _environ(proc.name)
        if env.get("WINEPREFIX") and os.path.realpath(env["WINEPREFIX"]) == pfx:
            return True
        if env.get("STEAM_COMPAT_DATA_PATH") and \
                os.path.realpath(os.path.join(env["STEAM_COMPAT_DATA_PATH"], "pfx")) == pfx:
            return True
    # wineserver keeps a lock on /tmp/.wine-<uid>/server-<dev>-<inode of the prefix>/lock
    try:
        st = os.stat(pfx)
        lock = os.stat(f"/tmp/.wine-{os.getuid()}/server-{st.st_dev:x}-{st.st_ino:x}/lock")
    except OSError:
        return False
    return (os.major(lock.st_dev), os.minor(lock.st_dev), lock.st_ino) in _locked_inodes()


# ------------------------------------------------------------ system.reg editing

def _is_win64(text):
    m = re.search(r"^#arch=(win32|win64)$", text[:4096], re.M)
    return m is None or m.group(1) == "win64"


def _layout(pfx, text):
    """[(registry key, Windows path, DLL arch, file in the prefix)] for this prefix's architecture."""
    pfx = Path(pfx)
    base = f"Software\\\\Classes\\\\CLSID\\\\{CLSID}\\\\ServerBinary"
    if not _is_win64(text):
        return [(base, f"C:\\Program Files\\{FOLDER}\\{DLL}", "x86",
                 pfx / "drive_c" / "Program Files" / FOLDER / DLL)]
    return [(base, f"C:\\Program Files\\{FOLDER}\\{DLL}", "x64",
             pfx / "drive_c" / "Program Files" / FOLDER / DLL),
            (f"Software\\\\Classes\\\\Wow6432Node\\\\CLSID\\\\{CLSID}\\\\ServerBinary",
             f"C:\\Program Files (x86)\\{FOLDER}\\{DLL}", "x86",
             pfx / "drive_c" / "Program Files (x86)" / FOLDER / DLL)]


def _blocks(text):
    """Split system.reg into its preamble and one block per [key] section (each with its trailing lines)."""
    starts = [m.start() for m in re.finditer(r"^\[", text, re.M)]
    if not starts:
        return text, []
    return text[:starts[0]], [text[a:b] for a, b in zip(starts, starts[1:] + [len(text)])]


def _block_key(block):
    header = block.split("\n", 1)[0]
    return header[1:header.rfind("]")].lower()


def _block_value(block):
    m = re.search(r'^@="((?:[^"\\]|\\.)*)"', block, re.M)
    return m.group(1).replace("\\\\", "\\") if m else None


def _section(key, value):
    now = int(time.time())
    filetime = (now + 11644473600) * 10_000_000
    escaped = value.replace("\\", "\\\\")
    return f"[{key}] {now}\n#time={filetime:x}\n@=\"{escaped}\"\n"


def _write_atomic(path, text):
    tmp = path.with_name(path.name + ".g502hub-tmp")
    tmp.write_bytes(text.encode("latin-1"))
    os.replace(tmp, path)


def _marker_path(layout):
    return layout[0][3].with_name(MARKER)


def is_installed(pfx):
    reg = Path(pfx) / "system.reg"
    try:
        text = reg.read_bytes().decode("latin-1")
    except OSError:
        return False
    layout = _layout(pfx, text)
    values = {_block_key(b): _block_value(b) for b in _blocks(text)[1]}
    return all(f.is_file() and (values.get(key.lower()) or "").lower() == path.lower()
               for key, path, _, f in layout)


def install(pfx):
    """Point the prefix's LED SDK at our DLLs. Refuses while the prefix is running."""
    pfx = Path(pfx)
    reg = pfx / "system.reg"
    if not reg.is_file():
        raise FileNotFoundError(f"{pfx} is not a Wine prefix (no system.reg)")
    if prefix_in_use(pfx):
        raise PrefixInUse("The game (or something else in its Wine prefix) is running; close it first")
    original = reg.read_bytes()
    text = original.decode("latin-1")
    layout = _layout(pfx, text)
    for _, _, arch, _ in layout:
        if not (BIN_DIR / arch / DLL).is_file():
            raise FileNotFoundError(f"{BIN_DIR / arch / DLL} is missing; build it with bridge/logitechled/build.sh")
    marker = _marker_path(layout)
    previous = json.loads(marker.read_text()) if marker.is_file() else {}

    preamble, blocks = _blocks(text)
    replaced = dict(previous.get("replaced", {}))
    appended = []
    for key, path, _, _ in layout:
        ours = _section(key, path)
        index = next((i for i, b in enumerate(blocks) if _block_key(b) == key.lower()), None)
        if index is None:
            appended.append(ours)
            continue
        old = blocks[index]
        if (_block_value(old) or "").lower() == path.lower():
            continue  # already ours
        replaced.setdefault(key, old)  # someone else's ServerBinary: put it back on uninstall
        blocks[index] = ours + ("\n" if old.endswith("\n\n") else "")
    new = preamble + "".join(blocks)
    tail = previous.get("tail_newlines", len(text) - len(text.rstrip("\n")))
    if appended:
        new = new.rstrip("\n") + "\n" + "".join("\n" + section for section in appended)

    backup = reg.with_name(reg.name + BACKUP_SUFFIX)
    if not backup.exists():
        backup.write_bytes(original)
    copied, created = [], list(previous.get("dirs", []))
    for _, _, arch, dest in layout:
        for parent in reversed(dest.relative_to(pfx).parents[:-1]):
            if not (pfx / parent).exists():
                created.append(str(parent))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BIN_DIR / arch / DLL, dest)
        copied.append(str(dest.relative_to(pfx)))
    marker.write_text(json.dumps({"version": 1, "files": copied, "dirs": created, "replaced": replaced,
                                  "tail_newlines": tail}, indent=2))
    if new != text:
        _write_atomic(reg, new)


def uninstall(pfx):
    """Remove what install() added. Returns False when there was nothing to remove."""
    pfx = Path(pfx)
    reg = pfx / "system.reg"
    if not reg.is_file():
        return False
    if prefix_in_use(pfx):
        raise PrefixInUse("The game (or something else in its Wine prefix) is running; close it first")
    text = reg.read_bytes().decode("latin-1")
    layout = _layout(pfx, text)
    marker = _marker_path(layout)
    if not marker.is_file() and not is_installed(pfx):
        return False
    info = json.loads(marker.read_text()) if marker.is_file() else {}
    replaced = info.get("replaced", {})

    preamble, blocks = _blocks(text)
    ours = {key.lower(): (key, path) for key, path, _, _ in layout}
    kept = []
    for block in blocks:
        entry = ours.get(_block_key(block))
        if entry is None or (_block_value(block) or "").lower() != entry[1].lower():
            kept.append(block)
        elif entry[0] in replaced:
            kept.append(replaced[entry[0]])
    new = preamble + "".join(kept)
    # Dropping the last sections leaves the blank line that separated them
    new = new.rstrip("\n") + "\n" * info.get("tail_newlines", 1)
    if new != text:
        _write_atomic(reg, new)

    for rel in info.get("files", [str(f.relative_to(pfx)) for _, _, _, f in layout]):
        path = pfx / rel
        if path.is_file():
            path.unlink()
    marker.unlink(missing_ok=True)
    folders = info.get("dirs", [str(f.parent.relative_to(pfx)) for _, _, _, f in layout])
    for rel in sorted(folders, key=lambda d: d.count("/"), reverse=True):  # deepest first
        try:
            (pfx / rel).rmdir()  # only if empty
        except OSError:
            pass
    reg.with_name(reg.name + BACKUP_SUFFIX).unlink(missing_ok=True)
    return True
