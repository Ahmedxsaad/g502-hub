use crate::config;
use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    io::{BufRead, BufReader, Read, Write},
    os::unix::net::UnixStream,
    path::PathBuf,
    process::{Command, Stdio},
    time::{Duration, Instant},
};
pub const VERSION: u32 = 1;
pub const MAX: usize = 2 * 1024 * 1024;
#[derive(Debug, Serialize, Deserialize)]
pub struct Request {
    pub version: u32,
    pub command: String,
    #[serde(default)]
    pub args: Value,
}
pub fn socket() -> Result<PathBuf> {
    Ok(config::runtime()?.join("service.sock"))
}
pub fn request(command: &str, args: Value) -> Result<Value> {
    let mut sock = UnixStream::connect(socket()?)?;
    sock.set_read_timeout(Some(Duration::from_secs(30)))?;
    sock.set_write_timeout(Some(Duration::from_secs(5)))?;
    let mut bytes = serde_json::to_vec(&Request {
        version: VERSION,
        command: command.into(),
        args,
    })?;
    ensure!(bytes.len() < MAX, "Request too large");
    bytes.push(b'\n');
    sock.write_all(&bytes)?;
    let mut line = String::new();
    BufReader::new(sock).take(MAX as u64).read_line(&mut line)?;
    ensure!(line.ends_with('\n'), "Incomplete service response");
    let v: Value = serde_json::from_str(&line)?;
    if let Some(e) = v["error"].as_str() {
        bail!("{e}");
    }
    Ok(v["result"].clone())
}
pub fn ensure_service() -> Result<()> {
    if request("ping", json!({})).is_ok() {
        return Ok(());
    }
    let dir = std::env::current_exe()?
        .parent()
        .context("No executable directory")?
        .to_owned();
    let log = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(config::runtime()?.join("service.log"))?;
    use std::os::unix::process::CommandExt;
    let mut command = Command::new(dir.join("g502-hubd-rust"));
    command
        .stdin(Stdio::null())
        .stdout(log.try_clone()?)
        .stderr(log);
    // The service must outlive both the GUI and the launching terminal.
    unsafe {
        command.pre_exec(|| {
            if libc::setsid() < 0 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }
    let mut child = command.spawn()?;
    let start = Instant::now();
    while start.elapsed() < Duration::from_secs(20) {
        if request("ping", json!({})).is_ok() {
            return Ok(());
        }
        if start.elapsed() > Duration::from_secs(1) && child.try_wait()?.is_some() {
            bail!("Rust service exited during startup; see service.log");
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    bail!("Rust service did not start; see service.log")
}
/// One-time test handover uses the Python service's public JSON protocol,
/// without loading or invoking any Python code in the Rust application.
pub fn stop_python() -> Result<()> {
    // The test launcher explicitly hands over from the previous installation.
    // Close its graphical client first so it cannot restart the old service.
    for entry in std::fs::read_dir("/proc")?.flatten() {
        if let Ok(pid) = entry.file_name().to_string_lossy().parse::<i32>() {
            if let Ok(bytes) = std::fs::read(entry.path().join("cmdline")) {
                let args: Vec<_> = bytes.split(|&b| b == 0).collect();
                if args
                    .windows(2)
                    .any(|a| a[0] == b"-m" && a[1] == b"g502hub.gui")
                {
                    unsafe {
                        libc::kill(pid, libc::SIGTERM);
                    }
                }
            }
        }
    }

    let runtime = std::env::var_os("XDG_RUNTIME_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(format!("/tmp/g502hub-{}", unsafe { libc::getuid() })));
    let path = runtime.join("g502-hub/service.sock");
    if let Ok(mut sock) = UnixStream::connect(path) {
        sock.set_read_timeout(Some(Duration::from_secs(5)))?;
        sock.write_all(b"{\"version\":1,\"command\":\"stop\",\"args\":{\"tuple\":[]},\"kwargs\":{\"dict\":[]}}\n")?;
        let mut reply = String::new();
        BufReader::new(sock)
            .take(MAX as u64)
            .read_line(&mut reply)?;
        std::thread::sleep(Duration::from_millis(500));
    }
    Ok(())
}
