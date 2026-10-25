import copy
import json
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from g502hub.effects import gsi
from g502hub.effects.gsi import GameState

FIXTURES = Path(__file__).parent / "fixtures" / "gsi"


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def post(port, path, payload):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=2) as r:
        return r.status


@pytest.fixture
def server():
    srv = gsi.GameStateServer(port=0)
    srv.start()
    assert srv.state == "running"
    yield srv
    srv.stop()


# ---------------------------------------------------------------- server

def test_server_receives_cs2_and_dota2(server):
    cs2 = fixture("cs2-live.json")
    assert post(server.port, "/cs2", cs2) == 200
    got = server.latest()
    assert got.game == "cs2" and got.data["player"]["state"]["health"] == 100
    # No path: identified by provider.appid
    assert post(server.port, "/", fixture("dota2-game.json")) == 200
    assert server.latest().game == "dota2"


def test_server_rejects_wrong_token(server):
    bad = fixture("cs2-live.json")
    bad["auth"]["token"] = "nope"
    with pytest.raises(urllib.error.HTTPError) as e:
        post(server.port, "/cs2", bad)
    assert e.value.code == 403
    assert server.latest() is None


def test_server_rejects_garbage(server):
    req = urllib.request.Request(f"http://127.0.0.1:{server.port}/cs2", data=b"{not json", method="POST")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=2)
    assert e.value.code == 400


def test_latest_goes_stale():
    srv = gsi.GameStateServer(port=0, stale_s=0.2)
    srv.start()
    try:
        post(srv.port, "/cs2", fixture("cs2-live.json"))
        assert srv.latest() is not None
        time.sleep(0.3)
        assert srv.latest() is None
    finally:
        srv.stop()


def test_port_in_use_is_an_error_not_an_exception():
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen()
    try:
        srv = gsi.GameStateServer(port=blocker.getsockname()[1])
        srv.start()
        assert srv.state == "error" and "port" in srv.error.lower()
        srv.stop()
        assert srv.state == "idle"
    finally:
        blocker.close()


def test_restart_after_stop(server):
    server.stop()
    assert server.state == "idle"
    server.start()
    assert server.state == "running"
    assert post(server.port, "/cs2", fixture("cs2-live.json")) == 200


# ---------------------------------------------------------------- Steam + cfg files

@pytest.fixture
def steam(tmp_path):
    """A fake Steam root with CS2 in the main library and Dota 2 in a second one."""
    root, other = tmp_path / "Steam", tmp_path / "games"
    for lib in (root, other):
        (lib / "steamapps/common").mkdir(parents=True)
    (root / "steamapps/libraryfolders.vdf").write_text(f'''"libraryfolders"
{{
    "0"
    {{
        "path"      "{root}"
        "apps" {{ "730" "123" }}
    }}
    "1"
    {{
        "path"      "{other}"
        "apps" {{ "570" "456" }}
    }}
}}
''')
    (root / "steamapps/appmanifest_730.acf").write_text(
        '"AppState"\n{\n    "appid" "730"\n    "name" "Counter-Strike 2"\n'
        '    "installdir" "Counter-Strike Global Offensive"\n}\n')
    (root / "steamapps/common/Counter-Strike Global Offensive/game/csgo").mkdir(parents=True)
    (other / "steamapps/appmanifest_570.acf").write_text(
        '"AppState"\n{\n    "appid" "570"\n    "name" "Dota 2"\n    "installdir" "dota 2 beta"\n}\n')
    (other / "steamapps/common/dota 2 beta/game/dota").mkdir(parents=True)
    return root, other


def test_libraries_and_games(steam):
    root, other = steam
    assert gsi.steam_libraries(root) == [root, other]
    games = gsi.installed_games(root)
    assert games == {"cs2": root / "steamapps/common/Counter-Strike Global Offensive",
                     "dota2": other / "steamapps/common/dota 2 beta"}
    paths = gsi.config_paths(root)
    assert paths["cs2"].as_posix().endswith("game/csgo/cfg/gamestate_integration_g502hub.cfg")
    assert paths["dota2"].as_posix().endswith(
        "game/dota/cfg/gamestate_integration/gamestate_integration_g502hub.cfg")


