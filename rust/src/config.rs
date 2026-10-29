use anyhow::{Result, ensure};
use serde_json::{Value, json};
use std::{
    fs::{self, File, OpenOptions},
    os::{fd::AsRawFd, unix::fs::PermissionsExt},
    path::PathBuf,
};
pub fn config_dir() -> PathBuf {
    std::env::var_os("XDG_CONFIG_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| home().join(".config"))
        .join("g502-hub-rust")
}
pub fn home() -> PathBuf {
    std::env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/tmp"))
}
pub fn data_dir() -> PathBuf {
    std::env::var_os("XDG_DATA_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| home().join(".local/share"))
        .join("g502-hub-rust")
}
pub fn runtime() -> Result<PathBuf> {
    let root = std::env::var_os("XDG_RUNTIME_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            PathBuf::from(format!("/tmp/g502-hub-rust-{}", unsafe { libc::getuid() }))
        })
        .join("g502-hub-rust");
    if !root.exists() {
        fs::create_dir_all(&root)?;
        fs::set_permissions(&root, fs::Permissions::from_mode(0o700))?;
    }
    use std::os::unix::fs::MetadataExt;
    let m = fs::symlink_metadata(&root)?;
    ensure!(
        m.is_dir() && m.uid() == unsafe { libc::getuid() } && m.mode() & 0o077 == 0,
        "Unsafe runtime directory"
    );
    Ok(root)
}
pub fn load() -> Result<Value> {
    let p = config_dir().join("settings.json");
    if p.exists() {
        Ok(serde_json::from_slice(&fs::read(p)?)?)
    } else {
        Ok(
            json!({"macros":[],"app_macros":{},"rules":[],"live":{"on":false,"effect":"wave","options":{}}}),
        )
    }
}
pub fn save(value: &Value) -> Result<()> {
    ensure!(value.is_object(), "Settings must be an object");
    let p = config_dir();
    fs::create_dir_all(&p)?;
    let lock = File::create(p.join("settings.lock"))?;
    ensure!(
        unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_EX) } == 0,
        "Settings lock failed"
    );
    let tmp = p.join("settings.tmp");
    fs::write(&tmp, serde_json::to_vec_pretty(value)?)?;
    fs::set_permissions(&tmp, fs::Permissions::from_mode(0o600))?;
    fs::rename(tmp, p.join("settings.json"))?;
    Ok(())
}
pub fn import_python() -> Result<()> {
    if config_dir().join("settings.json").exists() {
        return Ok(());
    }
    let p = std::env::var_os("XDG_CONFIG_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| home().join(".config"))
        .join("g502-hub/settings.json");
    if p.exists() {
        let value: Value = serde_json::from_slice(&fs::read(p)?)?;
        save(&value)?;
    }
    Ok(())
}
pub fn lock(name: &str) -> Result<File> {
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(runtime()?.join(name))?;
    ensure!(
        unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } == 0,
        "G502 Hub Rust is already running"
    );
    Ok(file)
}

pub fn autostart_path() -> PathBuf {
    std::env::var_os("XDG_CONFIG_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| home().join(".config"))
        .join("autostart/g502-hub-rust.desktop")
}
pub fn autostart(on: bool) -> Result<()> {
    let p = autostart_path();
    let old = p.with_file_name("g502-hub.desktop");
    let disabled = p.with_file_name("g502-hub.desktop.rust-disabled");
    if on {
        let exe = std::env::current_exe()?;
        fs::create_dir_all(p.parent().unwrap())?;
        if old.exists() && !disabled.exists() {
            fs::rename(&old, &disabled)?;
        }
        fs::write(
            p,
            format!(
                "[Desktop Entry]\nType=Application\nName=G502 Hub Rust\nExec=\"{}\" --background --take-over\nIcon=input-mouse\nTerminal=false\nX-GNOME-Autostart-enabled=true\n",
                exe.display()
                    .to_string()
                    .replace('\\', "\\\\")
                    .replace('"', "\\\"")
            ),
        )?;
    } else {
        if p.exists() {
            fs::remove_file(&p)?;
        }
        if disabled.exists() && !old.exists() {
            fs::rename(disabled, old)?;
        }
    }
    Ok(())
}
