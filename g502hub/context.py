"""What the user is doing: the active window, playing media and running Steam games.

Three sources, each allowed to fail on its own (see ContextWatcher.errors):
- the active window, from a small KWin script that calls us over D-Bus;
- media players, over MPRIS, followed by signals rather than polling;
- Steam games, from the SteamAppId in their processes' environment.
"""

import asyncio
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

KWIN_SCRIPT = Path(__file__).with_name("kwin") / "activewindow.js"
KWIN_PLUGIN = "g502hub-activewindow"
CONTEXT_IFACE = "io.github.g502hub.Context"
MPRIS_PREFIX = "org.mpris.MediaPlayer2."
STEAM_SCAN_S = 2.0
# Steam's own runtimes, run with a SteamAppId of their own
STEAM_TOOLS = {228980, 1070560, 1391110, 1493710, 1628350, 1826330, 1887720, 2180100, 2230260,
               2348590, 2805730, 3658110}
TOOL_PREFIXES = ("Proton", "Steam Linux Runtime", "Steamworks")
ART_NAMES = ("library_hero.jpg", "header.jpg", "library_header.jpg", "library_600x900.jpg",
             "library_capsule.jpg")


@dataclass(frozen=True)
class Media:
    player: str
    identity: str
    title: str
    artist: str
    album: str
    url: str
    status: str


@dataclass(frozen=True)
class Game:
    appid: int
    name: str
    pid: int
    art: str | None


@dataclass(frozen=True)
class Context:
    app: str
    title: str
    pid: int | None
    game: Game | None
    media: tuple[Media, ...]


# ------------------------------------------------------------ Steam files

def parse_vdf(text):
    """Valve's text KeyValues format (libraryfolders.vdf, appmanifest_*.acf) as nested dicts."""
    tokens = re.findall(r'"((?:[^"\\]|\\.)*)"|([{}])', text)
    root, stack, key = {}, [], None
    node = root
    for quoted, brace in tokens:
        if brace == "{":
            child = {}
            node[key] = child
            stack.append(node)
            node, key = child, None
        elif brace == "}":
            node = stack.pop() if stack else root
        elif key is None:
            key = quoted.replace('\\"', '"').replace("\\\\", "\\")
        else:
            node[key] = quoted.replace('\\"', '"').replace("\\\\", "\\")
            key = None
    return root


def steam_root(home=None):
    home = Path(home or Path.home())
    for candidate in (home / ".local/share/Steam", home / ".steam/steam", home / ".steam/root"):
        if (candidate / "steamapps").is_dir():
            return candidate.resolve()
    return None


def library_paths(root):
    """Every Steam library folder, the main one first."""
    if root is None:
        return []
    paths = [Path(root)]
    try:
        folders = parse_vdf((Path(root) / "steamapps/libraryfolders.vdf").read_text(errors="replace"))
    except OSError:
        return paths
    for entry in folders.get("libraryfolders", {}).values():
        if isinstance(entry, dict) and entry.get("path"):
            p = Path(entry["path"])
            if p.resolve() not in [q.resolve() for q in paths]:
                paths.append(p)
    return paths


def app_name(appid, libraries):
    """The installed game's name from its appmanifest, or None."""
    for lib in libraries:
        try:
            text = (Path(lib) / f"steamapps/appmanifest_{appid}.acf").read_text(errors="replace")
        except OSError:
            continue
        name = parse_vdf(text).get("AppState", {}).get("name")
        if name:
            return name
    return None


def is_tool(appid, name):
    return appid in STEAM_TOOLS or bool(name and name.startswith(TOOL_PREFIXES))


def installed_games(root=None):
    """(appid, name) of every installed Steam game, sorted by name, tools left out."""
    root = steam_root() if root is None else root
    found = {}
    for lib in library_paths(root):
        for manifest in (Path(lib) / "steamapps").glob("appmanifest_*.acf"):
            try:
                app = parse_vdf(manifest.read_text(errors="replace")).get("AppState", {})
                appid = int(app.get("appid") or manifest.stem.split("_", 1)[1])
            except (OSError, ValueError):
                continue
            name = app.get("name")
            if name and not is_tool(appid, name):
                found[appid] = name
    return sorted(found.items(), key=lambda item: item[1].lower())


def shortcut_names(root):
    """Names of non-Steam games added to Steam, from each user's binary shortcuts.vdf."""
    names = {}
    if root is None:
        return names
    for path in (Path(root) / "userdata").glob("*/config/shortcuts.vdf"):
        try:
            names.update(parse_shortcuts(path.read_bytes()))
        except OSError:
            pass
    return names