def test_install_and_uninstall(steam):
    root, _ = steam
    assert gsi.configs_installed(root) == {"cs2": False, "dota2": False}
    written = gsi.install_configs(port=41999, token="secret", root=root)
    assert len(written) == 2
    assert gsi.configs_installed(root) == {"cs2": True, "dota2": True}
    text = gsi.config_paths(root)["cs2"].read_text()
    assert '"uri"           "http://127.0.0.1:41999/cs2"' in text
    assert '"token"     "secret"' in text
    assert '"player_state"' in text and '"hero"' not in text
    assert '"hero"' in gsi.config_paths(root)["dota2"].read_text()
    assert gsi.install_configs(port=41999, token="secret", root=root) == written  # idempotent
    assert len(gsi.uninstall_configs(root)) == 2
    assert gsi.configs_installed(root) == {"cs2": False, "dota2": False}
    assert gsi.uninstall_configs(root) == []


def test_no_steam_is_fine(tmp_path):
    assert gsi.installed_games(tmp_path / "nothing") == {}
    assert gsi.install_configs(root=tmp_path / "nothing") == []


def test_config_is_valid_vdf_shape():
    text = gsi.config_text("dota2")
    assert text.count("{") == text.count("}") == 3
    for key in ("uri", "timeout", "buffer", "throttle", "heartbeat", "token"):
        assert f'"{key}"' in text


# ---------------------------------------------------------------- CS2 lighting

def cs2(**player_state):
    data = fixture("cs2-live.json")
    data["player"]["state"].update(player_state)
    return data


def state(data, game="cs2"):
    return GameState(game, data, time.monotonic())


def brightness(rgb):
    return max(rgb)


def test_cs2_none_outside_a_match():
    fx = gsi.Cs2Lighting()
    assert fx(None, 0) is None
    menu = fixture("cs2-live.json")
    del menu["map"], menu["round"]
    menu["player"]["activity"] = "menu"
    assert fx(state(menu), 0) is None
    assert fx(state(fixture("dota2-game.json"), "dota2"), 0) is None


def test_cs2_health_color_goes_green_to_red():
    fx = gsi.Cs2Lighting()
    full = fx(state(cs2(health=100)), 0)[1]
    half = fx(state(cs2(health=50)), 1)[1]
    low = fx(state(cs2(health=25)), 2)[1]
    assert full[1] > 0.9 and full[0] < 0.1
    assert half[0] > 0.9 and half[1] > 0.9 and half[2] < 0.1  # yellow
    assert low[0] > 0.9 and low[1] < 0.6


def test_cs2_team_color_on_dpi_lights():
    fx = gsi.Cs2Lighting()
    ct = fx(state(cs2()), 0)[0]
    t_side = fixture("cs2-live.json")
    t_side["player"]["team"] = "T"
    t = fx(state(t_side), 1)[0]
    assert ct[2] > ct[0] and t[0] > t[2]
    assert brightness(ct) < 0.6  # dimmed


def test_cs2_flashbang_white_and_decays():
    fx = gsi.Cs2Lighting()
    whites = []
    for i, flashed in enumerate((255, 180, 90, 0)):
        out = fx(state(cs2(flashed=flashed)), i * 0.1)
        whites.append(min(min(c) for c in out.values()))
    assert whites[0] > 0.99
    assert whites[0] > whites[1] > whites[2] > whites[3]


def test_cs2_burning_flickers_orange_on_logo():
    fx = gsi.Cs2Lighting()
    logos = [fx(state(cs2(burning=255)), t / 30)[1] for t in range(30)]
    assert all(c[0] >= c[1] >= c[2] for c in logos)  # orange-ish
    assert max(c[0] for c in logos) - min(c[0] for c in logos) > 0.2  # flickers


def test_cs2_dead_is_dim_red():
    fx = gsi.Cs2Lighting()
    out = fx(state(cs2(health=0)), 0)
    for c in out.values():
        assert c[0] > c[1] and c[0] > c[2] and brightness(c) < 0.5


def test_cs2_spectating_teammate_counts_as_dead():
    fx = gsi.Cs2Lighting()
    data = cs2(health=100, flashed=255)
    data["player"]["steamid"] = "76561198000000002"  # watching someone else
    out = fx(state(data), 0)
    for c in out.values():
        assert brightness(c) < 0.5 and c[1] < 0.05  # not their health, not their flash


def test_cs2_freezetime_breathes_team_color():
    fx = gsi.Cs2Lighting()
    data = cs2()
    data["round"]["phase"] = "freezetime"
    values = [fx(state(data), t / 10)[0] for t in range(31)]
    assert all(c[2] >= c[0] for c in values)  # CT blue
    assert max(map(brightness, values)) - min(map(brightness, values)) > 0.4


