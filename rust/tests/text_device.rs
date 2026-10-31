//! Opt-in kernel test. Grabs only its newly-created virtual device before sending keys.
use g502_hub::input::{self, Event, Player};
use serde_json::json;
use std::{
    collections::HashSet,
    fs::{self, File},
    io::Read,
    os::fd::AsRawFd,
    path::PathBuf,
    time::{Duration, Instant},
};
struct Grab {
    file: File,
    player: Player,
}
impl Drop for Grab {
    fn drop(&mut self) {
        self.player.stop_all();
        unsafe {
            libc::ioctl(self.file.as_raw_fd(), 0x40044590 as libc::c_ulong, 0);
        }
    }
}
fn devices() -> HashSet<PathBuf> {
    fs::read_dir("/sys/class/input")
        .unwrap()
        .flatten()
        .filter(|e| e.file_name().to_string_lossy().starts_with("event"))
        .map(|e| e.path())
        .collect()
}
#[test]
#[ignore = "requires /dev/uinput and access to its new /dev/input/event node"]
fn text_reaches_the_kernel_after_button_release() {
    let before = devices();
    let mut player = Player::default();
    player
        .press("initialize".into(), vec![Event::Wait(600000)], "once")
        .unwrap();
    let start = Instant::now();
    let device = loop {
        if let Some(path) = devices()
            .difference(&before)
            .find(|p| {
                fs::read_to_string(p.join("device/name"))
                    .is_ok_and(|name| name.trim() == "G502 Hub macros")
            })
            .cloned()
        {
            break path;
        }
        assert!(start.elapsed() < Duration::from_secs(3));
        std::thread::sleep(Duration::from_millis(10));
    };
    let file = File::open(PathBuf::from("/dev/input").join(device.file_name().unwrap())).unwrap();
    assert_eq!(
        unsafe { libc::ioctl(file.as_raw_fd(), 0x40044590 as libc::c_ulong, 1) },
        0,
        "Cannot grab own test keyboard; no text has been sent"
    );
    let mut grab = Grab { file, player };
    grab.player.stop_all();
    let typing = input::typing_table("fr+latin9").unwrap();
    let m =
        json!({"mode":"once","steps":[{"kind":"text","args":{"text":"Bonjour 123 @ test.fr"}}]});
    let events = input::expand(&m, &typing).unwrap();
    let expected: Vec<_> = events
        .iter()
        .filter_map(|e| match e {
            Event::Key(code, down) => Some((*code, i32::from(*down))),
            _ => None,
        })
        .collect();
    grab.player.press("text".into(), events, "once").unwrap();
    grab.player.release("text");
    let mut actual = vec![];
    while actual.len() < expected.len() {
        let mut poll = libc::pollfd {
            fd: grab.file.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        assert!(
            unsafe { libc::poll(&mut poll, 1, 2000) } > 0,
            "Keyboard events stopped before text completed"
        );
        let mut bytes = vec![0; std::mem::size_of::<libc::input_event>()];
        grab.file.read_exact(&mut bytes).unwrap();
        let e = unsafe { std::ptr::read_unaligned(bytes.as_ptr().cast::<libc::input_event>()) };
        if e.type_ == 1 {
            actual.push((e.code, e.value));
        }
    }
    grab.player.stop_all();
    assert_eq!(actual, expected);
    assert!(grab.player.error.lock().unwrap().is_none());
    println!(
        "Complete text macro: {} key events delivered through uinput after trigger release",
        actual.len()
    );
}
