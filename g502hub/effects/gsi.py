"""Valve Game State Integration (GSI) lighting for CS2 and Dota 2.

The games POST their state as JSON to the URI in a gamestate_integration_*.cfg
file (formats: developer.valvesoftware.com/wiki/Counter-Strike:_Global_Offensive_Game_State_Integration,
which CS2 still follows, reading game/csgo/cfg; Dota 2's community-documented
GSI, e.g. the dota2-gsi npm package and the dota-gsi crate). Dota 2 only reads
its cfg when launched with the -gamestateintegration launch option.
"""

import colorsys
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from math import cos, exp, pi, sin
from pathlib import Path

from .. import lightfx

PORT = 41502
TOKEN = "g502hub"
STALE_S = 10.0  # latest() returns None after this long without a POST
CFG_NAME = "gamestate_integration_g502hub.cfg"
APP_IDS = {"cs2": 730, "dota2": 570}
CFG_DIRS = {"cs2": "game/csgo/cfg", "dota2": "game/dota/cfg/gamestate_integration"}
DATA = {
    # player_state carries health/armor/flashed/burning/round_kills; bomb and
    # phase_countdowns are only sent while spectating but give the exact C4 timer
    "cs2": ["provider", "map", "round", "player_id", "player_state", "bomb", "phase_countdowns"],
    "dota2": ["provider", "map", "player", "hero"],
}
STEAM_ROOTS = [Path.home() / ".local/share/Steam", Path.home() / ".steam/steam",
               Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam"]


@dataclass(frozen=True)
class GameState:
    game: str  # "cs2" | "dota2"
    data: dict  # the raw JSON payload
    received_at: float  # time.monotonic()


def _game_of(path, data):
    name = path.strip("/").split("/")[0]
    if name in APP_IDS:
        return name
    appid = (data.get("provider") or {}).get("appid")
    return next((g for g, a in APP_IDS.items() if a == appid), None)


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        owner = self.server.owner
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except (ValueError, OSError):
            self._reply(400)
            return
        if not isinstance(data, dict) or (data.get("auth") or {}).get("token") != owner.token:
            self._reply(403)
            return
        game = _game_of(self.path, data)
        if game is None:
            self._reply(404)
            return
        owner._store(GameState(game, data, time.monotonic()))
        self._reply(200)

    def _reply(self, code):
        self.send_response(code)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


class GameStateServer:
    """Receives the games' POSTs on 127.0.0.1 in a background thread."""

    def __init__(self, port=PORT, token=TOKEN, stale_s=STALE_S):
        self.port = port  # the bound port once running (useful with port 0)
        self.token = token
        self.stale_s = stale_s
        self.state = "idle"
        self.error = None
        self._lock = threading.Lock()
        self._latest = None
        self._server = None
        self._thread = None

    def start(self):
        if self._server is not None:
            return
        try:
            server = ThreadingHTTPServer(("127.0.0.1", self.port), _Handler)
        except OSError as e:
            self.state, self.error = "error", f"Can't listen on port {self.port}: {e.strerror or e}"
            return
        server.owner = self
        server.daemon_threads = True
        self._server, self.port = server, server.server_address[1]
        self._thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2},
                                        name="gsi-server", daemon=True)
        self._thread.start()
        self.state, self.error = "running", None

    def stop(self):
        server, self._server = self._server, None
        if server is not None:
            try:
                server.shutdown()
                server.server_close()
            except OSError:
                pass
            self._thread.join(timeout=2)
        self.state = "idle"

    def _store(self, game_state):
        with self._lock:
            self._latest = game_state

    def latest(self):
        with self._lock:
            latest = self._latest
        if latest is None or time.monotonic() - latest.received_at > self.stale_s:
            return None
        return latest


# ---------------------------------------------------------------- Steam and cfg files

def _steam_root(root=None):
    if root is not None:
        return Path(root)
    return next((r for r in STEAM_ROOTS if (r / "steamapps").is_dir()), STEAM_ROOTS[0])


def steam_libraries(root=None):
    """Every Steam library folder, from libraryfolders.vdf (the Steam root first)."""
    root = _steam_root(root)
    found = [root]
    try:
        text = (root / "steamapps/libraryfolders.vdf").read_text(errors="replace")
    except OSError:
        text = ""
    for path in re.findall(r'"path"\s+"([^"]+)"', text):
        p = Path(path.replace("\\\\", "\\"))
        if p not in found:
            found.append(p)
    return [p for p in found if (p / "steamapps").is_dir()]


def installed_games(root=None):
    """{"cs2": game dir, "dota2": game dir} for the ones installed."""
    games = {}
    for library in steam_libraries(root):
        for game, appid in APP_IDS.items():
            manifest = library / f"steamapps/appmanifest_{appid}.acf"
            if game in games or not manifest.is_file():
                continue
            m = re.search(r'"installdir"\s+"([^"]+)"', manifest.read_text(errors="replace"))
            folder = library / "steamapps/common" / (m.group(1) if m else "")
            if m and folder.is_dir():
                games[game] = folder
    return games