def test_cs2_kill_flash_then_fades():
    fx = gsi.Cs2Lighting()
    base = fx(state(cs2(round_kills=0)), 0.0)
    flash = fx(state(cs2(round_kills=1)), 0.05)
    after = fx(state(cs2(round_kills=1)), 1.0)
    assert min(flash[0]) > 0.6
    assert after == base


def test_cs2_bomb_pulse_speeds_up():
    fx = gsi.Cs2Lighting()
    data = cs2()
    data["round"]["bomb"] = "planted"

    def beeps(start, end):
        """Count rising edges of the DPI lights' red over [start, end) seconds at 30 fps."""
        count, prev = 0, None
        for i in range(int(start * 30), int(end * 30)):
            r = fx(state(data), i / 30)[0][0]
            if prev is not None and r > prev + 0.3:
                count += 1
            prev = r
        return count

    early = beeps(0, 6)
    beeps(6, 34)
    late = beeps(34, 40)
    assert early >= 3 and late > early * 2


def test_cs2_bomb_uses_exact_countdown_when_given():
    assert gsi.Cs2Lighting.bomb_period(40) > gsi.Cs2Lighting.bomb_period(5) > gsi.Cs2Lighting.bomb_period(0)
    fx = gsi.Cs2Lighting()
    data = cs2()
    data["round"]["bomb"] = "planted"
    data["phase_countdowns"] = {"phase": "bomb", "phase_ends_in": "2.0"}
    fx(state(data), 0)
    reds = [fx(state(data), i / 30)[0][0] for i in range(1, 30)]
    rises = sum(1 for a, b in zip(reds, reds[1:]) if b > a + 0.3)
    assert rises >= 3  # ~0.2 s beeps near the end


def test_cs2_bomb_exploded_flash_fades():
    fx = gsi.Cs2Lighting()
    data = cs2()
    data["round"]["phase"] = "over"
    data["round"]["bomb"] = "exploded"
    boom = fx(state(data), 0)
    later = fx(state(data), 4)
    assert min(boom[0]) > 0.25 and brightness(boom[0]) > 0.95
    assert brightness(later[0]) < 0.6


# ---------------------------------------------------------------- Dota 2 lighting

def dota(**hero):
    data = fixture("dota2-game.json")
    data["hero"].update(hero)
    return data


def test_dota_none_outside_a_game():
    fx = gsi.Dota2Lighting()
    data = fixture("dota2-game.json")
    data["map"]["game_state"] = "DOTA_GAMERULES_STATE_HERO_SELECTION"
    assert fx(state(data, "dota2"), 0) is None
    assert fx(None, 0) is None
    assert fx(state(fixture("cs2-live.json")), 0) is None


def test_dota_health_and_mana():
    fx = gsi.Dota2Lighting()
    full = fx(state(dota(health_percent=100, mana_percent=100), "dota2"), 0)
    empty = fx(state(dota(health_percent=30, mana_percent=0), "dota2"), 1)
    assert full[1][1] > 0.9 and full[1][0] < 0.1  # green logo
    assert empty[1][0] > empty[1][1]  # reddish logo
    assert full[0][2] > 0.9 and brightness(empty[0]) < 0.2  # mana on the DPI lights


def test_dota_dead_pulses_dim_red_until_respawn():
    fx = gsi.Dota2Lighting()
    data = dota(alive=False, respawn_seconds=30, health_percent=0)
    values = [fx(state(data, "dota2"), t / 10)[1] for t in range(20)]
    assert all(c[0] >= c[1] and brightness(c) < 0.3 for c in values)
    assert max(map(brightness, values)) - min(map(brightness, values)) > 0.05
    soon = fx(state(dota(alive=False, respawn_seconds=0.5, health_percent=0), "dota2"), 0.8)[1]
    assert soon[1] > soon[0]  # radiant green as the hero comes back


def test_dota_stunned_flickers():
    fx = gsi.Dota2Lighting()
    logos = [fx(state(dota(stunned=True), "dota2"), t / 30)[1] for t in range(30)]
    assert max(map(min, logos)) - min(map(min, logos)) > 0.15


def test_dota_kill_flash():
    fx = gsi.Dota2Lighting()
    data = fixture("dota2-game.json")
    base = fx(state(data, "dota2"), 0)
    more = copy.deepcopy(data)
    more["player"]["kills"] += 1
    flash = fx(state(more, "dota2"), 0.02)
    assert flash[0][0] > base[0][0] + 0.5
    assert fx(state(more, "dota2"), 2.0) == base
