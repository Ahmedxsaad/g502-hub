import os
from pathlib import Path

import pytest

from g502hub import context
from g502hub.context import Media

STEAM = Path.home() / ".local/share/Steam"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text)


def manifest(appid, name):
    return f'"AppState"\n{{\n\t"appid"\t\t"{appid}"\n\t"name"\t\t"{name}"\n}}\n'


def fake_steam(tmp_path, extra_library=None):
    root = tmp_path / "Steam"
    libs = f'\t"0"\n\t{{\n\t\t"path"\t\t"{root}"\n\t}}\n'
    if extra_library:
        libs += f'\t"1"\n\t{{\n\t\t"path"\t\t"{extra_library}"\n\t}}\n'
    write(root / "steamapps/libraryfolders.vdf", f'"libraryfolders"\n{{\n{libs}}}\n')
    return root


def fake_proc(root, pid, env, start=100):
    write(root / str(pid) / "environ", b"\0".join(f"{k}={v}".encode() for k, v in env.items()) + b"\0")
    fields = ["S"] + ["0"] * 18 + [str(start)] + ["0"] * 5
    write(root / str(pid) / "stat", f"{pid} (game.exe) " + " ".join(fields))


def test_parse_vdf_nested_and_escapes():
    data = context.parse_vdf('"a"\n{\n\t"b"\t"1"\n\t"c"\n\t{\n\t\t"d"\t"x \\"y\\""\n\t}\n\t"e"\t"2"\n}\n')
    assert data == {"a": {"b": "1", "c": {"d": 'x "y"'}, "e": "2"}}


def test_library_paths_and_app_name(tmp_path):
    other = tmp_path / "Games/SteamLibrary"
    root = fake_steam(tmp_path, extra_library=other)
    write(other / "steamapps/appmanifest_42.acf", manifest(42, "Some Game"))
    libs = context.library_paths(root)
    assert libs == [root, other]
    assert context.app_name(42, libs) == "Some Game"
    assert context.app_name(43, libs) is None


@pytest.mark.skipif(not (STEAM / "steamapps/appmanifest_291550.acf").exists(), reason="no local Steam install")
def test_real_steam_files():
    root = context.steam_root()
    assert root is not None
    assert context.app_name(291550, context.library_paths(root)) == "Brawlhalla"
    assert context.is_tool(1493710, context.app_name(1493710, context.library_paths(root)))


def test_is_tool():
    assert context.is_tool(1, "Proton 9.0")
    assert context.is_tool(1, "Steam Linux Runtime 3.0 (sniper)")
    assert context.is_tool(228980, None)
    assert not context.is_tool(291550, "Brawlhalla")


@pytest.mark.parametrize("env, expected", [
    ({"SteamAppId": "291550", "HOME": "/x"}, (291550, False)),
    ({"SteamGameId": "570"}, (570, False)),
    ({"SteamAppId": "0", "SteamGameId": str((3000000000 << 32) | 0x02000000)}, (3000000000, True)),
    ({"SteamAppId": "0"}, None),
    ({"HOME": "/x"}, None),
    ({"SteamAppId": "nope"}, None),
])
def test_parse_environ(env, expected):
    blob = b"\0".join(f"{k}={v}".encode() for k, v in env.items())
    assert context.parse_environ(blob) == expected


def test_scanner_finds_games_skips_tools_and_prunes(tmp_path):
    root = fake_steam(tmp_path)
    write(root / "steamapps/appmanifest_291550.acf", manifest(291550, "Brawlhalla"))
    write(root / "steamapps/appmanifest_1493710.acf", manifest(1493710, "Proton Experimental"))
    proc = tmp_path / "proc"
    fake_proc(proc, 10, {"SteamAppId": "291550"}, start=500)
    fake_proc(proc, 11, {"SteamAppId": "291550"}, start=600)
    fake_proc(proc, 12, {"SteamAppId": "1493710"})
    fake_proc(proc, 13, {"PATH": "/usr/bin"})
    (proc / "self").mkdir()
    scanner = context.SteamScanner(proc, root)
    assert scanner.scan() == {(291550, False): [(500, 10), (600, 11)]}
    games = scanner.games()
    assert [(g.appid, g.name, g.pid) for g in games] == [(291550, "Brawlhalla", 11)]
    for f in (proc / "10").iterdir():
        f.unlink()
    (proc / "10").rmdir()
    for f in (proc / "11").iterdir():
        f.unlink()
    (proc / "11").rmdir()
    assert scanner.scan() == {}