def parse_shortcuts(data):
    """{shortcut appid: name} from binary shortcuts.vdf.

    Each entry has an int field "appid" (type byte 0x02, uint32) followed by a
    string field "AppName" (type byte 0x01), the order modern Steam writes.
    """
    out = {}
    starts = [m.start() for m in re.finditer(rb"\x02appid\x00", data, re.I)]
    for i, start in enumerate(starts):
        chunk = data[start:starts[i + 1] if i + 1 < len(starts) else len(data)]
        name = re.search(rb"\x01appname\x00([^\x00]*)\x00", chunk, re.I)
        if name and len(chunk) >= 11:
            out[int.from_bytes(chunk[7:11], "little")] = name.group(1).decode(errors="replace")
    return out


def find_art(appid, root, shortcut=False):
    """The widest local cover image Steam has cached for a game, or None."""
    if root is None:
        return None
    if shortcut:
        for grid in sorted((Path(root) / "userdata").glob("*/config/grid")):
            for name in (f"{appid}_hero", f"{appid}", f"{appid}p"):
                for ext in (".png", ".jpg", ".jpeg", ".webp"):
                    if (grid / (name + ext)).is_file():
                        return str(grid / (name + ext))
        return None
    folder = Path(root) / "appcache/librarycache" / str(appid)
    flat = Path(root) / "appcache/librarycache"
    for name in ART_NAMES:
        for candidate in (folder / name, *sorted(folder.glob(f"*/{name}"))):
            if candidate.is_file():
                return str(candidate)
    # Older Steam clients kept flat files named <appid>_<kind>.jpg
    for kind in ("library_hero", "header", "library_600x900"):
        if (flat / f"{appid}_{kind}.jpg").is_file():
            return str(flat / f"{appid}_{kind}.jpg")
    return None


# ------------------------------------------------------------ processes

def parse_environ(data):
    """(appid, is_shortcut) from a /proc/<pid>/environ blob, or None for non-Steam processes."""
    env = {}
    for item in data.split(b"\0"):
        key, sep, value = item.partition(b"=")
        if sep and key in (b"SteamAppId", b"SteamGameId"):
            env[key] = value
    try:
        appid = int(env.get(b"SteamAppId", b"0") or 0)
        gameid = int(env.get(b"SteamGameId", b"0") or 0)
    except ValueError:
        return None
    if appid > 0:
        return appid, False
    if gameid >= 1 << 32:  # a non-Steam shortcut: the shortcut id sits in the top 32 bits
        return gameid >> 32, True
    if gameid > 0:
        return gameid, False
    return None


def start_time(proc, pid):
    """Process start time in clock ticks since boot (field 22 of /proc/<pid>/stat)."""
    try:
        stat = (Path(proc) / str(pid) / "stat").read_text()
        return int(stat.rpartition(")")[2].split()[19])
    except (OSError, ValueError, IndexError):
        return 0


class SteamScanner:
    """Finds running Steam games by reading the environment of new processes only."""

    def __init__(self, proc="/proc", root=None, uid=None):
        self.proc = Path(proc)
        self.root = root
        self.uid = os.getuid() if uid is None else uid
        self._seen = {}  # pid -> (appid, is_shortcut) or None
        self._names = {}
        self._art = {}

    def scan(self):
        """{(appid, is_shortcut): [(start time, pid), ...] oldest first} of running games."""
        try:
            pids = {int(p.name) for p in self.proc.iterdir() if p.name.isdigit()}
        except OSError:
            return {}
        for gone in set(self._seen) - pids:
            del self._seen[gone]
        for pid in pids - set(self._seen):
            self._seen[pid] = self._read(pid)
        games = {}
        for pid, found in self._seen.items():
            if found is not None and not self._skip(*found):
                games.setdefault(found, []).append((start_time(self.proc, pid), pid))
        return {key: sorted(procs) for key, procs in games.items()}

    def _read(self, pid):
        path = self.proc / str(pid)
        try:
            if path.stat().st_uid != self.uid:
                return None
            return parse_environ((path / "environ").read_bytes())
        except OSError:  # gone, or not ours
            return None

    def _skip(self, appid, shortcut):
        return not shortcut and is_tool(appid, self.name(appid, shortcut))

    def name(self, appid, shortcut=False):
        key = (appid, shortcut)
        if self._names.get(key) is None:
            if shortcut:
                name = shortcut_names(self.root).get(appid)
            else:
                name = app_name(appid, library_paths(self.root))
            self._names[key] = name
        return self._names[key]

    def art(self, appid, shortcut=False):
        key = (appid, shortcut)
        if key not in self._art:
            self._art[key] = find_art(appid, self.root, shortcut)
        return self._art[key]

    def games(self, focused_pid=None, focused_app=""):
        return pick_games(self.scan(), self, focused_pid, focused_app)


