use crate::{
    context::{Context, Game},
    model::Profile,
};
use anyhow::{Context as _, Result, bail, ensure};
use serde_json::{Value, json};
use std::{
    collections::HashMap,
    io::{Read, Write},
    net::{TcpListener, UdpSocket},
    os::fd::{AsRawFd, OwnedFd},
    os::unix::process::CommandExt,
    process::{Child, Command, Stdio},
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, AtomicU64, Ordering},
    },
    thread,
    time::{Duration, Instant},
};
use zbus::{
    blocking::{Connection, Proxy},
    zvariant::{OwnedObjectPath, OwnedValue},
};
pub type Rgb = [f32; 3];
pub type Colors = [Rgb; 2];
pub fn scale(c: Rgb, n: f32) -> Rgb {
    c.map(|x| (x * n).clamp(0., 1.))
}
pub fn mix(a: Rgb, b: Rgb, n: f32) -> Rgb {
    std::array::from_fn(|i| a[i] * (1. - n.clamp(0., 1.)) + b[i] * n.clamp(0., 1.))
}
pub fn hsv(h: f32, s: f32, v: f32) -> Rgb {
    let h = h.rem_euclid(1.) * 6.;
    let i = h.floor() as i32;
    let f = h - i as f32;
    let p = v * (1. - s);
    let q = v * (1. - f * s);
    let t = v * (1. - (1. - f) * s);
    match i {
        0 => [v, t, p],
        1 => [q, v, p],
        2 => [p, v, t],
        3 => [p, q, v],
        4 => [t, p, v],
        _ => [v, p, q],
    }
}
pub fn rgb_hex(s: &str) -> Rgb {
    let b = crate::model::unhex(s.trim_start_matches('#')).unwrap_or(vec![20, 180, 255]);
    if b.len() == 3 {
        [b[0] as f32 / 255., b[1] as f32 / 255., b[2] as f32 / 255.]
    } else {
        [0., 0.5, 1.]
    }
}
pub fn adjust(rgb: Rgb, saturation: f32, brightness: f32) -> Rgb {
    let max = rgb.into_iter().fold(0f32, f32::max);
    let min = rgb.into_iter().fold(1f32, f32::min);
    let delta = max - min;
    let h = if delta < 1e-8 {
        0.
    } else if max == rgb[0] {
        ((rgb[1] - rgb[2]) / delta).rem_euclid(6.) / 6.
    } else if max == rgb[1] {
        ((rgb[2] - rgb[0]) / delta + 2.) / 6.
    } else {
        ((rgb[0] - rgb[1]) / delta + 4.) / 6.
    };
    hsv(
        h,
        if max == 0. {
            0.
        } else {
            ((delta / max) * saturation).min(1.)
        },
        (max * brightness).min(1.),
    )
}
pub fn wave(
    t: f32,
    period: f32,
    zone: usize,
    saturation: f32,
    brightness: f32,
    reverse: bool,
) -> Rgb {
    let lag = 0.18
        * if reverse {
            1. - zone as f32
        } else {
            zone as f32
        };
    hsv(t / period.max(0.1) - lag, saturation, brightness)
}
pub fn audio_colors(
    style: &str,
    data: &CaptureData,
    color: Rgb,
    sensitivity: f32,
    hue: &mut f32,
) -> Colors {
    match style {
        "spectrum" => {
            let h = 0.66 - 0.66 * data.centroid;
            let bass = (data.bass * sensitivity).min(1.).powf(1.5);
            let treble = (data.treble.max(data.mid * 0.7) * sensitivity)
                .min(1.)
                .powf(1.5);
            [hsv(h + 0.12, 1., treble), hsv(h, 1., bass)]
        }
        "rainbow" => {
            if data.beat {
                *hue = (*hue + 0.17) % 1.;
            }
            let amount = (data.bass.max(data.level) * sensitivity).min(1.).powf(1.3);
            [hsv(*hue + 0.5, 1., amount), hsv(*hue, 1., amount)]
        }
        _ => {
            let amount = (data.bass.max(data.level * 0.6) * sensitivity)
                .min(1.)
                .powf(1.6);
            [scale(color, (amount * 1.1).min(1.)), scale(color, amount)]
        }
    }
}
pub fn palette(pixels: &[[u8; 3]]) -> Colors {
    let mut data = vec![];
    let mut hist = [0f32; 36];
    let mut total = 0.;
    for pixel in pixels {
        let c = pixel.map(|v| v as f32 / 255.);
        let max = c.into_iter().fold(0f32, f32::max);
        let min = c.into_iter().fold(1f32, f32::min);
        let delta = max - min;
        let sat = if max > 0. { delta / max } else { 0. };
        let hue = if delta <= 1e-6 {
            0.
        } else if max == c[0] {
            ((c[1] - c[2]) / delta).rem_euclid(6.) / 6.
        } else if max == c[1] {
            ((c[2] - c[0]) / delta + 2.) / 6.
        } else {
            ((c[0] - c[1]) / delta + 4.) / 6.
        };
        let bin = ((hue * 36.) as usize).min(35);
        let weight = sat * sat * max;
        hist[bin] += weight;
        total += weight;
        data.push((c, bin, weight));
    }
    if pixels.is_empty() || total < 1e-3 * pixels.len() as f32 {
        return [[1.; 3]; 2];
    }
    let old = hist;
    for i in 0..36 {
        hist[i] = old[i] + 0.5 * (old[(i + 35) % 36] + old[(i + 1) % 36]);
    }
    let mut out = vec![];
    for _ in 0..2 {
        let peak = (0..36).fold(0, |best, i| if hist[i] > hist[best] { i } else { best });
        if hist[peak] <= 0. {
            break;
        }
        let mut sum = [0.; 3];
        let mut weights = 0.;
        for (c, bin, w) in &data {
            let distance = ((*bin as i32 - peak as i32 + 18).rem_euclid(36) - 18).abs();
            if distance <= 1 {
                weights += w;
                for i in 0..3 {
                    sum[i] += c[i] * w;
                }
            }
        }
        let color = sum.map(|v| v / weights.max(1e-6));
        let max = color.into_iter().fold(0f32, f32::max).max(1e-6);
        out.push(color.map(|v| v / max));
        for d in -3i32..=3 {
            hist[(peak as i32 + d).rem_euclid(36) as usize] = 0.;
        }
    }
    if out.is_empty() {
        [[1.; 3]; 2]
    } else {
        [out[0], out.get(1).copied().unwrap_or(out[0])]
    }
}
pub fn pulse(t: f32, period: f32) -> f32 {
    (1. - (std::f32::consts::TAU * t / period.max(0.02)).cos()) * 0.5
}
#[derive(Clone, Default)]
pub struct CaptureData {
    pub frame: Vec<u8>,
    pub bass: f32,
    pub mid: f32,
    pub treble: f32,
    pub level: f32,
    pub beat: bool,
    pub centroid: f32,
    pub updated: Option<Instant>,
    pub error: Option<String>,
    pub restore_token: Option<String>,
}
#[derive(Default)]
struct PortalState {
    bus: Option<Connection>,
    request: Option<String>,
    session: Option<String>,
}
pub struct Capture {
    pub data: Arc<Mutex<CaptureData>>,
    child: Arc<Mutex<Option<Child>>>,
    stop: Arc<AtomicBool>,
    portal: Arc<Mutex<PortalState>>,
    thread: Option<thread::JoinHandle<()>>,
}
fn spawn_capture(
    command: &mut Command,
    child: &Arc<Mutex<Option<Child>>>,
) -> Result<std::process::ChildStdout> {
    let mut c = command
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()?;
    let stdout = c.stdout.take().context("No capture pipe")?;
    *child.lock().unwrap() = Some(c);
    Ok(stdout)
}
static TOKEN: AtomicU64 = AtomicU64::new(0);
fn owned_string(s: String) -> OwnedValue {
    OwnedValue::try_from(zbus::zvariant::Value::from(s)).unwrap()
}
fn portal_request(
    bus: &Connection,
    state: &Arc<Mutex<PortalState>>,
    method: &str,
    session: Option<&OwnedObjectPath>,
    mut options: HashMap<&str, OwnedValue>,
) -> Result<HashMap<String, OwnedValue>> {
    let token = format!(
        "g502rust_{}_{}",
        std::process::id(),
        TOKEN.fetch_add(1, Ordering::Relaxed)
    );
    let name = bus
        .unique_name()
        .context("No D-Bus name")?
        .as_str()
        .trim_start_matches(':')
        .replace('.', "_");
    let path = format!("/org/freedesktop/portal/desktop/request/{name}/{token}");
    options.insert("handle_token", owned_string(token));
    let response = Proxy::new(
        bus,
        "org.freedesktop.portal.Desktop",
        path.as_str(),
        "org.freedesktop.portal.Request",
    )?;
    let mut responses = response.receive_signal("Response")?;
    state.lock().unwrap().request = Some(path.clone());
    let proxy = Proxy::new(
        bus,
        "org.freedesktop.portal.Desktop",
        "/org/freedesktop/portal/desktop",
        "org.freedesktop.portal.ScreenCast",
    )?;
    let _: OwnedObjectPath = match (method, session) {
        ("CreateSession", _) => proxy.call(method, &(options,))?,
        ("SelectSources", Some(s)) => proxy.call(method, &(s, options))?,
        ("Start", Some(s)) => proxy.call(method, &(s, "", options))?,
        _ => bail!("Invalid portal request"),
    };
    let msg = responses.next().context("Portal response missing")?;
    let (code, results): (u32, HashMap<String, OwnedValue>) = msg.body().deserialize()?;
    state.lock().unwrap().request = None;
    ensure!(code == 0, "Screen sharing cancelled or refused ({code})");
    Ok(results)
}
fn pipewire(
    state: &Arc<Mutex<PortalState>>,
    restore: Option<String>,
    data: &Arc<Mutex<CaptureData>>,
) -> Result<(OwnedFd, u32)> {
    let bus = Connection::session()?;
    state.lock().unwrap().bus = Some(bus.clone());
    let token = format!(
        "g502session_{}_{}",
        std::process::id(),
        TOKEN.fetch_add(1, Ordering::Relaxed)
    );
    let result = portal_request(
        &bus,
        state,
        "CreateSession",
        None,
        HashMap::from([("session_handle_token", owned_string(token))]),
    )?;
    let value = result
        .get("session_handle")
        .context("Portal session missing")?;
    let session = OwnedObjectPath::try_from(value.try_clone()?).or_else(|_| {
        let s = <&str>::try_from(value)?;
        OwnedObjectPath::try_from(s).map_err(zbus::zvariant::Error::from)
    })?;
    state.lock().unwrap().session = Some(session.to_string());
    let proxy = Proxy::new(
        &bus,
        "org.freedesktop.portal.Desktop",
        "/org/freedesktop/portal/desktop",
        "org.freedesktop.portal.ScreenCast",
    )?;
    let version = proxy.get_property::<u32>("version").unwrap_or(1);
    let mut options = HashMap::from([
        ("types", OwnedValue::from(1u32)),
        ("multiple", OwnedValue::from(false)),
    ]);
    if proxy
        .get_property::<u32>("AvailableCursorModes")
        .unwrap_or(0)
        & 1
        != 0
    {
        options.insert("cursor_mode", OwnedValue::from(1u32));
    }
    if version >= 4 {
        options.insert("persist_mode", OwnedValue::from(2u32));
        if let Some(t) = restore {
            options.insert("restore_token", owned_string(t));
        }
    }
    portal_request(&bus, state, "SelectSources", Some(&session), options)?;
    let result = portal_request(&bus, state, "Start", Some(&session), HashMap::new())?;
    if let Some(token) = result
        .get("restore_token")
        .and_then(|v| <&str>::try_from(v).ok())
    {
        data.lock().unwrap().restore_token = Some(token.into());
    }
    let value = result
        .get("streams")
        .context("No shared screen")?
        .try_clone()?;
    let streams: Vec<(u32, HashMap<String, OwnedValue>)> = Vec::try_from(value)?;
    let node = streams.first().context("No shared screen")?.0;
    let fd: zbus::zvariant::OwnedFd = proxy.call(
        "OpenPipeWireRemote",
        &(session, HashMap::<&str, OwnedValue>::new()),
    )?;
    Ok((fd.into(), node))
}
impl Capture {
    pub fn start(kind: &str, restore: Option<String>) -> Self {
        let data = Arc::new(Mutex::new(CaptureData::default()));
        let child = Arc::new(Mutex::new(None));
        let stop = Arc::new(AtomicBool::new(false));
        let portal = Arc::new(Mutex::new(PortalState::default()));
        let (d, ch, s, p) = (data.clone(), child.clone(), stop.clone(), portal.clone());
        let audio = kind == "audio";
        let thread = thread::spawn(move || {
            let result = (|| -> Result<()> {
                if audio {
                    let mut cmd = Command::new("parec");
                    cmd.args([
                        "--device=@DEFAULT_MONITOR@",
                        "--format=s16le",
                        "--rate=44100",
                        "--channels=1",
                        "--latency-msec=30",
                    ]);
                    let mut pipe = spawn_capture(&mut cmd, &ch)?;
                    let mut analyzer = crate::audio::Analyzer::default();
                    let mut bytes = [0u8; 1024];
                    while !s.load(Ordering::Relaxed) {
                        pipe.read_exact(&mut bytes)?;
                        let samples: Vec<_> = bytes
                            .chunks_exact(2)
                            .map(|p| i16::from_le_bytes([p[0], p[1]]))
                            .collect();
                        if let Some(levels) = analyzer.feed(&samples) {
                            let mut shared = d.lock().unwrap();
                            let mut levels = levels;
                            levels.beat |= shared.beat;
                            *shared = levels;
                        }
                    }
                } else {
                    let mut cmd = Command::new("gst-launch-1.0");
                    let wayland =
                        std::env::var("XDG_SESSION_TYPE").unwrap_or_default() == "wayland";
                    let _fd;
                    if wayland {
                        let (fd, node) = pipewire(&p, restore, &d)?;
                        let n = fd.as_raw_fd();
                        _fd = Some(fd);
                        cmd.args([
                            "-q",
                            "pipewiresrc",
                            &format!("fd={n}"),
                            &format!("path={node}"),
                            "do-timestamp=true",
                        ]);
                        unsafe {
                            cmd.pre_exec(move || {
                                if libc::fcntl(n, libc::F_SETFD, 0) < 0 {
                                    return Err(std::io::Error::last_os_error());
                                }
                                Ok(())
                            });
                        }
                    } else {
                        _fd = None;
                        cmd.args(["-q", "ximagesrc", "use-damage=false", "show-pointer=false"]);
                    }
                    cmd.args([
                        "!",
                        "videorate",
                        "!",
                        "video/x-raw,framerate=30/1",
                        "!",
                        "videoscale",
                        "!",
                        "videoconvert",
                        "!",
                        "video/x-raw,format=RGB,width=64,height=36",
                        "!",
                        "fdsink",
                        "fd=1",
                    ]);
                    let mut pipe = spawn_capture(&mut cmd, &ch)?;
                    let mut frame = vec![0; 64 * 36 * 3];
                    while !s.load(Ordering::Relaxed) {
                        pipe.read_exact(&mut frame)?;
                        d.lock().unwrap().frame.clone_from(&frame);
                    }
                }
                Ok(())
            })();
            if let Err(e) = result {
                if !s.load(Ordering::Relaxed) {
                    d.lock().unwrap().error = Some(e.to_string());
                }
            }
        });
        Self {
            data,
            child,
            stop,
            portal,
            thread: Some(thread),
        }
    }
}
impl Drop for Capture {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Relaxed);
        if let Some(mut c) = self.child.lock().unwrap().take() {
            let _ = c.kill();
            let _ = c.wait();
        }
        let portal = self.portal.lock().unwrap();
        if let Some(bus) = &portal.bus {
            for (path, iface) in [
                (portal.request.as_ref(), "org.freedesktop.portal.Request"),
                (portal.session.as_ref(), "org.freedesktop.portal.Session"),
            ] {
                if let Some(path) = path {
                    if let Ok(p) =
                        Proxy::new(bus, "org.freedesktop.portal.Desktop", path.as_str(), iface)
                    {
                        let _: zbus::Result<()> = p.call("Close", &());
                    }
                }
            }
        }
        drop(portal);
        if let Some(t) = self.thread.take() {
            if t.is_finished() {
                let _ = t.join();
            }
        }
    }
}
#[derive(Clone)]
struct Channel {
    base: Rgb,
    zones: [Option<Rgb>; 2],
    effect: Option<(u8, Rgb, f32, f32, f32)>,
    saved: Option<(Rgb, [Option<Rgb>; 2])>,
    touched: bool,
}
impl Default for Channel {
    fn default() -> Self {
        Self {
            base: [0.; 3],
            zones: [None, None],
            effect: None,
            saved: None,
            touched: false,
        }
    }
}
impl Channel {
    fn colors(&self, t: f32) -> Colors {
        std::array::from_fn(|z| {
            if let Some((kind, rgb, start, duration, period)) = self.effect {
                if duration <= 0. || t - start < duration {
                    let phase = (t - start) / period.max(0.02);
                    return if kind == 5 {
                        if phase as i32 % 2 == 0 { rgb } else { [0.; 3] }
                    } else {
                        scale(rgb, pulse(phase, 1.))
                    };
                }
            }
            self.zones[z].unwrap_or(self.base)
        })
    }
}
#[derive(Default)]
struct Sdk {
    pid: u32,
    last: f32,
    closed: bool,
    target: i32,
    mouse: Channel,
    fallback: Channel,
}
impl Sdk {
    fn handle(&mut self, b: &[u8], t: f32) {
        if b.len() < 8 || &b[..2] != b"LS" || b[2] != 1 {
            return;
        }
        let op = b[3];
        let count = match op {
            1 | 2 | 7 | 8 | 9 | 12 => 0,
            3 => 1,
            4 | 11 => 3,
            5 | 6 | 10 => 5,
            _ => return,
        };
        if b.len() < 8 + count * 4 {
            return;
        }
        let pid = u32::from_le_bytes(b[4..8].try_into().unwrap());
        let a: Vec<i32> = b[8..8 + count * 4]
            .chunks_exact(4)
            .map(|p| i32::from_le_bytes(p.try_into().unwrap()))
            .collect();
        if op == 1 || self.pid == 0 || (self.closed && op != 2) {
            *self = Self {
                pid,
                target: 7,
                ..Default::default()
            };
        }
        if self.pid != pid {
            return;
        }
        self.last = t;
        if op == 2 {
            self.closed = true;
            return;
        }
        if op == 3 {
            self.target = a[0];
            return;
        }
        let c = if self.target & 2 != 0 {
            &mut self.mouse
        } else {
            &mut self.fallback
        };
        let rgb =
            |s: &[i32]| -> [f32; 3] { std::array::from_fn(|i| s[i].clamp(0, 100) as f32 / 100.) };
        match op {
            4 | 11 => {
                c.base = rgb(&a);
                c.zones = [None, None];
                c.touched = true;
            }
            5 | 6 => {
                c.effect = Some((op, rgb(&a), t, a[3] as f32 / 1000., a[4] as f32 / 1000.));
                c.touched = true;
            }
            7 => c.effect = None,
            8 => c.saved = Some((c.base, c.zones)),
            9 => {
                if let Some((base, zones)) = c.saved {
                    c.base = base;
                    c.zones = zones;
                    c.effect = None;
                }
            }
            10 => {
                if a[0] == 3 && (0..2).contains(&a[1]) {
                    self.mouse.zones[a[1] as usize] = Some(rgb(&a[2..]));
                    self.mouse.touched = true;
                } else {
                    self.fallback.base = rgb(&a[2..]);
                    self.fallback.touched = true;
                }
            }
            _ => {}
        }
    }
    fn colors(&self, t: f32) -> Option<Colors> {
        if self.pid == 0 || self.closed || t - self.last > 3. {
            return None;
        }
        if self.mouse.touched {
            Some(self.mouse.colors(t))
        } else if self.fallback.touched {
            Some(self.fallback.colors(t))
        } else {
            None
        }
    }
}
pub struct GameInputs {
    gsi: Arc<Mutex<Option<(Instant, String, Value)>>>,
    sdk: Arc<Mutex<Sdk>>,
    stop: Arc<AtomicBool>,
    start: Instant,
}
impl GameInputs {
    fn new() -> Result<Self> {
        let listener = TcpListener::bind("127.0.0.1:41502")?;
        listener.set_nonblocking(true)?;
        let udp = UdpSocket::bind("127.0.0.1:41503")?;
        udp.set_read_timeout(Some(Duration::from_millis(200)))?;
        let stop = Arc::new(AtomicBool::new(false));
        let gsi = Arc::new(Mutex::new(None));
        let sdk = Arc::new(Mutex::new(Sdk::default()));
        let start = Instant::now();
        let (s, g) = (stop.clone(), gsi.clone());
        thread::spawn(move || {
            while !s.load(Ordering::Relaxed) {
                match listener.accept() {
                    Ok((mut c, _)) => {
                        let _ = c.set_read_timeout(Some(Duration::from_secs(1)));
                        let result = (|| -> Result<(String, Value)> {
                            let mut bytes = vec![];
                            let header_end;
                            loop {
                                let mut b = [0; 1024];
                                let n = c.read(&mut b)?;
                                ensure!(n > 0, "Incomplete GSI request");
                                bytes.extend_from_slice(&b[..n]);
                                ensure!(bytes.len() <= 65536, "GSI request too large");
                                if let Some(i) = bytes.windows(4).position(|w| w == b"\r\n\r\n") {
                                    header_end = i + 4;
                                    break;
                                }
                            }
                            let h = String::from_utf8_lossy(&bytes[..header_end]);
                            let path = h.split_whitespace().nth(1).unwrap_or("").to_string();
                            let len = h
                                .lines()
                                .find_map(|l| {
                                    l.to_lowercase()
                                        .strip_prefix("content-length:")
                                        .and_then(|s| s.trim().parse::<usize>().ok())
                                })
                                .unwrap_or(0);
                            ensure!(len <= 65536, "GSI request too large");
                            while bytes.len() < header_end + len {
                                let mut b = [0; 4096];
                                let n = c.read(&mut b)?;
                                ensure!(n > 0, "Incomplete GSI request");
                                bytes.extend_from_slice(&b[..n]);
                            }
                            let data: Value =
                                serde_json::from_slice(&bytes[header_end..header_end + len])?;
                            ensure!(data["auth"]["token"] == "g502hub", "Invalid GSI token");
                            let game = if path.starts_with("/cs2")
                                || data["provider"]["appid"] == 730
                            {
                                "cs2"
                            } else if path.starts_with("/dota2") || data["provider"]["appid"] == 570
                            {
                                "dota2"
                            } else {
                                bail!("Unknown game")
                            };
                            Ok((game.into(), data))
                        })();
                        let code = if let Ok((game, data)) = result {
                            *g.lock().unwrap() = Some((Instant::now(), game, data));
                            "200 OK"
                        } else {
                            "400 Bad Request"
                        };
                        let _ = c.write_all(
                            format!(
                                "HTTP/1.1 {code}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                            )
                            .as_bytes(),
                        );
                    }
                    Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                        thread::sleep(Duration::from_millis(50))
                    }
                    Err(_) => break,
                }
            }
        });
        let (s, sk) = (stop.clone(), sdk.clone());
        thread::spawn(move || {
            let mut b = [0; 512];
            while !s.load(Ordering::Relaxed) {
                if let Ok((n, addr)) = udp.recv_from(&mut b) {
                    if addr.ip().is_loopback() {
                        sk.lock()
                            .unwrap()
                            .handle(&b[..n], start.elapsed().as_secs_f32());
                    }
                }
            }
        });
        Ok(Self {
            gsi,
            sdk,
            stop,
            start,
        })
    }
    fn colors(&self, t: f32, state: &mut GameStates) -> Option<Colors> {
        if let Some((at, game, data)) = &*self.gsi.lock().unwrap() {
            if at.elapsed() < Duration::from_secs(10) {
                let fx = if game == "cs2" {
                    &mut state.cs2
                } else {
                    &mut state.dota2
                };
                if let Some(c) = fx.colors(game, data, t) {
                    return Some(c);
                }
            }
        }
        self.sdk
            .lock()
            .unwrap()
            .colors(self.start.elapsed().as_secs_f32())
    }
}
impl Drop for GameInputs {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Relaxed);
    }
}
#[derive(Default)]
struct GameStates {
    cs2: GameFx,
    dota2: GameFx,
}
#[derive(Default)]
pub struct GameFx {
    last_t: Option<f32>,
    bomb: String,
    bomb_at: f32,
    bomb_phase: f32,
    kills: Option<u64>,
    kill_at: Option<f32>,
}
impl GameFx {
    pub fn colors(&mut self, game: &str, d: &Value, t: f32) -> Option<Colors> {
        let dt = self.last_t.map(|last| (t - last).max(0.)).unwrap_or(0.);
        self.last_t = Some(t);
        let health = |n: f32| hsv(0.33 * n.clamp(0., 1.), 1., 1.);
        let mut out;
        if game == "cs2" {
            let p = &d["player"];
            if d["map"].is_null() || p["activity"] == "menu" || p["state"].is_null() {
                self.bomb.clear();
                self.kills = None;
                return None;
            }
            let s = &p["state"];
            let team = if p["team"] == "CT" {
                [0.25, 0.55, 1.]
            } else {
                [1., 0.6, 0.1]
            };
            let h = s["health"].as_f64().unwrap_or(100.) as f32;
            let spectating = !d["provider"]["steamid"].is_null()
                && !p["steamid"].is_null()
                && d["provider"]["steamid"] != p["steamid"];
            out = if spectating || (h <= 0. && d["round"]["phase"] == "live") {
                [mix([0.22, 0., 0.], [0.4, 0., 0.], pulse(t, 3.)); 2]
            } else if d["round"]["phase"] == "freezetime" {
                [scale(team, 0.25 + 0.55 * pulse(t, 3.)); 2]
            } else {
                [
                    scale(team, 0.45),
                    scale(
                        health(h / 100.),
                        if h > 0. && h <= 20. {
                            0.5 + 0.5 * pulse(t, 0.8)
                        } else {
                            1.
                        },
                    ),
                ]
            };
            let bomb = d["round"]["bomb"].as_str().unwrap_or("");
            if bomb != self.bomb {
                self.bomb = bomb.into();
                self.bomb_at = t;
                self.bomb_phase = 0.;
            }
            match bomb {
                "planted" => {
                    let remain = if d["phase_countdowns"]["phase"] == "bomb" {
                        d["phase_countdowns"]["phase_ends_in"]
                            .as_f64()
                            .map(|n| n as f32)
                            .or_else(|| {
                                d["phase_countdowns"]["phase_ends_in"]
                                    .as_str()
                                    .and_then(|s| s.parse().ok())
                            })
                    } else {
                        None
                    }
                    .unwrap_or(40. - (t - self.bomb_at));
                    let period = 0.12 + 0.9 * (remain / 40.).clamp(0., 1.).powf(1.5);
                    self.bomb_phase += dt / period;
                    let beep = (-(self.bomb_phase.fract() * 6.)).exp();
                    out[0] = scale([1., 0., 0.], 0.15 + 0.85 * beep);
                    out[1] = mix(out[1], [1., 0., 0.], 0.5 * beep);
                }
                "exploded" => {
                    out = out.map(|c| mix(c, [1., 0.75, 0.3], (-(t - self.bomb_at) / 0.8).exp()))
                }
                "defused" => {
                    out[0] = mix(out[0], [0.25, 0.55, 1.], (-(t - self.bomb_at) / 1.5).exp())
                }
                _ => {}
            }
            if !spectating {
                let burn = s["burning"].as_f64().unwrap_or(0.) as f32 / 255.;
                out[1] = mix(
                    out[1],
                    scale(
                        [1., 0.32, 0.],
                        0.55 + 0.45 * (t * 31.).sin() * (t * 17.3 + 1.).sin(),
                    ),
                    burn,
                );
                self.kill(Some(s["round_kills"].as_u64().unwrap_or(0)), t);
                if let Some(at) = self.kill_at {
                    let f = (-(t - at) / 0.12).exp();
                    if f < 0.01 {
                        self.kill_at = None;
                    } else {
                        out = [
                            mix(out[0], [1.; 3], f),
                            mix(out[1], mix(team, [1.; 3], 0.6), f),
                        ];
                    }
                }
                let flash = s["flashed"].as_f64().unwrap_or(0.) as f32 / 255.;
                out = out.map(|c| mix(c, [1.; 3], flash));
            }
        } else {
            let h = &d["hero"];
            let gs = d["map"]["game_state"].as_str().unwrap_or("");
            if ![
                "DOTA_GAMERULES_STATE_PRE_GAME",
                "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
            ]
            .contains(&gs)
                || h["health_percent"].is_null()
            {
                self.kills = None;
                return None;
            }
            let team = if d["player"]["team_name"] == "radiant" {
                [0.2, 0.9, 0.35]
            } else {
                [0.9, 0.22, 0.12]
            };
            let hp = h["health_percent"].as_f64().unwrap_or(100.) as f32 / 100.;
            out = if d["map"]["paused"].as_bool().unwrap_or(false) {
                [scale(team, 0.3); 2]
            } else if !h["alive"].as_bool().unwrap_or(true) {
                let soon = 1. - (h["respawn_seconds"].as_f64().unwrap_or(0.) as f32).min(5.) / 5.;
                [scale(
                    mix([0.22, 0., 0.], scale(team, 0.8), soon),
                    0.4 + 0.6 * pulse(t, 1.6 - soon),
                ); 2]
            } else if gs.ends_with("PRE_GAME") {
                [scale(team, 0.3 + 0.5 * pulse(t, 3.)); 2]
            } else {
                let mana = h["mana_percent"].as_f64().unwrap_or(0.) as f32 / 100.;
                let mut c = [
                    scale([0.15, 0.4, 1.], 0.12 + 0.88 * mana),
                    scale(
                        health(hp),
                        if hp <= 0.25 {
                            0.45 + 0.55 * pulse(t, 0.7)
                        } else {
                            1.
                        },
                    ),
                ];
                if h["silenced"].as_bool().unwrap_or(false) {
                    c[0] = mix(c[0], [0.6, 0.1, 0.9], 0.6);
                }
                if h["stunned"].as_bool().unwrap_or(false) || h["hexed"].as_bool().unwrap_or(false)
                {
                    let v = t * 1.6;
                    let flicker = 0.55 + 0.45 * (v * 31.).sin() * (v * 17.3 + 1.).sin();
                    c[1] = mix(c[1], [1.; 3], 0.25 + 0.5 * flicker);
                }
                c
            };
            self.kill(d["player"]["kills"].as_u64(), t);
            if let Some(at) = self.kill_at {
                let f = (-(t - at) / 0.25).exp();
                if f < 0.01 {
                    self.kill_at = None;
                } else {
                    out = out.map(|c| mix(c, [1., 0.78, 0.2], f));
                }
            }
        }
        Some(out)
    }
    fn kill(&mut self, n: Option<u64>, t: f32) {
        if let (Some(old), Some(n)) = (self.kills, n) {
            if n > old {
                self.kill_at = Some(t);
            }
        }
        self.kills = n;
        if self.kill_at.is_some_and(|at| t - at > 2.) {
            self.kill_at = None;
        }
    }
}
pub fn defaults() -> Value {
    json!({"screen":{"dpi_area":"screen","logo_area":"center","vivid":true,"saturation":1.3,"brightness":1.0,"smoothing":0.6},"audio":{"style":"pulse","color":"#14b4ff","sensitivity":1.0,"brightness":1.0},"wave":{"period":6.0,"saturation":1.0,"brightness":1.0,"reverse":false},"dpi":{"colors":["#ff2a2a","#ffd400","#3ddc84","#14b4ff","#a040ff"]}})
}
pub fn sample(frame: &[u8], area: &str, vivid: bool) -> Rgb {
    let mut colors = vec![];
    for y in 0..36 {
        for x in 0..64 {
            let yes = match area {
                "center" => (12..51).contains(&x) && (5..30).contains(&y),
                "left" => x < 21,
                "right" => x >= 42,
                "top" => y < 11,
                "bottom" => y >= 24,
                _ => true,
            };
            if yes {
                let i = (y * 64 + x) * 3;
                if i + 2 < frame.len() {
                    colors.push([
                        frame[i] as f32 / 255.,
                        frame[i + 1] as f32 / 255.,
                        frame[i + 2] as f32 / 255.,
                    ]);
                }
            }
        }
    }
    if colors.is_empty() {
        return [0.; 3];
    }
    let mut sum = [0.; 3];
    let mut weights = 0.;
    let mut scene = 0.;
    for c in &colors {
        let max = c.iter().copied().fold(0f32, f32::max);
        let min = c.iter().copied().fold(1f32, f32::min);
        let saturation = (max - min) / max.max(1e-6);
        let weight = if vivid {
            saturation.powi(2) * max.powi(2) + 1e-4
        } else {
            1.
        };
        weights += weight;
        scene += max.powi(2);
        for i in 0..3 {
            sum[i] += c[i] * weight;
        }
    }
    let color = sum.map(|c| c / weights);
    if !vivid {
        return color;
    }
    let peak = color.iter().copied().fold(0f32, f32::max);
    if peak < 1e-4 {
        return [0.; 3];
    }
    let level = (0.15 + (scene / colors.len() as f32).sqrt() * 1.6).min(1.);
    color.map(|c| c / peak * level)
}
pub struct Live {
    pub kind: String,
    pub colors: [[u8; 3]; 2],
    pub error: Option<String>,
    pub restore_token: Option<String>,
    capture: Option<Capture>,
    game: Option<GameInputs>,
    fx: GameStates,
    start: Instant,
    current: Colors,
    have_current: bool,
    hue: f32,
    art: HashMap<String, Colors>,
}
impl Default for Live {
    fn default() -> Self {
        Self {
            kind: String::new(),
            colors: [[0; 3]; 2],
            error: None,
            restore_token: None,
            capture: None,
            game: None,
            fx: GameStates::default(),
            start: Instant::now(),
            current: [[0.; 3]; 2],
            have_current: false,
            hue: 0.,
            art: HashMap::new(),
        }
    }
}
impl Live {
    fn art(&mut self, game: Option<&Game>) -> Option<Colors> {
        let path = game?.art.as_ref()?;
        let key = path.to_string_lossy().into_owned();
        if let Some(c) = self.art.get(&key) {
            return Some(*c);
        }
        let image = image::open(path)
            .ok()?
            .resize_exact(96, 54, image::imageops::FilterType::Triangle)
            .to_rgb8();
        let pixels: Vec<_> = image.pixels().map(|p| p.0).collect();
        let [main, second] = palette(&pixels);
        let c = [second, main];
        self.art.insert(key, c);
        Some(c)
    }
    pub fn choose_screen(&mut self) {
        self.capture = None;
        self.kind.clear();
        self.restore_token = None;
        self.error = None;
    }
    pub fn frame(
        &mut self,
        settings: &Value,
        rule: Option<&Value>,
        ctx: &Context,
        profile: Option<&Profile>,
        dpi: usize,
    ) -> Option<[[u8; 3]; 2]> {
        let kind = rule
            .and_then(|r| r["lighting"].as_str())
            .filter(|s| !s.is_empty())
            .or_else(|| {
                if settings["live"]["on"].as_bool().unwrap_or(false) {
                    settings["live"]["effect"].as_str()
                } else {
                    None
                }
            })
            .unwrap_or("");
        if kind != self.kind {
            self.capture = None;
            self.error = None;
            self.kind = kind.into();
            self.have_current = false;
            if ["screen", "audio"].contains(&kind) {
                self.capture = Some(Capture::start(
                    kind,
                    settings["screen_token"].as_str().map(str::to_owned),
                ));
            }
            if kind == "game" && self.game.is_none() {
                match GameInputs::new() {
                    Ok(g) => self.game = Some(g),
                    Err(e) => self.error = Some(e.to_string()),
                }
            }
        }
        if kind.is_empty() {
            return None;
        }
        let t = self.start.elapsed().as_secs_f32();
        let base = defaults();
        let mut options = base[kind].clone();
        if let (Some(src), Some(dst)) = (
            settings["live"]["options"][kind].as_object(),
            options.as_object_mut(),
        ) {
            dst.extend(src.clone());
        }
        let f =
            |key: &str, default: f32| options[key].as_f64().map(|n| n as f32).unwrap_or(default);
        let mut target = match kind {
            "color" => [rgb_hex(rule.and_then(|r| r["color"].as_str()).unwrap_or("#14b4ff")); 2],
            "breathing" => {
                [scale(
                    rgb_hex(rule.and_then(|r| r["color"].as_str()).unwrap_or("#14b4ff")),
                    0.06 + 0.94
                        * pulse(
                            t,
                            rule.and_then(|r| r["period_ms"].as_f64()).unwrap_or(4000.) as f32
                                / 1000.,
                        ),
                ); 2]
            }
            "wave" => std::array::from_fn(|z| {
                wave(
                    t,
                    f("period", 6.),
                    z,
                    f("saturation", 1.),
                    f("brightness", 1.),
                    options["reverse"].as_bool().unwrap_or(false),
                )
            }),
            "dpi" => {
                let p = profile?;
                let levels: Vec<_> = p
                    .dpi
                    .iter()
                    .enumerate()
                    .filter(|(_, d)| **d != 0 && **d != 65535)
                    .map(|(i, _)| i)
                    .collect();
                let index = levels.iter().position(|&i| i == dpi)?;
                [rgb_hex(options["colors"][index].as_str().unwrap_or("#14b4ff")); 2]
            }
            "art" => self.art(ctx.game.as_ref()).unwrap_or(
                [rgb_hex(rule.and_then(|r| r["color"].as_str()).unwrap_or("#14b4ff")); 2],
            ),
            "game" => self
                .game
                .as_ref()
                .and_then(|g| g.colors(t, &mut self.fx))
                .or_else(|| self.art(ctx.game.as_ref()))?,
            "screen" | "audio" => {
                let data = {
                    let mut source = self.capture.as_ref()?.data.lock().unwrap();
                    let mut data = source.clone();
                    source.beat = false;
                    if kind == "audio"
                        && data
                            .updated
                            .is_some_and(|at| at.elapsed() > Duration::from_millis(300))
                    {
                        data.level = 0.;
                        data.bass = 0.;
                        data.mid = 0.;
                        data.treble = 0.;
                        data.beat = false;
                    }
                    data
                };
                if let Some(e) = data.error {
                    self.error = Some(e);
                    return None;
                }
                if let Some(token) = &data.restore_token {
                    self.restore_token = Some(token.clone());
                }
                if kind == "screen" {
                    if data.frame.is_empty() {
                        return None;
                    }
                    let mut colors = std::array::from_fn(|z| {
                        sample(
                            &data.frame,
                            options[if z == 0 { "dpi_area" } else { "logo_area" }]
                                .as_str()
                                .unwrap_or("screen"),
                            options["vivid"].as_bool().unwrap_or(true),
                        )
                    });
                    for c in &mut colors {
                        *c = adjust(*c, f("saturation", 1.3), f("brightness", 1.));
                    }
                    colors
                } else {
                    let c = audio_colors(
                        options["style"].as_str().unwrap_or("pulse"),
                        &data,
                        rgb_hex(options["color"].as_str().unwrap_or("#14b4ff")),
                        f("sensitivity", 1.),
                        &mut self.hue,
                    );
                    c.map(|c| scale(c, f("brightness", 1.)))
                }
            }
            _ => {
                self.error = Some(format!("Unknown effect {kind}"));
                return None;
            }
        };
        let response = if kind == "screen" {
            1. - 0.93 * f("smoothing", 0.6)
        } else if kind == "art" {
            0.08
        } else {
            1.
        };
        for z in 0..2 {
            if self.have_current {
                target[z] = mix(self.current[z], target[z], response);
            }
        }
        self.current = target;
        self.have_current = true;
        let colors = target.map(|c| c.map(|n| (n.clamp(0., 1.) * 255.).round() as u8));
        self.colors = colors;
        Some(colors)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn vivid_screen_sampling_emphasizes_colored_highlights() {
        let mut frame = vec![64; 64 * 36 * 3];
        for pixel in frame.chunks_exact_mut(3).take(64 * 9) {
            pixel.copy_from_slice(&[255, 0, 0]);
        }
        let average = sample(&frame, "screen", false);
        let vivid = sample(&frame, "screen", true);
        assert!((average[0] - (0.25 + 0.75 * 64. / 255.)).abs() < 1e-4);
        assert!(vivid[0] > average[0] && vivid[1] < average[1]);
        assert_eq!(sample(&vec![0; 64 * 36 * 3], "screen", true), [0.; 3]);
    }
    #[test]
    fn sdk_routing_and_staleness() {
        let mut sdk = Sdk::default();
        let mut data = b"LS\x01\x04".to_vec();
        data.extend_from_slice(&1u32.to_le_bytes());
        for n in [100i32, 0, 50] {
            data.extend_from_slice(&n.to_le_bytes());
        }
        sdk.handle(&data, 0.);
        assert_eq!(sdk.colors(1.).unwrap()[0], [1., 0., 0.5]);
        assert!(sdk.colors(4.).is_none());
    }
    #[test]
    fn color_math() {
        assert_eq!(rgb_hex("#ff0080"), [1., 0., 128. / 255.]);
        assert_eq!(hsv(0., 1., 1.), [1., 0., 0.]);
        assert!(pulse(0., 1.).abs() < 0.001);
    }
}