def test_scanner_ignores_other_users(tmp_path):
    proc = tmp_path / "proc"
    fake_proc(proc, 20, {"SteamAppId": "570"})
    scanner = context.SteamScanner(proc, None, uid=os.getuid() + 1)
    assert scanner.scan() == {}


class Names:
    def __init__(self, names):
        self.names = names

    def name(self, appid, shortcut=False):
        return self.names.get(appid)

    def art(self, appid, shortcut=False):
        return None


def test_pick_games_focus_then_newest():
    running = {(1, False): [(100, 5), (150, 6)], (2, False): [(300, 9)], (3, True): [(200, 7)]}
    names = Names({1: "Old", 2: "New"})
    assert [g.appid for g in context.pick_games(running, names)] == [2, 3, 1]
    focused = context.pick_games(running, names, focused_pid=5)
    assert focused[0].appid == 1 and focused[0].pid == 5
    by_class = context.pick_games(running, names, focused_app="steam_app_1")
    assert by_class[0].appid == 1
    assert next(g for g in by_class if g.appid == 3).name == "Non-Steam game"


def test_find_art_prefers_wide_images(tmp_path):
    root = tmp_path / "Steam"
    cache = root / "appcache/librarycache"
    write(cache / "7/library_600x900.jpg", b"x")
    write(cache / "7/abc123/library_header.jpg", b"x")
    assert context.find_art(7, root).endswith("abc123/library_header.jpg")
    write(cache / "7/header.jpg", b"x")
    assert context.find_art(7, root).endswith("7/header.jpg")
    write(cache / "7/library_hero.jpg", b"x")
    assert context.find_art(7, root).endswith("7/library_hero.jpg")
    write(cache / "8_header.jpg", b"x")
    assert context.find_art(8, root).endswith("8_header.jpg")
    assert context.find_art(9, root) is None
    write(root / "userdata/1/config/grid/55_hero.png", b"x")
    assert context.find_art(55, root, shortcut=True).endswith("55_hero.png")


def test_parse_shortcuts():
    def entry(index, appid, name):
        return (b"\x00" + index + b"\x00\x02appid\x00" + appid.to_bytes(4, "little") +
                b"\x01AppName\x00" + name + b"\x00\x01Exe\x00\"/x\"\x00\x08")
    data = b"\x00shortcuts\x00" + entry(b"0", 3000000000, b"Osu") + entry(b"1", 12345, b"Heroic") + b"\x08\x08"
    assert context.parse_shortcuts(data) == {3000000000: "Osu", 12345: "Heroic"}


def test_media_from_props_and_order():
    m = context.media_from_props("mpv", "mpv", {
        "PlaybackStatus": "Playing",
        "Metadata": {"xesam:title": "Frieren - 05", "xesam:artist": ["A", "B"], "xesam:url": "file:///x.mkv"}})
    assert (m.title, m.artist, m.album, m.url, m.status) == ("Frieren - 05", "A, B", "", "file:///x.mkv", "Playing")
    paused = Media("a", "", "", "", "", "", "Paused")
    stopped = Media("b", "", "", "", "", "", "Stopped")
    assert context.order_media([stopped, paused, m]) == (m, paused, stopped)
    assert context.media_from_props("x", None, {}).status == "Stopped"


def test_kwin_script_template():
    source = context.kwin_script_source(":1.234")
    assert '":1.234"' in source and "%SERVICE%" not in source
    for name in ("workspace.windowActivated", "workspace.activeWindow", "captionChanged", "callDBus",
                 "resourceClass", "ActiveWindow"):
        assert name in source


def test_watcher_snapshot_before_start(tmp_path):
    w = context.ContextWatcher(proc=tmp_path, steam=tmp_path)
    c = w.current()
    assert (c.app, c.title, c.pid, c.game, c.media) == ("", "", None, None, ())
    w.stop()  # stopping a watcher that never started is fine


def test_installed_games_lists_games_not_tools(tmp_path):
    apps = tmp_path / "steamapps"
    apps.mkdir()
    (apps / "appmanifest_291550.acf").write_text('"AppState"\n{\n\t"appid"\t\t"291550"\n\t"name"\t\t"Brawlhalla"\n}\n')
    (apps / "appmanifest_1493710.acf").write_text('"AppState"\n{\n\t"appid"\t\t"1493710"\n\t"name"\t\t"Proton Experimental"\n}\n')
    (apps / "appmanifest_70.acf").write_text('"AppState"\n{\n\t"appid"\t\t"70"\n\t"name"\t\t"Half-Life"\n}\n')
    assert context.installed_games(tmp_path) == [(291550, "Brawlhalla"), (70, "Half-Life")]
