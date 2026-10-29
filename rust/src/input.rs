use anyhow::{Context, Result, bail, ensure};
use serde_json::Value;
use std::{
    collections::HashMap,
    fs::{File, OpenOptions},
    io::Write,
    os::fd::AsRawFd,
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
    },
    thread,
    time::{Duration, Instant},
};
#[path = "keys.rs"]
pub mod keys;
#[derive(Debug, Clone, PartialEq)]
pub enum Event {
    Key(u16, bool),
    Rel(u16, i32),
    Wait(u64),
}
pub fn combo(text: &str) -> Result<(u8, u8)> {
    let mut mods = 0;
    let mut usage = 0;
    for item in text.trim().to_lowercase().split('+') {
        let m = match item.trim() {
            "ctrl" | "control" | "lctrl" => 1,
            "shift" | "lshift" => 2,
            "alt" | "lalt" => 4,
            "meta" | "super" | "win" | "gui" | "lsuper" => 8,
            "rctrl" => 16,
            "rshift" => 32,
            "ralt" | "altgr" => 64,
            "rmeta" | "rsuper" => 128,
            _ => 0,
        };
        if m != 0 {
            mods |= m;
        } else {
            ensure!(usage == 0, "More than one key in {text}");
            usage = if let Some(h) = item.strip_prefix("key-0x") {
                u8::from_str_radix(h, 16)?
            } else {
                keys::KEYS
                    .iter()
                    .find(|(name, _)| *name == item)
                    .context(format!("Unknown key {item}"))?
                    .1 as u8
            };
        }
    }
    ensure!(mods != 0 || usage != 0, "Empty key combination");
    Ok((mods, usage))
}
pub fn consumer(text: &str) -> Result<u16> {
    if let Some(h) = text.strip_prefix("consumer-0x") {
        Ok(u16::from_str_radix(h, 16)?)
    } else {
        Ok(keys::CONSUMER
            .iter()
            .find(|(n, _)| *n == text)
            .context("Unknown media key")?
            .1)
    }
}
pub fn evdev(usage: u16) -> Result<u16> {
    keys::HID_EVDEV
        .iter()
        .find(|(h, _)| *h == usage)
        .map(|(_, e)| *e)
        .context(format!("Unsupported HID key {usage}"))
}
pub fn media_evdev(usage: u16) -> Result<u16> {
    Ok(match usage {
        0xcd => 164,
        0xb5 => 163,
        0xb6 => 165,
        0xb7 => 166,
        0xe2 => 113,
        0xe9 => 115,
        0xea => 114,
        0x6f => 225,
        0x70 => 224,
        0x192 => 140,
        0x194 => 144,
        0x18a => 155,
        0x223 => 172,
        0x224 => 158,
        0x225 => 159,
        0x227 => 173,
        0x221 => 217,
        _ => bail!("Unsupported media usage {usage}"),
    })
}
pub fn binding(text: &str) -> Result<[u8; 4]> {
    let text = text.trim().to_lowercase();
    let (s, arg) = text.split_once(':').unwrap_or((&text, ""));
    if s == "key" {
        let (m, u) = combo(arg)?;
        return Ok([128, 2, m, u]);
    }
    if s == "media" {
        let [a, b] = consumer(arg)?.to_be_bytes();
        return Ok([128, 3, a, b]);
    }
    if s == "raw" {
        let b = crate::model::unhex(arg)?;
        ensure!(b.len() == 4, "Binding needs four bytes");
        return Ok(b.try_into().unwrap());
    }
    if let Some(i) = ["left", "right", "middle", "back", "forward"]
        .iter()
        .position(|&n| n == s)
    {
        let [a, b] = (1u16 << i).to_be_bytes();
        return Ok([128, 1, a, b]);
    }
    if s == "disabled" {
        return Ok([128, 0, 255, 255]);
    }
    if s == "unassigned" {
        return Ok([255; 4]);
    }
    if s == "profile-select" {
        let n = arg.parse::<u8>()?;
        ensure!((1..=5).contains(&n), "Profile slot must be 1–5");
        return Ok([144, 13, 255, n]);
    }
    if let Some(i) = SPECIAL.iter().position(|&n| n == s) {
        return Ok([144, i as u8, 255, 255]);
    }
    bail!("Unknown button action {text}")
}
pub const SPECIAL: &[&str] = &[
    "noop",
    "tilt-left",
    "tilt-right",
    "dpi-up",
    "dpi-down",
    "dpi-cycle",
    "dpi-default",
    "dpi-shift",
    "profile-next",
    "profile-prev",
    "profile-cycle",
    "gshift",
    "battery",
    "profile-select",
    "mode-switch",
    "host",
    "scroll-down",
    "scroll-up",
];
pub fn describe_binding(b: [u8; 4]) -> String {
    match b {
        [255, 255, 255, 255] => "unassigned".into(),
        [128, 0, _, _] => "disabled".into(),
        [128, 1, a, c] => {
            let mask = u16::from_be_bytes([a, c]);
            if mask.count_ones() == 1 && mask < 32 {
                ["left", "right", "middle", "back", "forward"][mask.trailing_zeros() as usize]
                    .into()
            } else {
                format!("raw:{}", crate::model::hex(&b))
            }
        }
        [128, 2, m, u] => {
            let mut s = vec![];
            for (bit, n) in [
                (1, "ctrl"),
                (2, "shift"),
                (4, "alt"),
                (8, "meta"),
                (16, "rctrl"),
                (32, "rshift"),
                (64, "altgr"),
                (128, "rmeta"),
            ] {
                if m & bit != 0 {
                    s.push(n.to_string());
                }
            }
            if u != 0 {
                s.push(
                    keys::KEYS
                        .iter()
                        .find(|(_, v)| *v == u as u16)
                        .map(|(n, _)| n.to_string())
                        .unwrap_or(format!("key-0x{u:02x}")),
                );
            }
            format!("key:{}", s.join("+"))
        }
        [128, 3, a, c] => {
            let u = u16::from_be_bytes([a, c]);
            format!(
                "media:{}",
                keys::CONSUMER
                    .iter()
                    .find(|(_, v)| *v == u)
                    .map(|(n, _)| n.to_string())
                    .unwrap_or(format!("consumer-0x{u:04X}"))
            )
        }
        [144, f, _, a] if (f as usize) < SPECIAL.len() => {
            if f == 13 {
                format!("profile-select:{a}")
            } else {
                SPECIAL[f as usize].into()
            }
        }
        _ => format!("raw:{}", crate::model::hex(&b)),
    }
}
#[repr(C)]
struct Names {
    rules: *const libc::c_char,
    model: *const libc::c_char,
    layout: *const libc::c_char,
    variant: *const libc::c_char,
    options: *const libc::c_char,
}
#[link(name = "xkbcommon")]
unsafe extern "C" {
    fn xkb_context_new(flags: u32) -> *mut libc::c_void;
    fn xkb_context_unref(p: *mut libc::c_void);
    fn xkb_keymap_new_from_names(
        ctx: *mut libc::c_void,
        n: *const Names,
        flags: u32,
    ) -> *mut libc::c_void;
    fn xkb_keymap_unref(p: *mut libc::c_void);
    fn xkb_state_new(keymap: *mut libc::c_void) -> *mut libc::c_void;
    fn xkb_state_unref(p: *mut libc::c_void);
    fn xkb_keymap_mod_get_index(p: *mut libc::c_void, name: *const libc::c_char) -> u32;
    fn xkb_state_update_mask(
        p: *mut libc::c_void,
        a: u32,
        b: u32,
        c: u32,
        d: u32,
        e: u32,
        f: u32,
    ) -> u32;
    fn xkb_state_key_get_utf8(
        p: *mut libc::c_void,
        key: u32,
        buffer: *mut libc::c_char,
        size: usize,
    ) -> libc::c_int;
}
pub fn layout() -> String {
    if let Ok(s) = std::env::var("G502_RUST_LAYOUT") {
        return s;
    }
    if let Ok(o) = std::process::Command::new("gsettings")
        .args(["get", "org.gnome.desktop.input-sources", "sources"])
        .output()
    {
        let s = String::from_utf8_lossy(&o.stdout);
        if let Some((_, tail)) = s.split_once("'xkb', '") {
            if let Some((name, _)) = tail.split_once('\'') {
                return name.into();
            }
        }
    }
    if let Ok(o) = std::process::Command::new("localectl")
        .arg("status")
        .output()
    {
        for line in String::from_utf8_lossy(&o.stdout).lines() {
            if let Some(s) = line.trim().strip_prefix("X11 Layout:") {
                return s.trim().split(',').next().unwrap_or("us").into();
            }
        }
    }
    "us".into()
}
pub fn typing_table(layout: &str) -> Result<HashMap<char, (u8, u16)>> {
    use std::ffi::CString;
    let (layout, variant) = layout.split_once('+').unwrap_or((layout, ""));
    let l = CString::new(layout)?;
    let variant = CString::new(variant)?;
    let mut table = HashMap::new();
    unsafe {
        let ctx = xkb_context_new(0);
        ensure!(!ctx.is_null(), "Cannot open keyboard map");
        let names = Names {
            rules: std::ptr::null(),
            model: std::ptr::null(),
            layout: l.as_ptr(),
            variant: if variant.as_bytes().is_empty() {
                std::ptr::null()
            } else {
                variant.as_ptr()
            },
            options: std::ptr::null(),
        };
        let map = xkb_keymap_new_from_names(ctx, &names, 0);
        if map.is_null() {
            xkb_context_unref(ctx);
            bail!("Unknown keyboard layout");
        }
        let shift = xkb_keymap_mod_get_index(map, c"Shift".as_ptr());
        let altgr = xkb_keymap_mod_get_index(map, c"Mod5".as_ptr());
        let mut levels = vec![(0, 0)];
        if shift < 32 {
            levels.push((2, 1 << shift));
        }
        if altgr < 32 {
            levels.push((64, 1 << altgr));
            if shift < 32 {
                levels.push((66, (1 << shift) | (1 << altgr)));
            }
        }
        for (m, mask) in levels {
            let state = xkb_state_new(map);
            if state.is_null() {
                continue;
            }
            xkb_state_update_mask(state, mask, 0, 0, 0, 0, 0);
            for &(_, code) in keys::HID_EVDEV {
                let mut buf = [0i8; 64];
                let n = xkb_state_key_get_utf8(state, code as u32 + 8, buf.as_mut_ptr(), buf.len());
                if n > 0 && (n as usize) < buf.len() {
                    let bytes = std::slice::from_raw_parts(buf.as_ptr() as *const u8, n as usize);
                    if let Ok(s) = std::str::from_utf8(bytes) {
                        let mut chars = s.chars();
                        if let Some(c) = chars.next() {
                            if chars.next().is_none() {
                                table.entry(c).or_insert((m, code));
                            }
                        }
                    }
                }
            }
            xkb_state_unref(state);
        }
        xkb_keymap_unref(map);
        xkb_context_unref(ctx);
    }
    table.insert('\n', (0, 28));
    table.insert('\t', (0, 15));
    table.insert(' ', (0, 57));
    Ok(table)
}
fn key_events(out: &mut Vec<Event>, mods: u8, usage: u8, down: bool) -> Result<()> {
    if down {
        for &(b, c) in keys::MODS {
            if mods & b != 0 {
                out.push(Event::Key(c, true));
            }
        }
        if usage != 0 {
            out.push(Event::Key(evdev(usage as u16)?, true));
        }
    } else {
        if usage != 0 {
            out.push(Event::Key(evdev(usage as u16)?, false));
        }
        for &(b, c) in keys::MODS.iter().rev() {
            if mods & b != 0 {
                out.push(Event::Key(c, false));
            }
        }
    }
    Ok(())
}
pub fn expand(m: &Value, typing: &HashMap<char, (u8, u16)>) -> Result<Vec<Event>> {
    let steps = m["steps"]
        .as_array()
        .context("Macro steps must be an array")?;
    ensure!(steps.len() <= 4096, "Macro too long");
    let mode = m["mode"].as_str().unwrap_or("once");
    ensure!(
        ["once", "while-held", "toggle"].contains(&mode),
        "Invalid macro mode"
    );
    let gap = m["gap_ms"].as_u64().unwrap_or(0);
    ensure!(gap <= 10000, "Macro gap too large");
    let mut out = vec![];
    for (i, s) in steps.iter().enumerate() {
        if i > 0 && gap > 0 {
            out.push(Event::Wait(gap));
        }
        let a = &s["args"];
        match s["kind"].as_str().context("Missing macro step kind")? {
            "key" | "key-down" | "key-up" => {
                let (m, u) = combo(a["combo"].as_str().context("Missing key combo")?)?;
                match s["kind"].as_str().unwrap() {
                    "key" => {
                        key_events(&mut out, m, u, true)?;
                        key_events(&mut out, m, u, false)?;
                    }
                    "key-down" => key_events(&mut out, m, u, true)?,
                    _ => key_events(&mut out, m, u, false)?,
                }
            }
            "text" => {
                let text = a["text"].as_str().context("Text must be a string")?;
                ensure!(text.len() <= 65536, "Text too long");
                for c in text.chars() {
                    let &(m, code) = typing
                        .get(&c)
                        .context(format!("Cannot type {c:?} in this layout"))?;
                    for &(b, k) in keys::MODS {
                        if m & b != 0 {
                            out.push(Event::Key(k, true));
                        }
                    }
                    out.push(Event::Key(code, true));
                    out.push(Event::Key(code, false));
                    for &(b, k) in keys::MODS.iter().rev() {
                        if m & b != 0 {
                            out.push(Event::Key(k, false));
                        }
                    }
                }
            }
            "delay" => {
                let ms = a["ms"].as_u64().context("Invalid delay")?;
                ensure!(ms <= 600000, "Delay too long");
                out.push(Event::Wait(ms));
            }
            "click" | "button-down" | "button-up" => {
                let name = a["button"].as_str().context("Missing button")?;
                let i = ["left", "right", "middle", "back", "forward"]
                    .iter()
                    .position(|&n| n == name)
                    .context("Unknown mouse button")?;
                let code = [0x110, 0x111, 0x112, 0x113, 0x114][i];
                match s["kind"].as_str().unwrap() {
                    "click" => {
                        out.push(Event::Key(code, true));
                        out.push(Event::Key(code, false));
                    }
                    "button-down" => out.push(Event::Key(code, true)),
                    _ => out.push(Event::Key(code, false)),
                }
            }
            "scroll" | "hscroll" => {
                let n = a["amount"].as_i64().context("Missing scroll amount")?;
                ensure!((-1000..=1000).contains(&n), "Scroll amount too large");
                out.push(Event::Rel(
                    if s["kind"] == "scroll" { 8 } else { 6 },
                    n as i32,
                ));
            }
            "move" => {
                for (k, code) in [("dx", 0), ("dy", 1)] {
                    let n = a[k].as_i64().context("Missing movement")?;
                    ensure!((-32768..=32767).contains(&n), "Movement too large");
                    out.push(Event::Rel(code, n as i32));
                }
            }
            "media" => {
                let code = media_evdev(consumer(a["key"].as_str().context("Missing media key")?)?)?;
                out.push(Event::Key(code, true));
                out.push(Event::Key(code, false));
            }
            other => bail!("Unknown macro step {other}"),
        }
    }
    Ok(out)
}
#[repr(C)]
struct InputEvent {
    time: libc::timeval,
    kind: u16,
    code: u16,
    value: i32,
}
struct Backend {
    file: File,
    pressed: HashMap<u16, u32>,
}
impl Backend {
    fn new() -> Result<Self> {
        let mut file = OpenOptions::new()
            .write(true)
            .open("/dev/uinput")
            .context("Cannot open /dev/uinput; check device permissions")?;
        unsafe {
            for ev in [1, 2] {
                ensure!(
                    libc::ioctl(file.as_raw_fd(), 0x40045564 as libc::c_ulong, ev) == 0,
                    "uinput event setup failed"
                );
            }
            for code in (1..=255).chain(0x110..=0x114) {
                ensure!(
                    libc::ioctl(file.as_raw_fd(), 0x40045565 as libc::c_ulong, code) == 0,
                    "uinput key setup failed"
                );
            }
            for code in [0, 1, 6, 8] {
                ensure!(
                    libc::ioctl(file.as_raw_fd(), 0x40045566 as libc::c_ulong, code) == 0,
                    "uinput axis setup failed"
                );
            }
        }
        let mut setup = vec![0u8; 1116];
        let name = b"G502 Hub Rust macros";
        setup[..name.len()].copy_from_slice(name);
        setup[80..82].copy_from_slice(&3u16.to_ne_bytes());
        setup[82..84].copy_from_slice(&0x046du16.to_ne_bytes());
        file.write_all(&setup)?;
        ensure!(
            unsafe { libc::ioctl(file.as_raw_fd(), 0x5501 as libc::c_ulong) } == 0,
            "Cannot create uinput device"
        );
        Ok(Self {
            file,
            pressed: HashMap::new(),
        })
    }
    fn emit(&mut self, kind: u16, code: u16, value: i32) -> Result<()> {
        let e = InputEvent {
            time: libc::timeval {
                tv_sec: 0,
                tv_usec: 0,
            },
            kind,
            code,
            value,
        };
        let bytes = unsafe {
            std::slice::from_raw_parts(
                (&e as *const InputEvent).cast::<u8>(),
                std::mem::size_of::<InputEvent>(),
            )
        };
        self.file.write_all(bytes)?;
        Ok(())
    }
    fn key(&mut self, code: u16, down: bool) -> Result<()> {
        let n = self.pressed.entry(code).or_default();
        if down {
            *n += 1;
            if *n == 1 {
                self.emit(1, code, 1)?;
            }
        } else if *n > 0 {
            *n -= 1;
            if *n == 0 {
                self.emit(1, code, 0)?;
            }
        }
        self.emit(0, 0, 0)
    }
}
impl Drop for Backend {
    fn drop(&mut self) {
        unsafe {
            libc::ioctl(self.file.as_raw_fd(), 0x5502 as libc::c_ulong);
        }
    }
}
struct Run {
    cancel: Arc<AtomicBool>,
    finished: Arc<AtomicBool>,
    mode: String,
    thread: thread::JoinHandle<()>,
}
pub struct Player {
    backend: Option<Arc<Mutex<Backend>>>,
    runs: HashMap<String, Run>,
    pub error: Arc<Mutex<Option<String>>>,
}
impl Default for Player {
    fn default() -> Self {
        Self {
            backend: None,
            runs: HashMap::new(),
            error: Arc::new(Mutex::new(None)),
        }
    }
}
fn wait(cancel: &AtomicBool, ms: u64) {
    let end = Instant::now() + Duration::from_millis(ms);
    while !cancel.load(Ordering::Relaxed) && Instant::now() < end {
        thread::sleep(
            end.saturating_duration_since(Instant::now())
                .min(Duration::from_millis(10)),
        );
    }
}
impl Player {
    pub fn press(&mut self, key: String, events: Vec<Event>, mode: &str) -> Result<()> {
        self.reap();
        if let Some(run) = self.runs.get(&key) {
            if mode == "toggle" {
                run.cancel.store(true, Ordering::Relaxed);
            }
            return Ok(());
        }
        if self.backend.is_none() {
            self.backend = Some(Arc::new(Mutex::new(Backend::new()?)));
        }
        let backend = self.backend.as_ref().unwrap().clone();
        let cancel = Arc::new(AtomicBool::new(false));
        let finished = Arc::new(AtomicBool::new(false));
        let c = cancel.clone();
        let f = finished.clone();
        let mode = mode.to_owned();
        let once = mode == "once";
        let error = self.error.clone();
        let thread = thread::spawn(move || {
            let mut held = HashMap::<u16, u32>::new();
            let result = (|| -> Result<()> {
                loop {
                    let start = Instant::now();
                    for e in &events {
                        if c.load(Ordering::Relaxed) {
                            break;
                        }
                        match *e {
                            Event::Wait(ms) => wait(&c, ms),
                            Event::Key(code, down) => {
                                if down {
                                    *held.entry(code).or_default() += 1;
                                    backend.lock().unwrap().key(code, true)?;
                                } else if let Some(n) = held.get_mut(&code) {
                                    if *n > 0 {
                                        *n -= 1;
                                        backend.lock().unwrap().key(code, false)?;
                                    }
                                }
                                wait(&c, 4);
                            }
                            Event::Rel(code, n) => {
                                let mut b = backend.lock().unwrap();
                                b.emit(2, code, n)?;
                                b.emit(0, 0, 0)?;
                            }
                        }
                    }
                    if once || c.load(Ordering::Relaxed) {
                        break;
                    }
                    if start.elapsed() < Duration::from_millis(10) {
                        wait(&c, 10);
                    }
                }
                Ok(())
            })();
            if let Err(e) = result {
                *error.lock().unwrap() = Some(e.to_string());
            }
            for (code, n) in held {
                for _ in 0..n {
                    let _ = backend.lock().unwrap().key(code, false);
                }
            }
            f.store(true, Ordering::Relaxed);
        });
        self.runs.insert(
            key,
            Run {
                cancel,
                finished,
                mode,
                thread,
            },
        );
        Ok(())
    }
    pub fn release(&mut self, key: &str) {
        if let Some(r) = self.runs.get(key) {
            if r.mode == "while-held" {
                r.cancel.store(true, Ordering::Relaxed);
            }
        }
    }
    pub fn reap(&mut self) {
        let keys: Vec<_> = self
            .runs
            .iter()
            .filter(|(_, r)| r.finished.load(Ordering::Relaxed))
            .map(|(k, _)| k.clone())
            .collect();
        for k in keys {
            if let Some(r) = self.runs.remove(&k) {
                let _ = r.thread.join();
            }
        }
    }
    pub fn stop_all(&mut self) {
        for r in self.runs.values() {
            r.cancel.store(true, Ordering::Relaxed);
        }
        for (_, r) in self.runs.drain() {
            let _ = r.thread.join();
        }
    }
}
impl Drop for Player {
    fn drop(&mut self) {
        self.stop_all();
    }
}
pub fn onboard_macro(events: &[Event]) -> Result<Vec<u8>> {
    let mut out = vec![];
    for e in events {
        match *e {
            Event::Wait(mut ms) => {
                while ms > 0 {
                    let n = ms.min(65535) as u16;
                    out.push(0x40);
                    out.extend_from_slice(&n.to_be_bytes());
                    ms -= n as u64;
                }
            }
            Event::Key(code, down) => {
                if let Some(&(bit, _)) = keys::MODS.iter().find(|(_, k)| *k == code) {
                    out.extend_from_slice(&[if down { 0x43 } else { 0x44 }, bit, 0]);
                } else if let Some(&(hid, _)) = keys::HID_EVDEV.iter().find(|(_, k)| *k == code) {
                    out.extend_from_slice(&[if down { 0x43 } else { 0x44 }, 0, hid as u8]);
                } else if (0x110..=0x114).contains(&code) {
                    out.push(if down { 0x41 } else { 0x42 });
                    out.extend_from_slice(&(1u16 << (code - 0x110)).to_be_bytes());
                } else {
                    let usage = keys::CONSUMER
                        .iter()
                        .find(|(_, u)| media_evdev(*u).ok() == Some(code))
                        .context("Cannot store key in onboard macro")?
                        .1;
                    out.push(if down { 0x45 } else { 0x46 });
                    out.extend_from_slice(&usage.to_be_bytes());
                }
            }
            Event::Rel(code, n) => {
                if code == 6 || code == 8 {
                    let mut n = n;
                    while n != 0 {
                        let p = n.clamp(-127, 127);
                        out.extend_from_slice(&[
                            if code == 8 { 0x20 } else { 0x21 },
                            p as i8 as u8,
                        ]);
                        n -= p;
                    }
                } else {
                    out.push(0x61);
                    let v = (n as i16).to_be_bytes();
                    out.extend_from_slice(if code == 0 { &v } else { &[0, 0] });
                    out.extend_from_slice(if code == 1 { &v } else { &[0, 0] });
                }
            }
        }
    }
    out.push(255);
    ensure!(out.len() <= 253, "Macro does not fit onboard memory");
    Ok(out)
}
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn combinations() {
        assert_eq!(combo("ctrl+shift+a").unwrap(), (3, 4));
        assert!(combo("a+b").is_err());
        assert_eq!(binding("profile-select:3").unwrap(), [144, 13, 255, 3]);
    }
    #[test]
    fn config_macro_modes_and_clicks() {
        let m = json!({"mode":"while-held","steps":[{"kind":"click","args":{"button":"left"}}]});
        assert_eq!(
            expand(&m, &HashMap::new()).unwrap(),
            vec![Event::Key(0x110, true), Event::Key(0x110, false)]
        );
    }
    #[test]
    fn azerty_text() {
        let t = typing_table("fr").unwrap();
        assert_eq!(t[&'a'].1, 16);
        assert_eq!(t[&'1'].0 & 2, 2);
    }
    #[test]
    fn unknown_binding_survives() {
        for b in [[7, 8, 9, 10], [128, 2, 3, 4], [144, 11, 255, 255]] {
            assert_eq!(binding(&describe_binding(b)).unwrap(), b);
        }
    }
}

