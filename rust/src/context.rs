use crate::config;
use anyhow::{Context as _, Result};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    collections::{HashMap, HashSet},
    fs,
    path::PathBuf,
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
    },
    thread,
    time::{Duration, Instant},
};
use zbus::blocking::{Connection, Proxy};
use zbus::zvariant::OwnedValue;
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct Media {
    pub player: String,
    pub title: String,
    pub artist: String,
    pub album: String,
    pub url: String,
    pub status: String,
}
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct Game {
    pub appid: u32,
    pub name: String,
    pub pid: u32,
    pub art: Option<PathBuf>,
}
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct Context {
    pub app: String,
    pub title: String,
    pub pid: Option<u32>,
    pub game: Option<Game>,
    pub media: Vec<Media>,
    pub error: Option<String>,
}
pub fn root() -> Option<PathBuf> {
    [
        config::home().join(".local/share/Steam"),
        config::home().join(".steam/steam"),
        config::home().join(".steam/root"),
        config::home().join(".var/app/com.valvesoftware.Steam/.local/share/Steam"),
    ]
    .into_iter()
    .find(|p| p.join("steamapps").is_dir())
}
pub fn vdf_pairs(text: &str) -> Vec<(String, String)> {
    let mut tokens = vec![];
    let mut chars = text.chars();
    while let Some(c) = chars.next() {
        if c == '"' {
            let mut t = String::new();
            while let Some(c) = chars.next() {
                if c == '"' {
                    break;
                }
                if c == '\\' {
                    if let Some(n) = chars.next() {
                        t.push(n);
                    }
                } else {
                    t.push(c);
                }
            }
            tokens.push(t);
        }
    }
    tokens
        .windows(2)
        .map(|p| (p[0].clone(), p[1].clone()))
        .collect()
}
pub fn libraries() -> Vec<PathBuf> {
    let Some(root) = root() else {
        return vec![];
    };
    let mut list = vec![root.clone()];
    if let Ok(text) = fs::read_to_string(root.join("steamapps/libraryfolders.vdf")) {
        for (k, v) in vdf_pairs(&text) {
            if k == "path" {
                let p = PathBuf::from(v);
                if p.join("steamapps").is_dir() && !list.contains(&p) {
                    list.push(p);
                }
            }
        }
    }
    list
}
pub fn installed_games() -> Vec<Game> {
    let mut games = vec![];
    for lib in libraries() {
        if let Ok(entries) = fs::read_dir(lib.join("steamapps")) {
            for f in entries.flatten() {
                let p = f.path();
                let name = p.file_name().unwrap_or_default().to_string_lossy();
                if !name.starts_with("appmanifest_") || !name.ends_with(".acf") {
                    continue;
                }
                if let Ok(text) = fs::read_to_string(&p) {
                    let pairs = vdf_pairs(&text);
                    let id = pairs
                        .iter()
                        .find(|(k, _)| k == "appid")
                        .and_then(|(_, v)| v.parse().ok());
                    let name = pairs
                        .iter()
                        .find(|(k, _)| k == "name")
                        .map(|(_, v)| v.clone());
                    if let (Some(appid), Some(name)) = (id, name) {
                        if !is_tool(appid, &name) {
                            games.push(Game {
                                appid,
                                name,
                                pid: 0,
                                art: find_art(appid),
                            });
                        }
                    }
                }
            }
        }
    }
    games.sort_by_key(|g| g.name.to_lowercase());
    games.dedup_by_key(|g| g.appid);
    games
}
fn is_tool(id: u32, name: &str) -> bool {
    [
        228980, 1070560, 1391110, 1493710, 1628350, 1826330, 1887720, 2180100, 2230260, 2348590,
        2805730, 3658110,
    ]
    .contains(&id)
        || ["Proton", "Steam Linux Runtime", "Steamworks"]
            .iter()
            .any(|s| name.starts_with(s))
}
pub fn find_art(appid: u32) -> Option<PathBuf> {
    let r = root()?;
    let folder = r.join(format!("appcache/librarycache/{appid}"));
    for name in [
        "library_hero.jpg",
        "header.jpg",
        "library_header.jpg",
        "library_600x900.jpg",
    ] {
        let p = folder.join(name);
        if p.is_file() {
            return Some(p);
        }
        if let Ok(entries) = fs::read_dir(&folder) {
            for d in entries.flatten() {
                let p = d.path().join(name);
                if p.is_file() {
                    return Some(p);
                }
            }
        }
    }
    None
}
fn meta_string(meta: &HashMap<String, OwnedValue>, key: &str) -> String {
    meta.get(key)
        .and_then(|v| <&str>::try_from(v).ok())
        .unwrap_or("")
        .into()
}
fn media(bus: &Connection) -> Result<Vec<Media>> {
    let proxy = Proxy::new(
        bus,
        "org.freedesktop.DBus",
        "/org/freedesktop/DBus",
        "org.freedesktop.DBus",
    )?;
    let names: Vec<String> = proxy.call("ListNames", &())?;
    let mut list = vec![];
    for name in names
        .iter()
        .filter(|n| n.starts_with("org.mpris.MediaPlayer2."))
    {
        let result = (|| -> Result<Media> {
            let p = Proxy::new(
                bus,
                name.as_str(),
                "/org/mpris/MediaPlayer2",
                "org.mpris.MediaPlayer2.Player",
            )?;
            let meta: HashMap<String, OwnedValue> = p.get_property("Metadata")?;
            let status: String = p.get_property("PlaybackStatus")?;
            let artist = meta
                .get("xesam:artist")
                .and_then(|v| v.try_clone().ok())
                .and_then(|v| Vec::<String>::try_from(v).ok())
                .unwrap_or_default()
                .join(", ");
            Ok(Media {
                player: name.clone(),
                title: meta_string(&meta, "xesam:title"),
                artist,
                album: meta_string(&meta, "xesam:album"),
                url: meta_string(&meta, "xesam:url"),
                status,
            })
        })();
        if let Ok(m) = result {
            list.push(m);
        }
    }
    list.sort_by_key(|m| {
        if m.status == "Playing" {
            0
        } else if m.status == "Paused" {
            1
        } else {
            2
        }
    });
    Ok(list)
}
fn x11_window() -> Result<(String, String, Option<u32>)> {
    use x11rb::{
        connection::Connection as _,
        protocol::xproto::{AtomEnum, ConnectionExt},
    };
    let (c, screen) = x11rb::connect(None)?;
    let root = c.setup().roots[screen].root;
    let atom = |s: &[u8]| -> Result<u32> { Ok(c.intern_atom(false, s)?.reply()?.atom) };
    let prop = c
        .get_property(
            false,
            root,
            atom(b"_NET_ACTIVE_WINDOW")?,
            AtomEnum::WINDOW,
            0,
            1,
        )?
        .reply()?;
    let win = prop
        .value32()
        .and_then(|mut v| v.next())
        .context("No active window")?;
    let class = c
        .get_property(false, win, AtomEnum::WM_CLASS, AtomEnum::STRING, 0, 1024)?
        .reply()?
        .value;
    let app = class
        .split(|&b| b == 0)
        .filter(|p| !p.is_empty())
        .next_back()
        .map(|p| String::from_utf8_lossy(p).to_lowercase())
        .unwrap_or_default();
    let title = c
        .get_property(false, win, atom(b"_NET_WM_NAME")?, AtomEnum::ANY, 0, 4096)?
        .reply()?
        .value;
    let pid = c
        .get_property(false, win, atom(b"_NET_WM_PID")?, AtomEnum::CARDINAL, 0, 1)?
        .reply()?
        .value32()
        .and_then(|mut p| p.next());
    Ok((app, String::from_utf8_lossy(&title).into_owned(), pid))
}
struct ActiveWindow {
    state: Arc<Mutex<Context>>,
}
#[zbus::interface(name = "io.github.g502hub.Context")]
impl ActiveWindow {
    #[zbus(name = "ActiveWindow")]
    fn active_window(&self, app: &str, caption: &str, pid: &str) {
        let mut s = self.state.lock().unwrap();
        s.app = app.to_lowercase();
        s.title = caption.into();
        s.pid = pid.parse().ok();
    }
}
const KWIN_SCRIPT: &str = include_str!("../assets/activewindow.js");
fn start_kwin(bus: &Connection, state: Arc<Mutex<Context>>) -> Result<PathBuf> {
    bus.object_server().at("/Context", ActiveWindow { state })?;
    let proxy = Proxy::new(bus, "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting")?;
    let name = "g502hub-rust-activewindow";
    let loaded: bool = proxy.call("isScriptLoaded", &(name,))?;
    if loaded {
        let _: bool = proxy.call("unloadScript", &(name,))?;
    }
    let path = config::runtime()?.join("activewindow.js");
    fs::write(
        &path,
        KWIN_SCRIPT.replace(
            "%SERVICE%",
            bus.unique_name().context("No D-Bus name")?.as_str(),
        ),
    )?;
    let id: i32 = proxy.call("loadScript", &(path.to_string_lossy().as_ref(), name))?;
    anyhow::ensure!(id >= 0, "KWin refused script");
    let _: () = proxy.call("start", &())?;
    Ok(path)
}
pub struct Watcher {
    pub state: Arc<Mutex<Context>>,
    stop: Arc<AtomicBool>,
    thread: Option<thread::JoinHandle<()>>,
}
impl Default for Watcher {
    fn default() -> Self {
        Self::new()
    }
}
impl Watcher {
    pub fn new() -> Self {
        let state = Arc::new(Mutex::new(Context::default()));
        let stop = Arc::new(AtomicBool::new(false));
        let s = state.clone();
        let end = stop.clone();
        let thread = thread::spawn(move || {
            let bus = zbus::blocking::connection::Builder::session()
                .and_then(|b| b.method_timeout(Duration::from_secs(2)).build())
                .ok();
            let kde = std::env::var("XDG_CURRENT_DESKTOP")
                .unwrap_or_default()
                .to_lowercase()
                .contains("kde");
            let kwin = if kde {
                bus.as_ref().and_then(|b| start_kwin(b, s.clone()).ok())
            } else {
                None
            };
            let mut seen = HashMap::<u32, Option<u32>>::new();
            let mut games = HashMap::<u32, Game>::new();
            let mut scan = Instant::now() - Duration::from_secs(10);
            let mut scan_media = Instant::now() - Duration::from_secs(10);
            while !end.load(Ordering::Relaxed) {
                if kwin.is_none() {
                    if let Ok((app, title, pid)) = x11_window() {
                        let mut s = s.lock().unwrap();
                        s.app = app;
                        s.title = title;
                        s.pid = pid;
                    }
                }
                if scan.elapsed() >= Duration::from_secs(2) {
                    scan = Instant::now();
                    let mut pids = HashSet::new();
                    if let Ok(entries) = fs::read_dir("/proc") {
                        for e in entries.flatten() {
                            if let Some(pid) =
                                e.file_name().to_str().and_then(|p| p.parse::<u32>().ok())
                            {
                                pids.insert(pid);
                                seen.entry(pid).or_insert_with(|| {
                                    use std::os::unix::fs::MetadataExt;
                                    if fs::metadata(e.path()).ok()?.uid()
                                        != unsafe { libc::getuid() }
                                    {
                                        return None;
                                    }
                                    let bytes = fs::read(e.path().join("environ")).ok()?;
                                    let mut app = 0u64;
                                    let mut game = 0u64;
                                    for p in bytes.split(|&b| b == 0) {
                                        if let Some(v) = p.strip_prefix(b"SteamAppId=") {
                                            app = std::str::from_utf8(v).ok()?.parse().unwrap_or(0);
                                        }
                                        if let Some(v) = p.strip_prefix(b"SteamGameId=") {
                                            game =
                                                std::str::from_utf8(v).ok()?.parse().unwrap_or(0);
                                        }
                                    }
                                    let id = if app > 0 {
                                        app
                                    } else if game >= 1 << 32 {
                                        game >> 32
                                    } else {
                                        game
                                    };
                                    u32::try_from(id).ok().filter(|&n| n > 0)
                                });
                            }
                        }
                    }
                    seen.retain(|p, _| pids.contains(p));
                    if games.is_empty() {
                        games = installed_games()
                            .into_iter()
                            .map(|g| (g.appid, g))
                            .collect();
                    }
                    let focused = s.lock().unwrap().pid;
                    let mut running: Vec<_> = seen
                        .iter()
                        .filter_map(|(&pid, &id)| id.map(|id| (pid, id)))
                        .filter(|(_, id)| !is_tool(*id, games.get(id).map_or("", |g| &g.name)))
                        .collect();
                    running
                        .sort_by_key(|(pid, _)| (Some(*pid) != focused, std::cmp::Reverse(*pid)));
                    let game = running.first().map(|&(pid, appid)| {
                        let mut g = games.get(&appid).cloned().unwrap_or(Game {
                            appid,
                            name: format!("Steam {appid}"),
                            pid,
                            art: find_art(appid),
                        });
                        g.pid = pid;
                        g
                    });
                    s.lock().unwrap().game = game;
                }
                if scan_media.elapsed() >= Duration::from_secs(1) {
                    scan_media = Instant::now();
                    if let Some(b) = &bus {
                        if let Ok(media) = media(b) {
                            s.lock().unwrap().media = media;
                        }
                    }
                }
                for _ in 0..5 {
                    if end.load(Ordering::Relaxed) {
                        break;
                    }
                    thread::sleep(Duration::from_millis(100));
                }
            }
            if let Some(bus) = bus {
                if kwin.is_some() {
                    if let Ok(p) =
                        Proxy::new(&bus, "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting")
                    {
                        let _: zbus::Result<bool> =
                            p.call("unloadScript", &("g502hub-rust-activewindow",));
                    }
                }
            }
            if let Some(p) = kwin {
                let _ = fs::remove_file(p);
            }
        });
        Self {
            state,
            stop,
            thread: Some(thread),
        }
    }
    pub fn snapshot(&self) -> Context {
        self.state.lock().unwrap().clone()
    }
}
impl Drop for Watcher {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Relaxed);
        if let Some(t) = self.thread.take() {
            let _ = t.join();
        }
    }
}
pub fn matches(rule: &Value, ctx: &Context) -> bool {
    if !rule["enabled"].as_bool().unwrap_or(true) {
        return false;
    }
    let want = rule["value"].as_str().unwrap_or("").trim().to_lowercase();
    if want.is_empty() {
        return false;
    }
    match rule["trigger"].as_str().unwrap_or("") {
        "game" => ctx
            .game
            .as_ref()
            .is_some_and(|g| want == "any" || g.appid.to_string() == want),
        "app" => ctx.app.to_lowercase() == want,
        "title" => ctx.title.to_lowercase().contains(&want),
        "media" => ctx.media.iter().any(|m| {
            m.status == "Playing"
                && format!("{} {} {} {}", m.title, m.artist, m.album, m.url)
                    .to_lowercase()
                    .contains(&want)
        }),
        _ => false,
    }
}
pub fn install_gsi(remove: bool) -> Result<Vec<String>> {
    let mut list = vec![];
    for lib in libraries() {
        for (game, id, suffix, keys) in [
            (
                "cs2",
                730,
                "game/csgo/cfg",
                vec![
                    "provider",
                    "map",
                    "round",
                    "player_id",
                    "player_state",
                    "bomb",
                    "phase_countdowns",
                ],
            ),
            (
                "dota2",
                570,
                "game/dota/cfg/gamestate_integration",
                vec!["provider", "map", "player", "hero"],
            ),
        ] {
            let file = lib.join(format!("steamapps/appmanifest_{id}.acf"));
            if let Ok(text) = fs::read_to_string(file) {
                let pairs = vdf_pairs(&text);
                if let Some((_, dir)) = pairs.iter().find(|(k, _)| k == "installdir") {
                    let path = lib
                        .join("steamapps/common")
                        .join(dir)
                        .join(suffix)
                        .join("gamestate_integration_g502hub.cfg");
                    if remove {
                        if path.exists() {
                            fs::remove_file(&path)?;
                        }
                    } else {
                        fs::create_dir_all(path.parent().unwrap())?;
                        fs::write(
                            &path,
                            format!(
                                "\"G502 Hub\"\n{{\n \"uri\" \"http://127.0.0.1:41502/{game}\"\n \"timeout\" \"1.1\"\n \"buffer\" \"0.0\"\n \"throttle\" \"0.1\"\n \"heartbeat\" \"5.0\"\n \"auth\" {{ \"token\" \"g502hub\" }}\n \"data\" {{ {} }}\n}}\n",
                                keys.iter()
                                    .map(|k| format!("\"{k}\" \"1\""))
                                    .collect::<Vec<_>>()
                                    .join(" ")
                            ),
                        )?;
                    }
                    list.push(path.display().to_string());
                }
            }
        }
    }
    Ok(list)
}
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn rules() {
        let ctx = Context {
            title: "Video Player".into(),
            media: vec![Media {
                title: "One Piece".into(),
                status: "Playing".into(),
                ..Default::default()
            }],
            ..Default::default()
        };
        assert!(matches(&json!({"trigger":"title","value":"video"}), &ctx));
        assert!(matches(&json!({"trigger":"media","value":"piece"}), &ctx));
        assert!(!matches(
            &json!({"trigger":"media","value":"piece","enabled":false}),
            &ctx
        ));
    }
    #[test]
    fn vdf_handles_escapes() {
        assert!(vdf_pairs("\"path\" \"/a/b\"").contains(&("path".into(), "/a/b".into())));
    }
}
