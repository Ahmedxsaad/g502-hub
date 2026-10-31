//! Wine/Proton SDK registration. The receiver is Rust; existing SDK bridge DLLs
//! use the published upstream wire protocol and can be reused without Python.
use crate::{config, context};
use anyhow::{Context, Result, ensure};
use serde_json::{Value, json};
use std::{
    collections::HashMap,
    fs,
    path::{Path, PathBuf},
};
const CLSID: &str = "{a6519e67-7632-4375-afdf-caa889744403}";
fn latin(bytes: &[u8]) -> String {
    bytes.iter().map(|&b| char::from(b)).collect()
}
fn write_latin(path: &Path, text: &str) -> Result<()> {
    let data: Result<Vec<u8>> = text.chars().map(|c| Ok(u8::try_from(c as u32)?)).collect();
    let tmp = path.with_extension("rust-tmp");
    fs::write(&tmp, data?)?;
    fs::rename(tmp, path)?;
    Ok(())
}
fn blocks(text: &str) -> (String, Vec<String>) {
    let mut preamble = String::new();
    let mut blocks: Vec<String> = vec![];
    for line in text.split_inclusive('\n') {
        if line.starts_with('[') {
            blocks.push(line.into());
        } else if let Some(b) = blocks.last_mut() {
            b.push_str(line);
        } else {
            preamble.push_str(line);
        }
    }
    (preamble, blocks)
}
fn key(block: &str) -> String {
    let first = block.lines().next().unwrap_or("");
    first
        .strip_prefix('[')
        .and_then(|s| s.rsplit_once(']').map(|(s, _)| s))
        .unwrap_or("")
        .to_lowercase()
}
fn value(block: &str) -> Option<String> {
    block.lines().find_map(|line| {
        line.strip_prefix("@=\"")
            .and_then(|s| s.strip_suffix('"'))
            .map(|s| s.replace("\\\\", "\\"))
    })
}
fn layout(pfx: &Path, text: &str) -> Vec<(String, String, &'static str, PathBuf)> {
    let base = format!("Software\\\\Classes\\\\CLSID\\\\{CLSID}\\\\ServerBinary");
    let x86 = text.lines().any(|l| l == "#arch=win32");
    let mut list = vec![(
        base,
        "C:\\Program Files\\G502 Hub Rust\\LogitechLed.dll".into(),
        if x86 { "x86" } else { "x64" },
        pfx.join("drive_c/Program Files/G502 Hub Rust/LogitechLed.dll"),
    )];
    if !x86 {
        list.push((
            format!("Software\\\\Classes\\\\Wow6432Node\\\\CLSID\\\\{CLSID}\\\\ServerBinary"),
            "C:\\Program Files (x86)\\G502 Hub Rust\\LogitechLed.dll".into(),
            "x86",
            pfx.join("drive_c/Program Files (x86)/G502 Hub Rust/LogitechLed.dll"),
        ));
    }
    list
}
pub fn active(pfx: &Path) -> bool {
    let pfx = pfx.canonicalize().unwrap_or_else(|_| pfx.to_path_buf());
    if let Ok(entries) = fs::read_dir("/proc") {
        for e in entries.flatten() {
            if e.file_name().to_string_lossy().parse::<u32>().is_err() {
                continue;
            }
            if let Ok(bytes) = fs::read(e.path().join("environ")) {
                for item in bytes.split(|&b| b == 0) {
                    let target = if let Some(v) = item.strip_prefix(b"WINEPREFIX=") {
                        Some(PathBuf::from(String::from_utf8_lossy(v).as_ref()))
                    } else {
                        item.strip_prefix(b"STEAM_COMPAT_DATA_PATH=")
                            .map(|v| PathBuf::from(String::from_utf8_lossy(v).as_ref()).join("pfx"))
                    };
                    if let Some(path) = target {
                        if path.canonicalize().unwrap_or(path) == pfx {
                            return true;
                        }
                    }
                }
            }
        }
    }
    use std::os::unix::fs::MetadataExt;
    if let Ok(meta) = fs::metadata(&pfx) {
        let lock = PathBuf::from(format!(
            "/tmp/.wine-{}/server-{:x}-{:x}/lock",
            unsafe { libc::getuid() },
            meta.dev(),
            meta.ino()
        ));
        if let (Ok(m), Ok(locks)) = (fs::metadata(lock), fs::read_to_string("/proc/locks")) {
            let tag = format!(
                "{:02x}:{:02x}:{}",
                libc::major(m.dev()),
                libc::minor(m.dev()),
                m.ino()
            );
            if locks.split_whitespace().any(|s| s == tag) {
                return true;
            }
        }
    }
    false
}
pub fn installed(pfx: &Path) -> bool {
    let Ok(raw) = fs::read(pfx.join("system.reg")) else {
        return false;
    };
    let text = latin(&raw);
    let (_, b) = blocks(&text);
    layout(pfx, &text).iter().all(|(k, path, _, file)| {
        file.is_file()
            && b.iter()
                .find(|b| key(b) == k.to_lowercase())
                .and_then(|b| value(b))
                .is_some_and(|v| v.eq_ignore_ascii_case(path))
    })
}
pub fn prefixes() -> Vec<Value> {
    let games: HashMap<_, _> = context::installed_games()
        .into_iter()
        .map(|g| (g.appid, g.name))
        .collect();
    let mut list = vec![];
    for lib in context::libraries() {
        if let Ok(entries) = fs::read_dir(lib.join("steamapps/compatdata")) {
            for entry in entries.flatten() {
                if let Ok(id) = entry.file_name().to_string_lossy().parse::<u32>() {
                    let pfx = entry.path().join("pfx");
                    if pfx.join("system.reg").is_file() {
                        list.push(json!({"appid":id,"name":games.get(&id).cloned().unwrap_or(format!("Jeu non-Steam {id}")),"path":pfx,"installed":installed(&pfx)}));
                    }
                }
            }
        }
    }
    list
}
pub fn bin_dir() -> PathBuf {
    std::env::var_os("G502_RUST_BRIDGE_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| config::data_dir().join("bridge_bin"))
}
pub fn install(pfx: &Path, bin: &Path) -> Result<()> {
    ensure!(
        !active(pfx),
        "Ferme le jeu et Wine avant de modifier son préfixe"
    );
    let reg = pfx.join("system.reg");
    let original = fs::read(&reg).context("Ce dossier n’est pas un préfixe Wine")?;
    let text = latin(&original);
    let entries = layout(pfx, &text);
    for (_, _, arch, _) in &entries {
        ensure!(
            bin.join(arch).join("LogitechLed.dll").is_file(),
            "Bridge DLL {arch} missing"
        );
    }
    let marker = entries[0]
        .3
        .parent()
        .unwrap()
        .join("g502hub-rust-lightsync.json");
    let mut info: Value = if marker.exists() {
        serde_json::from_slice(&fs::read(&marker)?)?
    } else {
        json!({"replaced":{},"files":[],"version":1})
    };
    let (preamble, mut sections) = blocks(&text);
    for (k, path, _, _) in &entries {
        let section = format!("[{k}]\n@=\"{}\"\n\n", path.replace('\\', "\\\\"));
        if let Some(i) = sections.iter().position(|b| key(b) == k.to_lowercase()) {
            if value(&sections[i]).is_some_and(|v| v.eq_ignore_ascii_case(path)) {
                continue;
            }
            if info["replaced"][k].is_null() {
                info["replaced"][k] = sections[i].clone().into();
            }
            sections[i] = section;
        } else {
            sections.push(format!("\n{section}"));
        }
    }
    let backup = pfx.join("system.reg.g502hub-rust.bak");
    if !backup.exists() {
        fs::write(&backup, &original)?;
    }
    let mut files = vec![];
    for (_, _, arch, dest) in entries {
        fs::create_dir_all(dest.parent().unwrap())?;
        fs::copy(bin.join(arch).join("LogitechLed.dll"), &dest)?;
        files.push(dest.strip_prefix(pfx)?.display().to_string());
    }
    info["files"] = json!(files);
    fs::write(marker, serde_json::to_vec_pretty(&info)?)?;
    write_latin(&reg, &format!("{preamble}{}", sections.join("")))?;
    Ok(())
}
pub fn uninstall(pfx: &Path) -> Result<()> {
    ensure!(
        !active(pfx),
        "Ferme le jeu et Wine avant de modifier son préfixe"
    );
    let reg = pfx.join("system.reg");
    let text = latin(&fs::read(&reg)?);
    let entries = layout(pfx, &text);
    let marker = entries[0]
        .3
        .parent()
        .unwrap()
        .join("g502hub-rust-lightsync.json");
    ensure!(
        marker.exists(),
        "Ce préfixe n’a pas été modifié par la version Rust"
    );
    let info: Value = serde_json::from_slice(&fs::read(&marker)?)?;
    let (pre, sections) = blocks(&text);
    let mut out = pre;
    for block in sections {
        let ours = entries.iter().find(|(k, path, _, _)| {
            key(&block) == k.to_lowercase()
                && value(&block).is_some_and(|v| v.eq_ignore_ascii_case(path))
        });
        if let Some((k, _, _, _)) = ours {
            if let Some(old) = info["replaced"][k].as_str() {
                out.push_str(old);
            }
        } else {
            out.push_str(&block);
        }
    }
    write_latin(&reg, &out)?;
    for (_, _, _, file) in entries {
        if file.exists() {
            fs::remove_file(&file)?;
        }
        let _ = fs::remove_dir(file.parent().unwrap());
    }
    fs::remove_file(marker)?;
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn latin_registry_and_other_blocks_are_preserved() {
        let text = latin(b"WINE REGISTRY Version 2\n#arch=win64\n\n[Other] 1\n@=\"caf\xe9\"\n");
        let (p, b) = blocks(&text);
        assert_eq!(format!("{p}{}", b.join("")), text);
        assert_eq!(key(&b[0]), "other");
        assert_eq!(value(&b[0]), Some("café".into()));
    }
    #[test]
    fn prefix_architecture_selects_both_dlls() {
        assert_eq!(layout(Path::new("/fake"), "#arch=win64").len(), 2);
        assert_eq!(layout(Path::new("/fake"), "#arch=win32")[0].2, "x86");
    }
}