def config_paths(root=None):
    return {game: folder / CFG_DIRS[game] / CFG_NAME for game, folder in installed_games(root).items()}


def config_text(game, port=PORT, token=TOKEN):
    data = "\n".join(f'        "{key}"{" " * (18 - len(key))}"1"' for key in DATA[game])
    return f'''"G502 Hub"
{{
    "uri"           "http://127.0.0.1:{port}/{game}"
    "timeout"       "1.1"
    "buffer"        "0.0"
    "throttle"      "0.1"
    "heartbeat"     "5.0"
    "auth"
    {{
        "token"     "{token}"
    }}
    "data"
    {{
{data}
    }}
}}
'''


def install_configs(port=PORT, token=TOKEN, root=None):
    written = []
    for game, path in config_paths(root).items():
        text = config_text(game, port, token)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if path.read_text() == text:
                written.append(path)
                continue
        except OSError:
            pass
        tmp = path.with_suffix(".tmp")
        tmp.write_text(text)
        os.replace(tmp, path)
        written.append(path)
    return written


def uninstall_configs(root=None):
    removed = []
    for path in config_paths(root).values():
        try:
            path.unlink()
            removed.append(path)
        except FileNotFoundError:
            pass
    return removed


def configs_installed(root=None):
    return {game: path.is_file() for game, path in config_paths(root).items()}


# ---------------------------------------------------------------- lighting

CT_BLUE = (0.25, 0.55, 1.0)
T_GOLD = (1.0, 0.6, 0.1)
RED = (1.0, 0.0, 0.0)
WHITE = (1.0, 1.0, 1.0)
FIRE = (1.0, 0.32, 0.0)
DEAD = (0.22, 0.0, 0.0)
MANA = (0.15, 0.4, 1.0)
GOLD = (1.0, 0.78, 0.2)
RADIANT = (0.2, 0.9, 0.35)
DIRE = (0.9, 0.22, 0.12)
BOMB_S = 40.0  # CS2 C4 timer


def health_color(fraction):
    """Green at full health, yellow at half, red when nearly dead."""
    f = min(max(fraction, 0.0), 1.0)
    return colorsys.hsv_to_rgb(0.33 * f, 1.0, 1.0)


def _mix(a, b, f):
    f = min(max(f, 0.0), 1.0)
    return tuple(x + (y - x) * f for x, y in zip(a, b))


def _breathe(t, period):
    return (1 - cos(2 * pi * t / period)) / 2


def _flicker(t):
    """A fire-like, deterministic flicker in 0..1."""
    return 0.55 + 0.45 * sin(t * 31.0) * sin(t * 17.3 + 1.0)


