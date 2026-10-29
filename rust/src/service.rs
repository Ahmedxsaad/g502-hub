use crate::{
    config,
    context::{self, Context, Watcher},
    device::{Device, Info},
    effects::Live,
    input::{self, Player},
    ipc,
    model::{self, Directory, Led, Profile},
};
use anyhow::{Context as _, Result, bail, ensure};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::HashMap,
    fs,
    io::{BufRead, BufReader, Read, Write},
    os::{fd::AsRawFd, unix::net::UnixListener},
    sync::atomic::{AtomicBool, Ordering},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
#[derive(Clone, Default, Serialize, Deserialize)]
pub struct Snapshot {
    pub connected: bool,
    pub name: String,
    pub firmware: Vec<String>,
    pub info: Option<Info>,
    pub directory: Option<Directory>,
    pub profiles: Vec<Profile>,
    pub slot: usize,
    pub dpi_index: usize,
    pub settings: Value,
    pub context: Context,
    pub active_rule: Option<Value>,
    pub colors: Option<[[u8; 3]; 2]>,
    pub status: String,
    pub error: Option<String>,
    pub macro_error: Option<String>,
    pub pid: u32,
}
struct Engine {
    device: Option<Device>,
    snapshot: Snapshot,
    watcher: Option<Watcher>,
    live: Live,
    player: Player,
    typing: HashMap<char, (u8, u16)>,
    spy: Option<u8>,
    mask: u16,
    backup_done: bool,
    slot_before: Option<usize>,
    rule_id: Option<String>,
    last_colors: Option<[[u8; 3]; 2]>,
    last_send: Instant,
}
impl Engine {
    fn new() -> Result<Self> {
        config::import_python()?;
        let settings = config::load()?;
        let l = settings["keyboard_layout"]
            .as_str()
            .map(str::to_owned)
            .unwrap_or_else(input::layout);
        let typing = input::typing_table(&l)?;
        let mut e = Self {
            device: None,
            snapshot: Snapshot {
                settings,
                pid: std::process::id(),
                ..Default::default()
            },
            watcher: None,
            live: Live::default(),
            player: Player::default(),
            typing,
            spy: None,
            mask: 0,
            backup_done: false,
            slot_before: None,
            rule_id: None,
            last_colors: None,
            last_send: Instant::now(),
        };
        e.update_watcher();
        Ok(e)
    }
    fn update_watcher(&mut self) {
        let want = self.snapshot.settings["rules"]
            .as_array()
            .is_some_and(|r| r.iter().any(|r| r["enabled"].as_bool().unwrap_or(true)));
        if want && self.watcher.is_none() {
            self.watcher = Some(Watcher::new());
        } else if !want {
            self.watcher = None;
            self.snapshot.context = Context::default();
        }
    }
    fn connect(&mut self) -> Result<()> {
        let mut d = Device::open()?;
        if d.mode()? != 1 {
            d.set_mode(1)?;
        }
        let directory = d.directory()?;
        ensure!(
            !directory.entries.is_empty() && directory.entries.len() <= 16,
            "Invalid profile count"
        );
        let mut profiles = vec![];
        for e in &directory.entries {
            profiles.push(d.profile(e.sector)?);
        }
        let (sector, dpi) = d.current()?;
        self.snapshot.name = d.name.clone();
        self.snapshot.firmware = d.firmware.clone();
        self.snapshot.info = Some(d.info.clone());
        self.snapshot.slot = directory
            .entries
            .iter()
            .position(|e| e.sector == sector)
            .map(|n| n + 1)
            .unwrap_or(1);
        self.snapshot.dpi_index = dpi as usize;
        self.snapshot.directory = Some(directory);
        self.snapshot.profiles = profiles;
        self.snapshot.connected = true;
        self.snapshot.status = "Prêt — service Rust natif".into();
        self.snapshot.error = None;
        self.device = Some(d);
        self.backup_done = false;
        self.mask = 0;
        self.sync_spy()?;
        Ok(())
    }
    fn sync_spy(&mut self) -> Result<()> {
        let need = self.snapshot.settings["app_macros"]
            .as_object()
            .is_some_and(|m| !m.is_empty());
        if let Some(d) = &mut self.device {
            if need && self.spy.is_none() {
                self.spy = Some(d.spy_start()?);
            } else if !need && self.spy.is_some() {
                d.spy_stop()?;
                self.spy = None;
                self.player.stop_all();
            }
        }
        Ok(())
    }
    fn lost(&mut self, error: anyhow::Error) {
        self.player.stop_all();
        self.device = None;
        self.spy = None;
        self.snapshot.connected = false;
        self.snapshot.error = Some(error.to_string());
        self.snapshot.status = "Souris déconnectée — reconnexion automatique".into();
    }
    fn current_profile(&self) -> Option<&Profile> {
        self.snapshot
            .slot
            .checked_sub(1)
            .and_then(|i| self.snapshot.profiles.get(i))
    }
    fn buttons(&mut self, mask: u16) {
        let old = self.mask;
        self.mask = mask;
        let layer = self.current_profile().is_some_and(|p| {
            p.buttons
                .iter()
                .enumerate()
                .any(|(i, b)| b[0] == 144 && b[1] == 11 && (old | mask) & (1 << i) != 0)
        });
        let slot = self.snapshot.slot;
        for button in 0..16 {
            let bit = 1u16 << button;
            if (old ^ mask) & bit == 0 {
                continue;
            }
            let key = format!("{slot}:{}:{button}", u8::from(layer));
            if mask & bit == 0 {
                self.player.release(&key);
                self.player
                    .release(&format!("{slot}:{}:{button}", u8::from(!layer)));
                continue;
            }
            let mid = self.snapshot.settings["app_macros"][&key].as_str();
            let m = mid
                .and_then(|id| {
                    self.snapshot.settings["macros"]
                        .as_array()?
                        .iter()
                        .find(|m| m["id"].as_str() == Some(id))
                })
                .cloned();
            if let Some(m) = m {
                let result = input::expand(&m, &self.typing).and_then(|events| {
                    self.player
                        .press(key, events, m["mode"].as_str().unwrap_or("once"))
                });
                if let Err(e) = result {
                    self.snapshot.macro_error = Some(e.to_string());
                }
            }
        }
    }
    fn events(&mut self) -> Result<()> {
        let Some(d) = &mut self.device else {
            return Ok(());
        };
        d.hid.drain()?;
        let mut masks = vec![];
        while let Some((index, event, params)) = d.hid.events.pop_front() {
            if Some(index) == self.spy && event == 0 && params.len() >= 2 {
                masks.push(u16::from_be_bytes([params[0], params[1]]));
            }
        }
        for mask in masks {
            self.buttons(mask);
        }
        self.player.reap();
        if let Some(e) = self.player.error.lock().unwrap().take() {
            self.snapshot.macro_error = Some(e);
        }
        Ok(())
    }
    fn poll(&mut self) -> Result<()> {
        if let Some(d) = &mut self.device {
            let (sector, dpi) = d.current()?;
            let before = (self.snapshot.slot, self.snapshot.dpi_index);
            if let Some(slot) = self
                .snapshot
                .directory
                .as_ref()
                .and_then(|dir| dir.entries.iter().position(|e| e.sector == sector))
            {
                self.snapshot.slot = slot + 1;
            }
            self.snapshot.dpi_index = dpi as usize;
            if before != (self.snapshot.slot, self.snapshot.dpi_index)
                && self.snapshot.settings["osd"].as_bool().unwrap_or(true)
            {
                let text = if before.0 != self.snapshot.slot {
                    format!(
                        "{} · profil {}",
                        self.current_profile()
                            .and_then(|p| p.name.as_deref())
                            .unwrap_or("G502"),
                        self.snapshot.slot
                    )
                } else {
                    format!(
                        "{} DPI",
                        self.current_profile()
                            .and_then(|p| p.dpi.get(dpi as usize))
                            .copied()
                            .unwrap_or(0)
                    )
                };
                std::thread::spawn(move || {
                    let _ = show_osd(&text);
                });
            }
        }
        Ok(())
    }
    fn rules(&mut self) -> Result<()> {
        if let Some(w) = &self.watcher {
            self.snapshot.context = w.snapshot();
        }
        let rule = self.snapshot.settings["rules"]
            .as_array()
            .and_then(|r| {
                r.iter()
                    .find(|r| context::matches(r, &self.snapshot.context))
            })
            .cloned();
        let id = rule
            .as_ref()
            .and_then(|r| r["id"].as_str())
            .map(str::to_owned);
        if id != self.rule_id {
            let old = self.snapshot.active_rule.clone();
            if let Some(slot) = rule
                .as_ref()
                .and_then(|r| r["slot"].as_u64())
                .filter(|&n| n > 0)
            {
                if self.slot_before.is_none() {
                    self.slot_before = Some(self.snapshot.slot);
                }
                if self.snapshot.connected {
                    self.activate(slot as usize)?;
                }
            } else if let Some(slot) = self.slot_before.take() {
                if old.as_ref().and_then(|r| r["slot"].as_u64()) == Some(self.snapshot.slot as u64)
                    && self.snapshot.connected
                {
                    self.activate(slot)?;
                }
            }
            self.rule_id = id;
        }
        self.snapshot.active_rule = rule;
        Ok(())
    }
    fn effects(&mut self) -> Result<()> {
        let profile = self.current_profile().cloned();
        let previous = self.live.kind.clone();
        let colors = self.live.frame(
            &self.snapshot.settings,
            self.snapshot.active_rule.as_ref(),
            &self.snapshot.context,
            profile.as_ref(),
            self.snapshot.dpi_index,
        );
        if let Some(c) = colors {
            self.snapshot.colors = Some(c);
            if self.last_colors != Some(c) || self.last_send.elapsed() > Duration::from_secs(1) {
                if let Some(d) = &mut self.device {
                    for (z, rgb) in c.iter().enumerate() {
                        d.led(z, &Led::fixed(*rgb))?;
                    }
                    self.last_colors = Some(c);
                    self.last_send = Instant::now();
                }
            }
        } else if self.live.kind.is_empty() {
            self.snapshot.colors = None;
            if !previous.is_empty() {
                self.restore_lighting()?;
                self.last_colors = None;
            }
        }
        if let Some(token) = self.live.restore_token.take() {
            if self.snapshot.settings["screen_token"].as_str() != Some(&token) {
                self.snapshot.settings["screen_token"] = token.into();
                config::save(&self.snapshot.settings)?;
            }
        }
        if let Some(error) = &self.live.error {
            self.snapshot.error = Some(error.clone());
        }
        Ok(())
    }
    fn restore_lighting(&mut self) -> Result<()> {
        let leds = self.current_profile().map(|p| p.leds.clone());
        if let (Some(d), Some(leds)) = (&mut self.device, leds) {
            for (z, led) in leds.iter().enumerate() {
                d.led(z, led)?;
            }
        }
        Ok(())
    }
    fn d(&mut self) -> Result<&mut Device> {
        self.device.as_mut().context("G502 HERO non connectée")
    }
    fn sector(&self, slot: usize) -> Result<u16> {
        self.snapshot
            .directory
            .as_ref()
            .and_then(|d| slot.checked_sub(1).and_then(|i| d.entries.get(i)))
            .map(|e| e.sector)
            .context("Profil invalide")
    }
    fn activate(&mut self, slot: usize) -> Result<()> {
        let sector = self.sector(slot)?;
        ensure!(
            self.snapshot.directory.as_ref().unwrap().entries[slot - 1].enabled,
            "Enable this profile before activating it"
        );
        self.d()?.activate(sector)?;
        self.snapshot.slot = slot;
        self.snapshot.dpi_index = self
            .current_profile()
            .map(|p| p.default_dpi as usize)
            .unwrap_or(0);
        self.last_colors = None;
        Ok(())
    }
    fn backup(&mut self, path: Option<&str>) -> Result<String> {
        let data = self.d()?.backup()?;
        let p = if let Some(path) = path {
            std::path::PathBuf::from(path)
        } else {
            config::data_dir().join("backups").join(format!(
                "onboard-{}.json",
                SystemTime::now().duration_since(UNIX_EPOCH)?.as_millis()
            ))
        };
        if let Some(parent) = p.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(&p, serde_json::to_vec_pretty(&data)?)?;
        self.backup_done = true;
        Ok(p.display().to_string())
    }
    fn before_write(&mut self) -> Result<()> {
        if !self.backup_done {
            self.backup(None)?;
        }
        Ok(())
    }
    fn write_profile(&mut self, slot: usize, mut profile: Profile) -> Result<()> {
        let sector = self.sector(slot)?;
        let bytes = profile.encode()?;
        self.before_write()?;
        self.d()?.write_sector(sector, &bytes, false)?;
        profile.raw = bytes;
        let current = slot == self.snapshot.slot;
        let dpi = self.snapshot.dpi_index as u8;
        if current {
            self.d()?.reload(dpi)?;
        }
        let mut assignments_changed = false;
        if let Some(map) = self.snapshot.settings["app_macros"].as_object_mut() {
            for (layer, bindings) in [&profile.buttons, &profile.gshift].iter().enumerate() {
                for (button, binding) in bindings.iter().enumerate() {
                    if binding[..2] != [128, 0] {
                        assignments_changed |=
                            map.remove(&format!("{slot}:{layer}:{button}")).is_some();
                    }
                }
            }
        }
        if assignments_changed {
            self.player.stop_all();
            config::save(&self.snapshot.settings)?;
            self.sync_spy()?;
        }
        self.snapshot.profiles[slot - 1] = profile;
        self.last_colors = None;
        self.snapshot.status = "Profil enregistré et vérifié sur la souris".into();
        Ok(())
    }
    fn clear_app_assignments(&mut self, slot: usize) -> Result<()> {
        if let Some(map) = self.snapshot.settings["app_macros"].as_object_mut() {
            map.retain(|k, _| !k.starts_with(&format!("{slot}:")));
        }
        config::save(&self.snapshot.settings)?;
        self.sync_spy()
    }
    fn settings(&mut self, value: Value) -> Result<()> {
        ensure!(value.is_object(), "Invalid settings");
        if let Some(macros) = value["macros"].as_array() {
            ensure!(macros.len() <= 4096, "Too many macros");
            for m in macros {
                input::expand(m, &self.typing)?;
            }
        }
        if let Some(rules) = value["rules"].as_array() {
            for r in rules {
                ensure!(
                    ["game", "app", "title", "media"]
                        .contains(&r["trigger"].as_str().unwrap_or("")),
                    "Invalid rule trigger"
                );
            }
        }
        if let Some(pages) = value["macro_pages"].as_object() {
            for page in pages.values() {
                ensure!(
                    page.as_u64()
                        .is_some_and(|n| macro_page_allowed(&self.snapshot, n)),
                    "Invalid macro page: profiles and factory memory are protected"
                );
            }
        }
        let typing = value["keyboard_layout"]
            .as_str()
            .map(input::typing_table)
            .transpose()?;
        self.player.stop_all();
        config::save(&value)?;
        if let Some(typing) = typing {
            self.typing = typing;
        }
        self.snapshot.settings = value;
        self.update_watcher();
        self.sync_spy()?;
        self.snapshot.status = "Réglages enregistrés".into();
        Ok(())
    }
    fn macro_sector(&mut self, id: &str) -> Result<u16> {
        if let Some(n) = self.snapshot.settings["macro_pages"][id].as_u64() {
            ensure!(
                macro_page_allowed(&self.snapshot, n),
                "Macro page overlaps a profile or is outside user memory"
            );
            return Ok(n as u16);
        }
        let profile_sectors: Vec<_> = self
            .snapshot
            .directory
            .as_ref()
            .context("No directory")?
            .entries
            .iter()
            .map(|e| e.sector)
            .collect();
        let count = self.d()?.info.sector_count;
        for n in 1..count as u16 {
            if profile_sectors.contains(&n) {
                continue;
            }
            let used = self.snapshot.settings["macro_pages"]
                .as_object()
                .is_some_and(|m| m.values().any(|v| v.as_u64() == Some(n as u64)));
            let referenced = self
                .snapshot
                .profiles
                .iter()
                .flat_map(|p| p.buttons.iter().chain(&p.gshift))
                .any(|b| b[0] < 128 && b[1] == n as u8);
            if !used && !referenced && self.d()?.read_sector(n)?.iter().all(|&b| b == 255) {
                return Ok(n);
            }
        }
        bail!("No free sector for an onboard macro")
    }
    fn store_macro(&mut self, id: &str, m: &Value) -> Result<u16> {
        ensure!(
            m["mode"].as_str().unwrap_or("once") == "once",
            "Onboard macros support once mode only"
        );
        let events = input::expand(m, &self.typing)?;
        let payload = input::onboard_macro(&events)?;
        let n = self.macro_sector(id)?;
        let size = self.d()?.info.sector_size;
        ensure!(payload.len() <= size - 2, "Macro too large");
        let mut page = vec![255; size];
        page[..payload.len()].copy_from_slice(&payload);
        let page = model::sealed(page)?;
        self.before_write()?;
        self.d()?.write_sector(n, &page, false)?;
        if !self.snapshot.settings["macro_pages"].is_object() {
            self.snapshot.settings["macro_pages"] = json!({});
        }
        self.snapshot.settings["macro_pages"][id] = n.into();
        Ok(n)
    }
    fn assign_macro(&mut self, a: &Value) -> Result<()> {
        let slot = a["slot"].as_u64().context("Missing slot")? as usize;
        self.sector(slot)?;
        let layer = a["layer"].as_u64().unwrap_or(0) as usize;
        let button = a["button"].as_u64().context("Missing button")? as usize;
        ensure!(layer < 2 && button < 16, "Invalid button");
        let id = a["id"].as_str().context("Missing macro id")?;
        let m = self.snapshot.settings["macros"]
            .as_array()
            .and_then(|m| m.iter().find(|m| m["id"] == id))
            .cloned()
            .context("Unknown macro")?;
        let b = if m["target"] == "mouse" {
            let n = self.store_macro(id, &m)?;
            [0, n as u8, 0, 0]
        } else {
            [128, 0, 255, 255]
        };
        let mut p = self.snapshot.profiles[slot - 1].clone();
        if layer == 0 {
            p.buttons[button] = b;
        } else {
            p.gshift[button] = b;
        }
        self.write_profile(slot, p)?;
        if !self.snapshot.settings["app_macros"].is_object() {
            self.snapshot.settings["app_macros"] = json!({});
        }
        let k = format!("{slot}:{layer}:{button}");
        if m["target"] == "mouse" {
            self.snapshot.settings["app_macros"]
                .as_object_mut()
                .unwrap()
                .remove(&k);
        } else {
            self.snapshot.settings["app_macros"][k] = id.into();
        }
        config::save(&self.snapshot.settings)?;
        self.sync_spy()?;
        Ok(())
    }
    fn command(&mut self, cmd: &str, a: Value) -> Result<Value> {
        match cmd {
            "ping" => {
                Ok(json!({"version":ipc::VERSION,"pid":std::process::id(),"implementation":"Rust"}))
            }
            "snapshot" => Ok(serde_json::to_value(&self.snapshot)?),
            "settings" => {
                self.settings(a)?;
                Ok(json!("Réglages enregistrés"))
            }
            "activate" => {
                self.activate(a["slot"].as_u64().context("Missing slot")? as usize)?;
                Ok(json!("Profil activé"))
            }
            "write_profile" => {
                let slot = a["slot"].as_u64().context("Missing slot")? as usize;
                let p: Profile = serde_json::from_value(a["profile"].clone())?;
                self.write_profile(slot, p)?;
                Ok(json!("Profil enregistré"))
            }
            "preview_dpi" => {
                let dpi = u16::try_from(a["dpi"].as_u64().context("Missing DPI")?)?;
                self.d()?.preview_dpi(dpi)?;
                Ok(Value::Null)
            }
            "dpi_index" => {
                let index = u8::try_from(a["index"].as_u64().context("Missing index")?)?;
                self.d()?.dpi_index(index)?;
                self.snapshot.dpi_index = index as usize;
                Ok(Value::Null)
            }
            "preview_led" => {
                let zone = a["zone"].as_u64().context("Missing zone")? as usize;
                let led: Led = serde_json::from_value(a["led"].clone())?;
                self.d()?.led(zone, &led)?;
                Ok(Value::Null)
            }
            "backup" => Ok(json!(self.backup(a["path"].as_str())?)),
            "export_profile" => {
                let slot = a["slot"].as_u64().context("Missing slot")? as usize;
                self.sector(slot)?;
                let p = &self.snapshot.profiles[slot - 1];
                let value = json!({"format":"g502-hub-profile","version":1,"device":"046d:c08b","app":"G502 Hub","summary":{"name":p.name,"dpi":p.dpi},"sector":model::hex(&p.encode()?)});
                let path = a["path"].as_str().context("Missing path")?;
                fs::write(path, serde_json::to_vec_pretty(&value)?)?;
                Ok(json!(path))
            }
            "import_profile" => {
                let slot = a["slot"].as_u64().context("Missing slot")? as usize;
                let path = a["path"].as_str().context("Missing path")?;
                let value: Value = serde_json::from_slice(&fs::read(path)?)?;
                ensure!(
                    value["format"] == "g502-hub-profile"
                        && value["device"] == "046d:c08b"
                        && value["version"].as_u64().unwrap_or(999) <= 1,
                    "Incompatible profile file"
                );
                let bytes =
                    model::unhex(value["sector"].as_str().context("Missing profile data")?)?;
                ensure!(model::crc_ok(&bytes), "Profile checksum mismatch");
                let mut p = Profile::decode(&bytes)?;
                for b in p.buttons.iter_mut().chain(&mut p.gshift) {
                    if b[0] < 128 {
                        *b = [128, 0, 255, 255];
                    }
                }
                self.write_profile(slot, p)?;
                self.clear_app_assignments(slot)?;
                Ok(json!("Profil importé ; macros externes désactivées"))
            }
            "restore" => {
                let value: Value = serde_json::from_slice(&fs::read(
                    a["path"].as_str().context("Missing path")?,
                )?)?;
                let size = self.d()?.info.sector_size;
                ensure!(
                    value["sector_size"].as_u64() == Some(size as u64),
                    "Backup sector size mismatch"
                );
                let sectors = value["sectors"].as_object().context("Invalid backup")?;
                let mut pages = vec![];
                let count = self.d()?.info.sector_count as u16;
                for (k, v) in sectors {
                    let n = u16::from_str_radix(k.trim_start_matches("0x"), 16)?;
                    if n >= count {
                        continue;
                    }
                    let bytes = model::unhex(v.as_str().context("Invalid sector")?)?;
                    ensure!(
                        bytes.len() == size
                            && (model::crc_ok(&bytes) || bytes.iter().all(|&b| b == 255)),
                        "Invalid backup sector {n}"
                    );
                    pages.push((n, bytes));
                }
                pages.sort_by_key(|(n, _)| if *n == 0 { u16::MAX } else { *n });
                self.backup(None)?;
                for (n, bytes) in pages {
                    if self.d()?.read_sector(n)? != bytes {
                        self.d()?.write_sector(n, &bytes, true)?;
                    }
                }
                if let Some(n) = value["current_profile"].as_u64() {
                    self.d()?.activate(u16::try_from(n)?)?;
                }
                self.connect()?;
                Ok(json!("Sauvegarde restaurée et vérifiée"))
            }
            "copy_profile" => {
                let from = a["from"].as_u64().context("Missing source")? as usize;
                let to = a["to"].as_u64().context("Missing destination")? as usize;
                self.sector(from)?;
                self.sector(to)?;
                let p = self.snapshot.profiles[from - 1].clone();
                self.write_profile(to, p)?;
                self.clear_app_assignments(to)?;
                Ok(json!("Profil copié"))
            }
            "reset_profile" => {
                let slot = a["slot"].as_u64().context("Missing slot")? as usize;
                self.sector(slot)?;
                let raw = self.d()?.read_sector(256)?;
                let dir = Directory::decode(&raw)?.context("No factory profiles")?;
                let sector = dir.entries[(slot - 1) % dir.entries.len()].sector;
                let p = self.d()?.profile(sector)?;
                self.write_profile(slot, p)?;
                self.clear_app_assignments(slot)?;
                Ok(json!("Profil usine restauré"))
            }
            "profile_enabled" => {
                let slot = a["slot"].as_u64().context("Missing slot")? as usize;
                self.sector(slot)?;
                let mut dir = self.snapshot.directory.clone().context("No directory")?;
                dir.entries[slot - 1].enabled =
                    a["enabled"].as_bool().context("Missing enabled value")?;
                let bytes = dir.encode()?;
                self.before_write()?;
                let current = self.d()?.current()?.0;
                self.d()?.write_sector(0, &bytes, false)?;
                if dir.entries.iter().any(|e| e.enabled && e.sector == current) {
                    self.d()?.activate(current)?;
                }
                self.snapshot.directory = Some(dir);
                self.poll()?;
                Ok(json!("Cycle des profils enregistré"))
            }
            "assign_macro" => {
                self.assign_macro(&a)?;
                Ok(json!("Macro assignée et vérifiée"))
            }
            "save_macro" => {
                let id = a["id"].as_str().context("Macro id missing")?.to_owned();
                input::expand(&a, &self.typing)?;
                let old_page = self.snapshot.settings["macro_pages"][&id].as_u64();
                let to_mouse = a["target"] == "mouse";
                let app_used = self.snapshot.settings["app_macros"]
                    .as_object()
                    .is_some_and(|m| m.values().any(|v| v == &id));
                let page = if to_mouse && (old_page.is_some() || app_used) {
                    Some(self.store_macro(&id, &a)?)
                } else {
                    None
                };
                let mut added = Vec::new();
                for slot in 1..=self.snapshot.profiles.len() {
                    let mut p = self.snapshot.profiles[slot - 1].clone();
                    let mut changed = false;
                    for (layer, bindings) in [&mut p.buttons, &mut p.gshift].into_iter().enumerate()
                    {
                        for (button, binding) in bindings.iter_mut().enumerate() {
                            let key = format!("{slot}:{layer}:{button}");
                            if let Some(page) = page {
                                if self.snapshot.settings["app_macros"][&key] == id {
                                    *binding = [0, page as u8, 0, 0];
                                    changed = true;
                                }
                            } else if !to_mouse
                                && old_page.is_some_and(|page| {
                                    binding[0] < 128 && binding[1] as u64 == page
                                })
                            {
                                *binding = [128, 0, 255, 255];
                                added.push(key);
                                changed = true;
                            }
                        }
                    }
                    if changed {
                        self.write_profile(slot, p)?;
                    }
                }
                let mut settings = self.snapshot.settings.clone();
                if !settings["app_macros"].is_object() {
                    settings["app_macros"] = json!({});
                }
                if to_mouse {
                    settings["app_macros"]
                        .as_object_mut()
                        .unwrap()
                        .retain(|_, v| v != &id);
                } else {
                    for key in added {
                        settings["app_macros"][key] = id.clone().into();
                    }
                }
                if !settings["macros"].is_array() {
                    settings["macros"] = json!([]);
                }
                let list = settings["macros"].as_array_mut().unwrap();
                if let Some(i) = list.iter().position(|m| m["id"] == id) {
                    list[i] = a;
                } else {
                    list.push(a);
                }
                self.settings(settings)?;
                Ok(json!("Macro enregistrée"))
            }
            "delete_macro" => {
                let id = a["id"].as_str().context("Missing macro id")?;
                let page = self.snapshot.settings["macro_pages"][id].as_u64();
                if let Some(page) = page {
                    ensure!(
                        macro_page_allowed(&self.snapshot, page),
                        "Protected profile sector cannot be erased as a macro"
                    );
                    for slot in 1..=self.snapshot.profiles.len() {
                        let mut p = self.snapshot.profiles[slot - 1].clone();
                        let mut change = false;
                        for b in p.buttons.iter_mut().chain(&mut p.gshift) {
                            if b[0] < 128 && b[1] as u64 == page {
                                *b = [128, 0, 255, 255];
                                change = true;
                            }
                        }
                        if change {
                            self.write_profile(slot, p)?;
                        }
                    }
                }
                let mut settings = self.snapshot.settings.clone();
                if let Some(list) = settings["macros"].as_array_mut() {
                    list.retain(|m| m["id"] != id);
                }
                if let Some(map) = settings["app_macros"].as_object_mut() {
                    map.retain(|_, v| v != id);
                }
                if let Some(map) = settings["macro_pages"].as_object_mut() {
                    map.remove(id);
                }
                self.settings(settings)?;
                if let Some(page) = page {
                    let size = self.d()?.info.sector_size;
                    self.d()?
                        .write_sector(u16::try_from(page)?, &vec![255; size], true)?;
                }
                Ok(json!("Macro supprimée"))
            }
            "bridge_prefixes" => Ok(json!(crate::bridge::prefixes())),
            "bridge_install" => {
                crate::bridge::install(
                    std::path::Path::new(a["path"].as_str().context("Missing prefix")?),
                    &crate::bridge::bin_dir(),
                )?;
                Ok(json!("Intégration LIGHTSYNC installée"))
            }
            "bridge_remove" => {
                crate::bridge::uninstall(std::path::Path::new(
                    a["path"].as_str().context("Missing prefix")?,
                ))?;
                Ok(json!("Intégration LIGHTSYNC retirée"))
            }
            "games" => Ok(serde_json::to_value(context::installed_games())?),
            "install_gsi" => Ok(json!(context::install_gsi(false)?)),
            "remove_gsi" => Ok(json!(context::install_gsi(true)?)),
            "refresh" => {
                self.player.stop_all();
                self.spy = None;
                self.connect()?;
                Ok(Value::Null)
            }
            "choose_screen" => {
                let mut s = self.snapshot.settings.clone();
                s["screen_token"] = Value::Null;
                s["live"]["effect"] = json!("screen");
                s["live"]["on"] = json!(true);
                self.settings(s)?;
                self.live.choose_screen();
                Ok(Value::Null)
            }
            "lighting" => {
                let mut s = self.snapshot.settings.clone();
                if !s["live"].is_object() {
                    s["live"] = json!({});
                }
                s["live"]["on"] = a["on"].clone();
                if let Some(effect) = a["effect"].as_str() {
                    ensure!(
                        ["screen", "audio", "wave", "dpi"].contains(&effect),
                        "Unknown effect"
                    );
                    s["live"]["effect"] = effect.into();
                }
                self.settings(s)?;
                Ok(Value::Null)
            }
            other => bail!("Unknown command {other}"),
        }
    }
    fn stop(&mut self) {
        self.player.stop_all();
        let _ = self.restore_lighting();
        if let Some(d) = &mut self.device {
            if self.spy.is_some() {
                let _ = d.spy_stop();
            }
        }
    }
}
fn show_osd(text: &str) -> Result<()> {
    let c = zbus::blocking::Connection::session()?;
    let p = zbus::blocking::Proxy::new(
        &c,
        "org.kde.plasmashell",
        "/org/kde/osdService",
        "org.kde.osdService",
    )?;
    let _: () = p.call("showText", &("input-mouse", text))?;
    Ok(())
}
static STOP: AtomicBool = AtomicBool::new(false);
extern "C" fn signal_handler(_: libc::c_int) {
    STOP.store(true, Ordering::Relaxed);
}
pub fn run() -> Result<()> {
    let _lock = config::lock("service.lock")?;
    let socket = ipc::socket()?;
    if socket.exists() {
        fs::remove_file(&socket)?;
    }
    let mut e = Engine::new()?;
    if let Err(error) = e.connect() {
        e.lost(error);
    }
    let listener = UnixListener::bind(&socket)?;
    listener.set_nonblocking(true)?;
    unsafe {
        libc::signal(libc::SIGTERM, signal_handler as *const () as usize);
        libc::signal(libc::SIGINT, signal_handler as *const () as usize);
    }
    let mut last_poll = Instant::now();
    let mut last_rule = Instant::now();
    let mut last_effect = Instant::now();
    let mut reconnect = Instant::now();
    while !STOP.load(Ordering::Relaxed) {
        if e.device.is_none() && reconnect.elapsed() > Duration::from_secs(2) {
            reconnect = Instant::now();
            if let Err(error) = e.connect() {
                e.lost(error);
            }
        }
        let fd = e
            .device
            .as_ref()
            .map(|d| d.hid.file.as_raw_fd())
            .unwrap_or(-1);
        let mut fds = [
            libc::pollfd {
                fd: listener.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
            libc::pollfd {
                fd,
                events: libc::POLLIN,
                revents: 0,
            },
        ];
        let tick = if e.live.kind.is_empty()
            && e.snapshot.settings["live"]["on"] != true
            && e.snapshot
                .active_rule
                .as_ref()
                .is_none_or(|r| r["lighting"].is_null())
        {
            Duration::from_millis(250)
        } else {
            Duration::from_millis(33)
        };
        let next = if tick.as_millis() == 33 {
            last_effect + tick
        } else {
            last_poll + tick
        };
        let timeout = next
            .saturating_duration_since(Instant::now())
            .as_millis()
            .min(250) as i32;
        unsafe {
            libc::poll(fds.as_mut_ptr(), 2, timeout);
        }
        if fds[1].revents != 0 {
            if let Err(error) = e.events() {
                e.lost(error);
            }
        }
        if fds[0].revents & libc::POLLIN != 0 {
            while let Ok((mut stream, _)) = listener.accept() {
                let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
                let _ = stream.set_write_timeout(Some(Duration::from_secs(2)));
                let result = (|| -> Result<Value> {
                    let mut line = String::new();
                    BufReader::new(&stream)
                        .take(ipc::MAX as u64)
                        .read_line(&mut line)?;
                    ensure!(line.ends_with('\n'), "Incomplete request");
                    let request: ipc::Request = serde_json::from_str(&line)?;
                    ensure!(request.version == ipc::VERSION, "Incompatible protocol");
                    if request.command == "stop" {
                        STOP.store(true, Ordering::Relaxed);
                        Ok(json!("Service stopped"))
                    } else {
                        e.command(&request.command, request.args)
                    }
                })();
                let response = match result {
                    Ok(value) => json!({"result":value}),
                    Err(error) => {
                        e.snapshot.status = error.to_string();
                        json!({"error":error.to_string()})
                    }
                };
                if let Ok(mut bytes) = serde_json::to_vec(&response) {
                    bytes.push(b'\n');
                    let _ = stream.write_all(&bytes);
                }
            }
        }
        if last_poll.elapsed() >= Duration::from_millis(250) {
            last_poll = Instant::now();
            if let Err(error) = e.poll() {
                e.lost(error);
            }
            if let Err(error) = e.events() {
                e.lost(error);
            }
        }
        if last_rule.elapsed() >= Duration::from_millis(300) {
            last_rule = Instant::now();
            if let Err(error) = e.rules() {
                e.snapshot.error = Some(error.to_string());
            }
        }
        if last_effect.elapsed() >= tick {
            last_effect = Instant::now();
            if let Err(error) = e.effects() {
                e.snapshot.error = Some(error.to_string());
            }
        }
    }
    e.stop();
    let _ = fs::remove_file(socket);
    Ok(())
}

fn macro_page_allowed(snapshot: &Snapshot, page: u64) -> bool {
    page > 0
        && snapshot
            .info
            .as_ref()
            .is_some_and(|i| page < i.sector_count as u64)
        && snapshot
            .directory
            .as_ref()
            .is_some_and(|d| !d.entries.iter().any(|e| e.sector as u64 == page))
}
#[cfg(test)]
mod memory_guard_tests {
    use super::*;
    #[test]
    fn macros_cannot_overwrite_profiles_or_factory_memory() {
        let mut snapshot = Snapshot::default();
        snapshot.info = Some(Info {
            profile_format: 2,
            macro_format: 1,
            profile_count: 5,
            rom_profile_count: 5,
            button_count: 11,
            sector_count: 10,
            sector_size: 255,
        });
        snapshot.directory = Some(Directory {
            entries: (1..=5)
                .map(|sector| crate::model::Entry {
                    sector,
                    enabled: true,
                    flag: 0,
                })
                .collect(),
            terminator: [255, 255, 0, 0],
            raw: vec![],
        });
        for page in [0, 1, 2, 3, 4, 5, 10, 256] {
            assert!(!macro_page_allowed(&snapshot, page));
        }
        for page in [6, 7, 8, 9] {
            assert!(macro_page_allowed(&snapshot, page));
        }
    }
}
