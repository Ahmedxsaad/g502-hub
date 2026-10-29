use crate::model::{self, Directory, Led, Profile};
use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize};
use std::{
    collections::{HashMap, VecDeque},
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    os::{fd::AsRawFd, unix::fs::OpenOptionsExt},
    path::PathBuf,
    time::{Duration, Instant},
};
const ONBOARD: u16 = 0x8100;
#[derive(Debug)]
pub struct ProtocolError {
    pub code: u8,
    pub feature: u8,
    pub function: u8,
}
impl std::fmt::Display for ProtocolError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "HID++ error {:02x}, feature {}, function {}",
            self.code, self.feature, self.function
        )
    }
}
impl std::error::Error for ProtocolError {}
pub struct Hid {
    pub file: File,
    pub path: PathBuf,
    sw: u8,
    features: HashMap<u16, u8>,
    pub events: VecDeque<(u8, u8, Vec<u8>)>,
}
impl Hid {
    pub fn discover() -> Result<Self> {
        let root = std::env::var_os("G502_RUST_HIDRAW_ROOT")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("/sys/class/hidraw"));
        for node in fs::read_dir(root)? {
            let path = node?.path();
            let device = path.join("device");
            let u = fs::read_to_string(device.join("uevent"))
                .unwrap_or_default()
                .to_uppercase();
            let d = fs::read(device.join("report_descriptor")).unwrap_or_default();
            if u.contains("0000046D:0000C08B")
                && d.windows(3).any(|w| w == [6, 0, 255])
                && d.windows(2).any(|w| w == [0x85, 0x11])
            {
                let path = PathBuf::from("/dev").join(path.file_name().unwrap());
                let file = OpenOptions::new()
                    .read(true)
                    .write(true)
                    .custom_flags(libc::O_NONBLOCK)
                    .open(&path)
                    .with_context(|| format!("Cannot open {}", path.display()))?;
                return Ok(Self::from_file(file, path));
            }
        }
        bail!("G502 HERO not found")
    }
    pub fn from_file(file: File, path: PathBuf) -> Self {
        Self {
            file,
            path,
            sw: 0x0c,
            features: HashMap::from([(0, 0)]),
            events: VecDeque::new(),
        }
    }
    pub fn read(&mut self, timeout: Duration) -> Result<Option<Vec<u8>>> {
        let mut p = libc::pollfd {
            fd: self.file.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        let n = unsafe { libc::poll(&mut p, 1, timeout.as_millis().min(i32::MAX as u128) as i32) };
        if n < 0 {
            let e = std::io::Error::last_os_error();
            if e.kind() == std::io::ErrorKind::Interrupted {
                return Ok(None);
            }
            return Err(e.into());
        }
        if n == 0 {
            return Ok(None);
        }
        ensure!(
            p.revents & (libc::POLLHUP | libc::POLLERR | libc::POLLNVAL) == 0,
            "Mouse disconnected"
        );
        let mut buf = [0; 64];
        match self.file.read(&mut buf) {
            Ok(0) => bail!("Mouse disconnected"),
            Ok(n) => Ok(Some(buf[..n].to_vec())),
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => Ok(None),
            Err(e) => Err(e.into()),
        }
    }
    fn event(&mut self, data: &[u8]) {
        if data.len() >= 7
            && [0x10, 0x11].contains(&data[0])
            && data[1] == 255
            && ![0xff, 0x8f].contains(&data[2])
            && data[3] & 15 == 0
        {
            if self.events.len() >= 256 {
                self.events.pop_front();
            }
            self.events
                .push_back((data[2], data[3] >> 4, data[4..].to_vec()));
        }
    }
    pub fn request(
        &mut self,
        index: u8,
        function: u8,
        params: &[u8],
        retries: usize,
    ) -> Result<Vec<u8>> {
        ensure!(params.len() <= 16, "HID++ payload too long");
        let mut msg = vec![
            if params.len() <= 3 { 0x10 } else { 0x11 },
            255,
            index,
            function << 4 | self.sw,
        ];
        msg.extend_from_slice(params);
        msg.resize(if params.len() <= 3 { 7 } else { 20 }, 0);
        for attempt in 0..=retries {
            self.file.write_all(&msg)?;
            let deadline = Instant::now() + Duration::from_secs(1);
            while Instant::now() < deadline {
                let Some(data) = self.read(deadline.saturating_duration_since(Instant::now()))?
                else {
                    break;
                };
                if data.len() < 5 || ![0x10, 0x11].contains(&data[0]) || data[1] != 255 {
                    continue;
                }
                if [0xff, 0x8f].contains(&data[2]) && data[3] == index && data[4] == msg[3] {
                    ensure!(data.len() >= 6, "Truncated error reply");
                    if data[5] == 8 && attempt < retries {
                        std::thread::sleep(Duration::from_millis(10));
                        break;
                    }
                    return Err(ProtocolError {
                        code: data[5],
                        feature: index,
                        function,
                    }
                    .into());
                }
                if data[2] == index && data[3] == msg[3] {
                    let mut reply = data[4..].to_vec();
                    reply.resize(16, 0);
                    return Ok(reply);
                }
                self.event(&data);
            }
        }
        bail!("No HID++ reply (feature {index}, function {function})")
    }
    pub fn index(&mut self, feature: u16) -> Result<u8> {
        if let Some(&idx) = self.features.get(&feature) {
            return Ok(idx);
        }
        let r = self.request(0, 0, &feature.to_be_bytes(), 2)?;
        ensure!(r[0] != 0, "Unsupported HID++ feature {feature:04x}");
        self.features.insert(feature, r[0]);
        Ok(r[0])
    }
    pub fn call(&mut self, feature: u16, function: u8, params: &[u8]) -> Result<Vec<u8>> {
        let i = self.index(feature)?;
        self.request(i, function, params, 2)
    }
    pub fn drain(&mut self) -> Result<()> {
        for _ in 0..256 {
            let Some(d) = self.read(Duration::ZERO)? else {
                break;
            };
            self.event(&d);
        }
        Ok(())
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Info {
    pub profile_format: u8,
    pub macro_format: u8,
    pub profile_count: u8,
    pub rom_profile_count: u8,
    pub button_count: u8,
    pub sector_count: u8,
    pub sector_size: usize,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Zone {
    pub index: u8,
    pub location: u16,
    pub effects: HashMap<u16, u8>,
}
pub struct Device {
    pub hid: Hid,
    pub info: Info,
    pub zones: Vec<Zone>,
    pub name: String,
    pub firmware: Vec<String>,
    lock: File,
}
struct Lock(File);
impl Drop for Lock {
    fn drop(&mut self) {
        unsafe {
            libc::flock(self.0.as_raw_fd(), libc::LOCK_UN);
        }
    }
}
impl Device {
    pub fn open() -> Result<Self> {
        let mut hid = Hid::discover()?;
        let r = hid.call(ONBOARD, 0, &[])?;
        let info = Info {
            profile_format: r[1],
            macro_format: r[2],
            profile_count: r[3],
            rom_profile_count: r[4],
            button_count: r[5],
            sector_count: r[6],
            sector_size: u16::from_be_bytes([r[7], r[8]]) as usize,
        };
        ensure!(
            (254..=4096).contains(&info.sector_size),
            "Unsupported sector size"
        );
        let len = hid.call(5, 0, &[])?[0] as usize;
        let mut name = vec![];
        while name.len() < len {
            let r = hid.call(5, 1, &[name.len() as u8])?;
            name.extend_from_slice(&r);
        }
        name.truncate(len);
        let mut firmware = vec![];
        for n in 0..hid.call(3, 0, &[])?[0] {
            let r = hid.call(3, 1, &[n])?;
            firmware.push(format!(
                "{} {:02X}.{:02X}.B{:04X}",
                String::from_utf8_lossy(&r[1..4]).trim_matches(['\0', ' ']),
                r[4],
                r[5],
                u16::from_be_bytes([r[6], r[7]])
            ));
        }
        let mut zones = vec![];
        for n in 0..hid.call(0x8070, 0, &[])?[0] {
            let r = hid.call(0x8070, 1, &[n])?;
            let mut effects = HashMap::new();
            for e in 0..r[3] {
                let x = hid.call(0x8070, 2, &[n, e])?;
                effects.insert(u16::from_be_bytes([x[2], x[3]]), e);
            }
            zones.push(Zone {
                index: n,
                location: u16::from_be_bytes([r[1], r[2]]),
                effects,
            });
        }
        let dir = std::env::var_os("XDG_RUNTIME_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|| {
                PathBuf::from(format!("/tmp/g502-hub-{}", unsafe { libc::getuid() }))
            });
        fs::create_dir_all(&dir)?;
        let lock = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .mode(0o600)
            .open(dir.join("g502-hub.lock"))?;
        Ok(Self {
            hid,
            info,
            zones,
            name: String::from_utf8_lossy(&name).into_owned(),
            firmware,
            lock,
        })
    }
    fn acquire(&self) -> Result<Lock> {
        let file = self.lock.try_clone()?;
        let start = Instant::now();
        loop {
            if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } == 0 {
                return Ok(Lock(file));
            }
            ensure!(
                start.elapsed() < Duration::from_secs(10),
                "Another application is busy with the mouse"
            );
            std::thread::sleep(Duration::from_millis(20));
        }
    }
    fn sector_raw(&mut self, sector: u16) -> Result<Vec<u8>> {
        let size = self.info.sector_size;
        let mut data = vec![0; size];
        for offset in (0..size).step_by(16) {
            let off = offset.min(size - 16);
            let mut p = sector.to_be_bytes().to_vec();
            p.extend_from_slice(&(off as u16).to_be_bytes());
            let r = self.hid.call(ONBOARD, 5, &p)?;
            data[off..off + 16].copy_from_slice(&r[..16]);
        }
        Ok(data)
    }
    pub fn read_sector(&mut self, sector: u16) -> Result<Vec<u8>> {
        let _lock = self.acquire()?;
        self.sector_raw(sector)
    }
    pub fn directory(&mut self) -> Result<Directory> {
        let raw = self.read_sector(0)?;
        if let Some(d) = Directory::decode(&raw)? {
            return Ok(d);
        }
        Directory::decode(&self.read_sector(256)?)?.context("No onboard directory")
    }
    pub fn profile(&mut self, sector: u16) -> Result<Profile> {
        Profile::decode(&self.read_sector(sector)?)
    }
    pub fn mode(&mut self) -> Result<u8> {
        Ok(self.hid.call(ONBOARD, 2, &[])?[0])
    }
    pub fn set_mode(&mut self, mode: u8) -> Result<()> {
        ensure!([1, 2].contains(&mode), "Invalid mode");
        self.hid.call(ONBOARD, 1, &[mode])?;
        Ok(())
    }
    pub fn current(&mut self) -> Result<(u16, u8)> {
        let r = self.hid.call(ONBOARD, 4, &[])?;
        let dpi = self.hid.call(ONBOARD, 11, &[])?[0];
        Ok((u16::from_be_bytes([r[0], r[1]]), dpi))
    }
    pub fn activate(&mut self, sector: u16) -> Result<()> {
        self.hid.call(ONBOARD, 3, &sector.to_be_bytes())?;
        Ok(())
    }
    pub fn dpi_index(&mut self, index: u8) -> Result<()> {
        ensure!(index < 5, "Invalid DPI index");
        self.hid.call(ONBOARD, 12, &[index])?;
        Ok(())
    }
    pub fn dpi_range(&mut self) -> Result<[u16; 3]> {
        let r = self.hid.call(0x2201, 1, &[0])?;
        crate::parity::dpi_range(&r[1..])
    }
    pub fn preview_dpi(&mut self, dpi: u16) -> Result<()> {
        let [lo, hi, _] = self.dpi_range()?;
        ensure!((lo..=hi).contains(&dpi), "Invalid DPI");
        let [a, b] = dpi.to_be_bytes();
        self.hid.call(0x2201, 3, &[0, a, b])?;
        Ok(())
    }
    pub fn write_sector(&mut self, sector: u16, data: &[u8], allow_erased: bool) -> Result<()> {
        ensure!(
            self.info.profile_format == 2 && self.info.macro_format == 1,
            "Writes require profile format 2, macro format 1"
        );
        ensure!(
            sector < 256 && sector < (self.info.sector_count as u16),
            "Factory or invalid sector is not writable"
        );
        ensure!(
            data.len() == self.info.sector_size,
            "Incorrect sector length"
        );
        let valid = model::crc_ok(data);
        ensure!(
            valid || (allow_erased && data.iter().all(|&x| x == 255)),
            "Invalid sector CRC"
        );
        let _lock = self.acquire()?;
        let index = self.hid.index(ONBOARD)?;
        let mut success = false;
        for attempt in 0..3 {
            let result = (|| -> Result<()> {
                let mut p = sector.to_be_bytes().to_vec();
                p.extend_from_slice(&[0, 0]);
                p.extend_from_slice(&(data.len() as u16).to_be_bytes());
                self.hid.request(index, 6, &p, 0)?;
                for chunk in data.chunks(16) {
                    let mut p = chunk.to_vec();
                    p.resize(16, 255);
                    self.hid.request(index, 7, &p, 0)?;
                }
                match self.hid.request(index, 8, &[], 0) {
                    Ok(_) => {}
                    Err(e) => {
                        let expected = !valid
                            && e.downcast_ref::<ProtocolError>()
                                .is_some_and(|e| e.code == 4);
                        if !expected {
                            return Err(e);
                        }
                    }
                }
                Ok(())
            })();
            match result {
                Ok(()) => {
                    success = true;
                    break;
                }
                Err(e)
                    if attempt < 2
                        && (e
                            .downcast_ref::<ProtocolError>()
                            .is_some_and(|e| e.code == 8)
                            || e.to_string().contains("No HID++ reply")) =>
                {
                    std::thread::sleep(Duration::from_millis(50))
                }
                Err(e) => return Err(e),
            }
        }
        ensure!(success, "Sector write did not finish");
        ensure!(
            self.sector_raw(sector)? == data,
            "Sector read-back verification failed"
        );
        Ok(())
    }
    pub fn reload(&mut self, index: u8) -> Result<()> {
        let (current, _) = self.current()?;
        let d = self.directory()?;
        if let Some(other) = d.entries.iter().find(|e| e.sector != current && e.enabled) {
            self.activate(other.sector)?;
            self.activate(current)?;
        } else {
            self.set_mode(2)?;
            self.set_mode(1)?;
        }
        self.dpi_index(index)?;
        Ok(())
    }
    pub fn led(&mut self, zone: usize, led: &Led) -> Result<()> {
        let z = self.zones.get(zone).context("Unknown LED zone")?;
        let effect = *z
            .effects
            .get(&(led.effect as u16))
            .context("Unsupported LED effect")?;
        let mut p = vec![zone as u8, effect];
        let mut block = led.encode();
        if led.effect == 1 {
            block[4] = 2;
        }
        p.extend_from_slice(&block[1..]);
        p.push(0);
        self.hid.call(0x8070, 3, &p)?;
        Ok(())
    }
    pub fn spy_start(&mut self) -> Result<u8> {
        let i = self.hid.index(0x8110)?;
        self.hid.request(i, 1, &[], 2)?;
        Ok(i)
    }
    pub fn spy_stop(&mut self) -> Result<()> {
        self.hid.call(0x8110, 2, &[])?;
        Ok(())
    }
    pub fn backup(&mut self) -> Result<serde_json::Value> {
        let mut sectors = serde_json::Map::new();
        let count = self.info.sector_count as u16;
        for n in (0..count).chain(256..256 + self.info.rom_profile_count as u16 + 1) {
            sectors.insert(
                format!("0x{n:04X}"),
                model::hex(&self.read_sector(n)?).into(),
            );
        }
        let mode = self.mode()?;
        let current = self.current()?.0;
        Ok(
            serde_json::json!({"name":self.name,"firmware":self.firmware,"mode":mode,"current_profile":current,"sector_size":self.info.sector_size,"sectors":sectors}),
        )
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use std::os::fd::{FromRawFd, IntoRawFd};
    use std::os::unix::net::UnixStream;
    #[test]
    fn transport_matches_replies_and_queues_events() {
        let (a, mut b) = UnixStream::pair().unwrap();
        let file = unsafe { File::from_raw_fd(a.into_raw_fd()) };
        let mut h = Hid::from_file(file, PathBuf::from("test"));
        let t = std::thread::spawn(move || {
            let mut msg = [0; 7];
            b.read_exact(&mut msg).unwrap();
            assert_eq!(&msg[..4], &[0x10, 255, 9, 0x2c]);
            b.write_all(&[0x10, 255, 5, 0, 0, 1, 0]).unwrap();
            std::thread::sleep(Duration::from_millis(5));
            b.write_all(&[0x10, 255, 9, 0x2c, 42, 0, 0]).unwrap();
            std::thread::sleep(Duration::from_millis(10));
        });
        let reply = h.request(9, 2, &[], 0).unwrap();
        assert_eq!(reply[0], 42);
        assert_eq!(h.events.len(), 1);
        t.join().unwrap();
    }
}

#[cfg(test)]
mod write_tests {
    use super::*;
    use std::os::fd::{FromRawFd, IntoRawFd};
    use std::os::unix::net::UnixStream;
    use std::sync::{
        Arc,
        atomic::{AtomicUsize, Ordering},
    };
    fn fake(corrupt: bool, busy: bool) -> (Device, Arc<AtomicUsize>, std::thread::JoinHandle<()>) {
        let (a, mut b) = UnixStream::pair().unwrap();
        let writes = Arc::new(AtomicUsize::new(0));
        let count = writes.clone();
        let thread = std::thread::spawn(move || {
            let mut stored = model::sealed(vec![0; 255]).unwrap();
            let mut pending = vec![];
            let mut once = busy;
            loop {
                let mut id = [0];
                if b.read_exact(&mut id).is_err() {
                    break;
                }
                let size = if id[0] == 0x10 { 7 } else { 20 };
                let mut packet = vec![0; size];
                packet[0] = id[0];
                b.read_exact(&mut packet[1..]).unwrap();
                let function = packet[3] >> 4;
                let mut payload = vec![0; 16];
                if function == 6 {
                    count.fetch_add(1, Ordering::SeqCst);
                    if once {
                        once = false;
                        b.write_all(&[0x10, 255, 0xff, packet[2], packet[3], 8, 0])
                            .unwrap();
                        continue;
                    }
                    pending.clear();
                } else if function == 7 {
                    pending.extend_from_slice(&packet[4..]);
                } else if function == 8 {
                    pending.truncate(255);
                    stored = pending.clone();
                    if !model::crc_ok(&stored) {
                        b.write_all(&[0x10, 255, 0xff, packet[2], packet[3], 4, 0])
                            .unwrap();
                        continue;
                    }
                } else if function == 5 {
                    let offset = u16::from_be_bytes([packet[6], packet[7]]) as usize;
                    payload.copy_from_slice(&stored[offset..offset + 16]);
                    if corrupt {
                        payload[0] ^= 1;
                    }
                } else {
                    panic!("Unexpected function {function}");
                }
                let mut reply = vec![0x11, 255, packet[2], packet[3]];
                reply.extend(payload);
                b.write_all(&reply).unwrap();
            }
        });
        let mut hid = Hid::from_file(
            unsafe { File::from_raw_fd(a.into_raw_fd()) },
            PathBuf::from("fake"),
        );
        hid.features.insert(ONBOARD, 1);
        let path = std::env::temp_dir().join(format!(
            "g502-lock-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let lock = OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .open(&path)
            .unwrap();
        fs::remove_file(path).unwrap();
        let info = Info {
            profile_format: 2,
            macro_format: 1,
            profile_count: 5,
            rom_profile_count: 5,
            button_count: 11,
            sector_count: 10,
            sector_size: 255,
        };
        (
            Device {
                hid,
                info,
                zones: vec![],
                name: "fake".into(),
                firmware: vec![],
                lock,
            },
            writes,
            thread,
        )
    }
    #[test]
    fn writes_are_verified_and_busy_retries_restart_whole_sector() {
        let (mut d, count, t) = fake(false, true);
        let data = model::sealed(vec![23; 255]).unwrap();
        d.write_sector(1, &data, false).unwrap();
        assert_eq!(count.load(Ordering::SeqCst), 2);
        drop(d);
        t.join().unwrap();
    }
    #[test]
    fn mismatched_readback_is_an_error() {
        let (mut d, _, t) = fake(true, false);
        assert!(
            d.write_sector(1, &model::sealed(vec![23; 255]).unwrap(), false)
                .unwrap_err()
                .to_string()
                .contains("verification")
        );
        drop(d);
        t.join().unwrap();
    }
    #[test]
    fn invalid_writes_never_reach_transport() {
        let (mut d, count, t) = fake(false, false);
        let valid = model::sealed(vec![0; 255]).unwrap();
        assert!(d.write_sector(256, &valid, false).is_err());
        assert!(d.write_sector(10, &valid, false).is_err());
        assert!(d.write_sector(1, &valid[..250], false).is_err());
        assert!(d.write_sector(1, &vec![7; 255], false).is_err());
        assert!(d.write_sector(1, &vec![7; 255], true).is_err());
        assert_eq!(count.load(Ordering::SeqCst), 0);
        drop(d);
        t.join().unwrap();
    }
    #[test]
    fn erased_sector_requires_explicit_flag_and_is_verified() {
        let (mut d, _, t) = fake(false, false);
        let erased = vec![255; 255];
        assert!(d.write_sector(1, &erased, false).is_err());
        d.write_sector(1, &erased, true).unwrap();
        drop(d);
        t.join().unwrap();
    }
}