#[cfg(test)]
mod playback_tests {
    use super::*;
    use std::os::{
        fd::{FromRawFd, IntoRawFd},
        unix::net::UnixStream,
    };
    fn player() -> (Player, UnixStream) {
        let (a, b) = UnixStream::pair().unwrap();
        let backend = Backend {
            file: unsafe { File::from_raw_fd(a.into_raw_fd()) },
            pressed: HashMap::new(),
        };
        let mut p = Player::default();
        p.backend = Some(Arc::new(Mutex::new(backend)));
        (p, b)
    }
    fn until(mut f: impl FnMut() -> bool) {
        let start = Instant::now();
        while !f() {
            assert!(start.elapsed() < Duration::from_secs(2));
            thread::sleep(Duration::from_millis(1));
        }
    }
    #[test]
    fn held_and_toggle_cancel_release_keys() {
        for mode in ["while-held", "toggle"] {
            let (mut p, _reader) = player();
            p.press(
                "a".into(),
                vec![Event::Key(29, true), Event::Wait(600000)],
                mode,
            )
            .unwrap();
            until(|| p.backend.as_ref().unwrap().lock().unwrap().pressed.get(&29) == Some(&1));
            if mode == "while-held" {
                p.release("a");
            } else {
                p.press("a".into(), vec![], mode).unwrap();
            }
            until(|| p.runs["a"].finished.load(Ordering::Relaxed));
            p.reap();
            assert!(p.runs.is_empty());
            assert_eq!(p.backend.as_ref().unwrap().lock().unwrap().pressed[&29], 0);
        }
    }
    #[test]
    fn stopping_one_macro_does_not_release_another_macros_modifier() {
        let (mut p, _reader) = player();
        for k in ["a", "b"] {
            p.press(
                k.into(),
                vec![Event::Key(29, true), Event::Wait(600000)],
                "while-held",
            )
            .unwrap();
        }
        until(|| p.backend.as_ref().unwrap().lock().unwrap().pressed.get(&29) == Some(&2));
        p.release("a");
        until(|| p.runs["a"].finished.load(Ordering::Relaxed));
        assert_eq!(p.backend.as_ref().unwrap().lock().unwrap().pressed[&29], 1);
        p.stop_all();
        assert_eq!(p.backend.as_ref().unwrap().lock().unwrap().pressed[&29], 0);
    }
    #[test]
    fn onboard_modifier_release_contains_the_released_bit() {
        let m = serde_json::json!({"steps":[{"kind":"key","args":{"combo":"ctrl+c"}}]});
        let e = expand(&m, &HashMap::new()).unwrap();
        assert_eq!(
            onboard_macro(&e).unwrap(),
            vec![0x43, 1, 0, 0x43, 0, 6, 0x44, 0, 6, 0x44, 1, 0, 255]
        );
    }
}

#[cfg(test)]
mod variant_tests {
    #[test]
    fn gnome_layout_variant_is_supported() {
        assert!(super::typing_table("fr+latin9").unwrap().contains_key(&'é'));
    }
}