def pick_games(running, scanner, focused_pid=None, focused_app=""):
    """Game tuples for `running`, the focused one first, then the most recently started."""
    out = []
    for (appid, shortcut), procs in running.items():
        procs = sorted(procs)
        pids = {pid for _, pid in procs}
        focused = (focused_pid in pids) or (not shortcut and focused_app == f"steam_app_{appid}")
        pid = focused_pid if focused_pid in pids else procs[-1][1]
        name = scanner.name(appid, shortcut) or ("Non-Steam game" if shortcut else f"Steam app {appid}")
        game = Game(appid, name, pid, scanner.art(appid, shortcut))
        out.append((not focused, -procs[0][0], game))
    out.sort(key=lambda t: (t[0], t[1]))
    return [g for _, _, g in out]


def order_media(players):
    """Playing players first, then paused, then stopped; stable within each."""
    rank = {"Playing": 0, "Paused": 1}
    return tuple(sorted(players, key=lambda m: rank.get(m.status, 2)))


def media_from_props(player, identity, props):
    """A Media from an MPRIS Player's property dict (values already unwrapped)."""
    meta = props.get("Metadata") or {}

    def text(key):
        v = meta.get(key, "")
        if isinstance(v, (list, tuple)):
            return ", ".join(str(x) for x in v)
        return str(v) if v is not None else ""

    return Media(player, identity or "", text("xesam:title"), text("xesam:artist"), text("xesam:album"),
                 text("xesam:url"), str(props.get("PlaybackStatus") or "Stopped"))


def kwin_script_source(service):
    return KWIN_SCRIPT.read_text().replace("%SERVICE%", service)


# ------------------------------------------------------------ D-Bus

