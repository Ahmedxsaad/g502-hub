use serde_json::{Value, json};
use std::{
    fs,
    io::{BufRead, BufReader, Write},
    os::unix::{fs::PermissionsExt, net::UnixStream},
    path::PathBuf,
    process::{Child, Command, Stdio},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
struct Service {
    child: Child,
    root: PathBuf,
}
impl Drop for Service {
    fn drop(&mut self) {
        let _ = self.rpc("stop", json!({}));
        let start = Instant::now();
        while start.elapsed() < Duration::from_secs(5) {
            if self.child.try_wait().unwrap().is_some() {
                let _ = fs::remove_dir_all(&self.root);
                return;
            }
            std::thread::sleep(Duration::from_millis(20));
        }
        let _ = self.child.kill();
        let _ = self.child.wait();
        let _ = fs::remove_dir_all(&self.root);
    }
}
impl Service {
    fn rpc(&self, command: &str, args: Value) -> Value {
        let mut s = UnixStream::connect(self.root.join("run/g502-hub-rust/service.sock")).unwrap();
        s.set_read_timeout(Some(Duration::from_secs(3))).unwrap();
        writeln!(s, "{}", json!({"version":1,"command":command,"args":args})).unwrap();
        let mut line = String::new();
        BufReader::new(s).read_line(&mut line).unwrap();
        serde_json::from_str(&line).unwrap()
    }
}
#[test]
fn native_service_lifecycle_and_rejected_commands() {
    let root = std::env::temp_dir().join(format!(
        "g502-rust-test-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(root.join("run")).unwrap();
    fs::set_permissions(root.join("run"), fs::Permissions::from_mode(0o700)).unwrap();
    fs::create_dir_all(root.join("devices")).unwrap();
    let bin = env!("CARGO_BIN_EXE_g502-hubd");
    let child = Command::new(bin)
        .env("XDG_RUNTIME_DIR", root.join("run"))
        .env("XDG_CONFIG_HOME", root.join("config"))
        .env("G502_RUST_HIDRAW_ROOT", root.join("devices"))
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    let service = Service { child, root };
    let start = Instant::now();
    while !service.root.join("run/g502-hub-rust/service.sock").exists() {
        assert!(start.elapsed() < Duration::from_secs(10));
        std::thread::sleep(Duration::from_millis(20));
    }
    let ping = service.rpc("ping", json!({}));
    assert_eq!(ping["result"]["implementation"], "Rust");
    let pid = ping["result"]["pid"].clone();
    let snapshot = service.rpc("snapshot", json!({}));
    assert_eq!(snapshot["result"]["connected"], false);
    assert!(service.rpc("unknown", json!({}))["error"].is_string());
    assert!(service.rpc("write_profile", json!({"slot":1,"profile":{}}))["error"].is_string());
    assert!(
        service.rpc(
            "settings",
            json!({"macros":[{"steps":[{"kind":"bad","args":{}}]}]})
        )["error"]
            .is_string()
    );
    assert!(
        service.rpc(
            "settings",
            json!({"macros":[],"rules":[],"live":{"on":false}})
        )["error"]
            .is_null()
    );
    let second = Command::new(bin)
        .env("XDG_RUNTIME_DIR", service.root.join("run"))
        .env("XDG_CONFIG_HOME", service.root.join("config"))
        .env("G502_RUST_HIDRAW_ROOT", service.root.join("devices"))
        .output()
        .unwrap();
    assert!(!second.status.success());
    assert_eq!(service.rpc("ping", json!({}))["result"]["pid"], pid);
}