class Cs2Lighting:
    """Logo: health. DPI lights: team color. Overlays for freezetime, bomb, kills, fire and flashes."""

    def __init__(self):
        self._last_t = None
        self._planted_at = None
        self._bomb_phase = 0.0
        self._bomb_state = None
        self._bomb_changed_at = 0.0
        self._kills = None
        self._kill_at = None

    def __call__(self, state, t):
        dt = 0.0 if self._last_t is None else max(0.0, t - self._last_t)
        self._last_t = t
        d = state.data if state is not None and state.game == "cs2" else None
        player = (d or {}).get("player") or {}
        if d is None or "map" not in d or player.get("activity") == "menu" or "state" not in player:
            self._planted_at, self._bomb_state, self._kills = None, None, None
            return None
        rnd = d.get("round") or {}
        ps = player["state"]
        team = CT_BLUE if player.get("team") == "CT" else T_GOLD
        me = (d.get("provider") or {}).get("steamid")
        spectating = me is not None and player.get("steamid") not in (None, me)
        health = ps.get("health", 100)
        phase = rnd.get("phase")

        if spectating or (health <= 0 and phase == "live"):
            dead = _mix(DEAD, (0.4, 0.0, 0.0), _breathe(t, 3.0))
            out = {0: dead, 1: dead}
        elif phase == "freezetime":
            glow = lightfx.scale(team, 0.25 + 0.55 * _breathe(t, 3.0))
            out = {0: glow, 1: glow}
        else:
            logo = health_color(health / 100)
            if 0 < health <= 20:
                logo = lightfx.scale(logo, 0.5 + 0.5 * _breathe(t, 0.8))
            out = {0: lightfx.scale(team, 0.45), 1: logo}

        out = self._bomb(out, rnd, d, t, dt)
        if not spectating and ps.get("burning", 0) > 0:
            out[1] = _mix(out[1], lightfx.scale(FIRE, _flicker(t)), ps["burning"] / 255)
        out = self._kill_flash(out, ps.get("round_kills", 0) if not spectating else None, team, t)
        flashed = ps.get("flashed", 0) if not spectating else 0
        if flashed > 0:
            amount = flashed / 255
            out = {z: _mix(c, WHITE, amount) for z, c in out.items()}
        return out

    @staticmethod
    def bomb_period(remaining):
        """Seconds per beep: slow at plant, frantic in the last seconds."""
        f = min(max(remaining / BOMB_S, 0.0), 1.0)
        return 0.12 + 0.9 * f ** 1.5

    def _bomb(self, out, rnd, d, t, dt):
        bomb = rnd.get("bomb")
        if bomb != self._bomb_state:
            self._bomb_state, self._bomb_changed_at = bomb, t
            self._planted_at = t if bomb == "planted" else None
            self._bomb_phase = 0.0
        if bomb == "planted":
            countdown = d.get("phase_countdowns") or {}
            if countdown.get("phase") == "bomb" and countdown.get("phase_ends_in") is not None:
                remaining = float(countdown["phase_ends_in"])
            else:
                remaining = BOMB_S - (t - self._planted_at)
            self._bomb_phase += dt / self.bomb_period(remaining)
            beep = exp(-((self._bomb_phase % 1.0) * 6.0))  # sharp attack, quick decay
            out[0] = lightfx.scale(RED, 0.15 + 0.85 * beep)
            out[1] = _mix(out[1], RED, 0.5 * beep)
        elif bomb == "exploded":
            boom = exp(-(t - self._bomb_changed_at) / 0.8)
            out = {z: _mix(c, (1.0, 0.75, 0.3), boom) for z, c in out.items()}
        elif bomb == "defused":
            out[0] = _mix(out[0], CT_BLUE, exp(-(t - self._bomb_changed_at) / 1.5))
        return out

    def _kill_flash(self, out, kills, team, t):
        if kills is None:
            return out
        if self._kills is not None and kills > self._kills:
            self._kill_at = t
        self._kills = kills
        if self._kill_at is not None:
            f = exp(-(t - self._kill_at) / 0.12)
            if f < 0.01:
                self._kill_at = None
            else:
                out = {0: _mix(out[0], WHITE, f), 1: _mix(out[1], _mix(team, WHITE, 0.6), f)}
        return out


class Dota2Lighting:
    """Logo: hero health. DPI lights: mana. Dead: dim red pulse until respawn."""

    IN_GAME = {"DOTA_GAMERULES_STATE_PRE_GAME", "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS"}

    def __init__(self):
        self._kills = None
        self._kill_at = None

    def __call__(self, state, t):
        d = state.data if state is not None and state.game == "dota2" else None
        hero = (d or {}).get("hero") or {}
        game_state = ((d or {}).get("map") or {}).get("game_state")
        if d is None or game_state not in self.IN_GAME or "health_percent" not in hero:
            self._kills = None
            return None
        player = d.get("player") or {}
        team = RADIANT if player.get("team_name") == "radiant" else DIRE

        if (d.get("map") or {}).get("paused"):
            out = {0: lightfx.scale(team, 0.3), 1: lightfx.scale(team, 0.3)}
        elif not hero.get("alive", True):
            respawn = float(hero.get("respawn_seconds") or 0)
            soon = 1 - min(respawn, 5.0) / 5.0  # fades toward the team color in the last 5 s
            period = 1.6 - 1.0 * soon
            pulse = _breathe(t, period)
            color = _mix(DEAD, lightfx.scale(team, 0.8), soon)
            out = {0: lightfx.scale(color, 0.4 + 0.6 * pulse), 1: lightfx.scale(color, 0.4 + 0.6 * pulse)}
        elif game_state == "DOTA_GAMERULES_STATE_PRE_GAME":
            glow = lightfx.scale(team, 0.3 + 0.5 * _breathe(t, 3.0))
            out = {0: glow, 1: glow}
        else:
            health = hero["health_percent"] / 100
            logo = health_color(health)
            if health <= 0.25:
                logo = lightfx.scale(logo, 0.45 + 0.55 * _breathe(t, 0.7))
            mana = hero.get("mana_percent", 0) / 100
            out = {0: lightfx.scale(MANA, 0.12 + 0.88 * mana), 1: logo}
            if hero.get("silenced"):
                out[0] = _mix(out[0], (0.6, 0.1, 0.9), 0.6)
            if hero.get("stunned") or hero.get("hexed"):
                out[1] = _mix(out[1], WHITE, 0.25 + 0.5 * _flicker(t * 1.6))

        kills = player.get("kills")
        if kills is not None:
            if self._kills is not None and kills > self._kills:
                self._kill_at = t
            self._kills = kills
        if self._kill_at is not None:
            f = exp(-(t - self._kill_at) / 0.25)
            if f < 0.01:
                self._kill_at = None
            else:
                out = {z: _mix(c, GOLD, f) for z, c in out.items()}
        return out