def _unwrap(value):
    from dbus_fast import Variant
    if isinstance(value, Variant):
        return _unwrap(value.value)
    if isinstance(value, dict):
        return {k: _unwrap(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_unwrap(v) for v in value]
    return value


def _context_interface(on_window):
    from dbus_fast.service import ServiceInterface, method

    class ContextInterface(ServiceInterface):
        def __init__(self):
            super().__init__(CONTEXT_IFACE)

        @method()
        def ActiveWindow(self, app: "s", caption: "s", pid: "s"):  # noqa: F821 (D-Bus signatures)
            on_window(app, caption, pid)

    return ContextInterface()


class ContextWatcher:
    """Collects the context in background threads; current() is a cheap snapshot."""

    def __init__(self, proc="/proc", steam=None):
        self.errors = {}
        self._lock = threading.Lock()
        self._window = ("", "", None)
        self._players = {}  # bus name -> Media
        self._running = {}  # SteamScanner.scan() result
        self._scanner = SteamScanner(proc, steam_root() if steam is None else steam)
        self._loop = None
        self._stop_async = None
        self._stop = threading.Event()
        self._threads = []
        self._script_path = None

    # ------------------------------------------------------------ API

    def start(self):
        if self._threads:
            return
        self._stop.clear()
        for target in (self._dbus_thread, self._steam_thread):
            t = threading.Thread(target=target, daemon=True, name=f"g502hub-{target.__name__}")
            t.start()
            self._threads.append(t)

    def stop(self):
        self._stop.set()
        loop, stop = self._loop, self._stop_async
        if loop is not None and stop is not None:
            try:
                loop.call_soon_threadsafe(stop.set)
            except RuntimeError:  # loop already closed
                pass
        for t in self._threads:
            t.join(timeout=2.5)
        self._threads = []

    def current(self):
        with self._lock:
            app, title, pid = self._window
            players = list(self._players.values())
            running = dict(self._running)
        games = pick_games(running, self._scanner, pid, app) if running else []
        return Context(app, title, pid, games[0] if games else None, order_media(players))

    def _error(self, source, message):
        with self._lock:
            if message is None:
                self.errors.pop(source, None)
            else:
                self.errors[source] = str(message)

    # ------------------------------------------------------------ Steam

    def _steam_thread(self):
        while not self._stop.is_set():
            try:
                running = self._scanner.scan()
                with self._lock:
                    self._running = running
                self._error("steam", None)
            except Exception as e:  # keep scanning; report why
                self._error("steam", f"{type(e).__name__}: {e}")
            self._stop.wait(STEAM_SCAN_S)

    # ------------------------------------------------------------ D-Bus

    def _dbus_thread(self):
        loop = asyncio.new_event_loop()
        self._loop = loop
        try:
            loop.run_until_complete(self._dbus_main())
        except Exception as e:
            self._error("dbus", f"{type(e).__name__}: {e}")
        finally:
            self._loop = None
            loop.close()

    async def _dbus_main(self):
        from dbus_fast.aio import MessageBus

        self._stop_async = asyncio.Event()
        if self._stop.is_set():
            return
        bus = await MessageBus().connect()
        try:
            try:
                await self._start_mpris(bus)
            except Exception as e:
                self._error("mpris", f"{type(e).__name__}: {e}")
            try:
                await self._start_kwin(bus)
            except Exception as e:
                self._error("kwin", f"{type(e).__name__}: {e}")
            if not self._stop.is_set():
                await self._stop_async.wait()
        finally:
            try:
                await asyncio.wait_for(self._stop_kwin(bus), 1.5)
            except Exception:
                pass
            bus.disconnect()

    @staticmethod
    async def _call(bus, dest, path, iface, member, signature="", body=()):
        from dbus_fast import Message, MessageType
        reply = await bus.call(Message(destination=dest, path=path, interface=iface, member=member,
                                       signature=signature, body=list(body)))
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError(f"{reply.error_name}: {reply.body[0] if reply.body else ''}")
        return reply.body

    # ---- KWin

    async def _start_kwin(self, bus):
        def on_window(app, caption, pid):
            with self._lock:
                self._window = (app.lower(), caption, int(pid) if pid.isdigit() else None)

        bus.export("/Context", _context_interface(on_window))
        runtime = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp")
        self._script_path = runtime / f"g502hub-activewindow-{os.getpid()}.js"
        self._script_path.write_text(kwin_script_source(bus.unique_name))
        kwin = ("org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting")
        loaded = await self._call(bus, *kwin, "isScriptLoaded", "s", [KWIN_PLUGIN])
        if loaded and loaded[0]:  # left over from a run that didn't shut down
            await self._call(bus, *kwin, "unloadScript", "s", [KWIN_PLUGIN])
        script_id = await self._call(bus, *kwin, "loadScript", "ss", [str(self._script_path), KWIN_PLUGIN])
        if not script_id or script_id[0] < 0:
            raise RuntimeError("KWin refused to load the active-window script")
        await self._call(bus, *kwin, "start")
        self._error("kwin", None)

    async def _stop_kwin(self, bus):
        try:
            await self._call(bus, "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting",
                             "unloadScript", "s", [KWIN_PLUGIN])
        finally:
            if self._script_path is not None:
                self._script_path.unlink(missing_ok=True)

    # ---- MPRIS

    async def _start_mpris(self, bus):
        from dbus_fast import MessageType

        owners = {}  # unique name -> well-known MPRIS name
        props = {}   # well-known name -> Player property dict
        identities = {}
        dbus = ("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus")

        def publish(name):
            with self._lock:
                if name in props:
                    self._players[name] = media_from_props(name[len(MPRIS_PREFIX):], identities.get(name),
                                                           props[name])
                else:
                    self._players.pop(name, None)

        async def add(name):
            try:
                owner = (await self._call(bus, *dbus, "GetNameOwner", "s", [name]))[0]
                path = "/org/mpris/MediaPlayer2"
                ident = await self._call(bus, name, path, "org.freedesktop.DBus.Properties", "Get", "ss",
                                         ["org.mpris.MediaPlayer2", "Identity"])
                player = await self._call(bus, name, path, "org.freedesktop.DBus.Properties", "GetAll", "s",
                                          ["org.mpris.MediaPlayer2.Player"])
            except Exception:
                return  # it went away, or isn't a well-behaved player
            owners[owner] = name
            identities[name] = str(_unwrap(ident[0])) if ident else ""
            props[name] = _unwrap(player[0]) if player else {}
            publish(name)

        def remove(name):
            props.pop(name, None)
            identities.pop(name, None)
            for unique, wk in list(owners.items()):
                if wk == name:
                    del owners[unique]
            publish(name)

        def on_message(msg):
            if msg.message_type != MessageType.SIGNAL:
                return None
            if msg.member == "NameOwnerChanged" and msg.interface == "org.freedesktop.DBus":
                name, _, new = msg.body
                if name.startswith(MPRIS_PREFIX):
                    remove(name)
                    if new:
                        asyncio.ensure_future(add(name))
            elif msg.member == "PropertiesChanged" and msg.path == "/org/mpris/MediaPlayer2":
                iface, changed, invalidated = msg.body
                name = owners.get(msg.sender)
                if name is None or iface != "org.mpris.MediaPlayer2.Player":
                    return None
                props.setdefault(name, {}).update(_unwrap(changed))
                if invalidated:
                    asyncio.ensure_future(add(name))
                else:
                    publish(name)
            return None

        bus.add_message_handler(on_message)
        for rule in ("type='signal',interface='org.freedesktop.DBus.Properties',member='PropertiesChanged',"
                     "path='/org/mpris/MediaPlayer2'",
                     "type='signal',sender='org.freedesktop.DBus',interface='org.freedesktop.DBus',"
                     "member='NameOwnerChanged',arg0namespace='org.mpris.MediaPlayer2'"):
            await self._call(bus, *dbus, "AddMatch", "s", [rule])
        names = (await self._call(bus, *dbus, "ListNames"))[0]
        for name in names:
            if name.startswith(MPRIS_PREFIX):
                await add(name)
        self._error("mpris", None)
