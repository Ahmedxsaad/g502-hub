//! Desktop helpers run outside the hardware service.
use crate::config;
use anyhow::{Context, Result, ensure};
use std::{
    fs,
    io::Write,
    path::PathBuf,
    process::{Command, Stdio},
};
pub const UDEV_RULE: &str = include_str!("../udev/70-g502-hub.rules");
pub fn photo_path() -> PathBuf {
    std::env::var_os("XDG_DATA_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| config::home().join(".local/share"))
        .join("g502-hub/g502-hero.png")
}
pub fn prepare_photo(bytes: &[u8]) -> Result<image::RgbaImage> {
    let image = image::load_from_memory(bytes)?;
    ensure!(
        image.width() == 2500 && image.height() == 2160,
        "Unexpected Logitech image dimensions; the product photo may have changed"
    );
    Ok(image
        .crop_imm(730, 130, 1030, 1850)
        .resize_exact(618, 1110, image::imageops::FilterType::Lanczos3)
        .to_rgba8())
}
pub fn download_photo() -> Result<String> {
    let output=Command::new("curl").args(["--fail","--location","--max-time","30","--max-filesize","25000000","--user-agent","Mozilla/5.0","https://resource.logitechg.com/f_png,q_auto/content/dam/gaming/en/non-braid/hyjal-g502-hero/2025/g502-hero-mouse-top-angle-gallery-1.png"]).output().context("Install curl to download the mouse picture")?;
    ensure!(
        output.status.success(),
        "Photo download failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let image = prepare_photo(&output.stdout)?;
    let path = photo_path();
    fs::create_dir_all(path.parent().unwrap())?;
    let tmp = path.with_extension("part.png");
    image.save(&tmp)?;
    fs::rename(tmp, &path)?;
    Ok(format!("Photo saved to {}", path.display()))
}
pub fn access_status() -> &'static str {
    let mut status = "missing";
    for path in [
        "/etc/udev/rules.d/70-g502-hub.rules",
        "/usr/lib/udev/rules.d/70-g502-hub.rules",
    ] {
        if let Ok(text) = fs::read_to_string(path) {
            if text == UDEV_RULE {
                return "current";
            }
            status = "old";
        }
    }
    if status == "old"
        && fs::OpenOptions::new()
            .write(true)
            .open("/dev/uinput")
            .is_ok()
    {
        "current"
    } else {
        status
    }
}
pub fn fix_access() -> Result<String> {
    // Fixed script and rule bytes, never interpolated user paths or values.
    let mut child=Command::new("pkexec").args(["sh","-c","cat > /etc/udev/rules.d/70-g502-hub.rules && chmod 644 /etc/udev/rules.d/70-g502-hub.rules && udevadm control --reload && udevadm trigger --action=change --subsystem-match=hidraw && udevadm trigger --action=change --sysname-match=uinput"]).stdin(Stdio::piped()).stderr(Stdio::piped()).spawn().context("pkexec isn't available")?;
    child
        .stdin
        .take()
        .unwrap()
        .write_all(UDEV_RULE.as_bytes())?;
    let result = child.wait_with_output()?;
    ensure!(
        result.status.success(),
        "{}",
        if matches!(result.status.code(), Some(126 | 127)) {
            "The password prompt was cancelled".into()
        } else {
            String::from_utf8_lossy(&result.stderr).into_owned()
        }
    );
    Ok("Access granted. Replug the mouse if it isn't found in a few seconds.".into())
}
pub fn session_info() -> Vec<String> {
    vec![
        format!("G502 Hub {}", env!("CARGO_PKG_VERSION")),
        "Native Rust · egui/eframe".into(),
        format!(
            "Kernel {}",
            fs::read_to_string("/proc/sys/kernel/osrelease")
                .unwrap_or_default()
                .trim()
        ),
        format!(
            "Desktop {} ({})",
            std::env::var("XDG_CURRENT_DESKTOP").unwrap_or("?".into()),
            std::env::var("XDG_SESSION_TYPE").unwrap_or("?".into())
        ),
    ]
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn downloaded_photo_dimensions_and_crop_are_validated() {
        use image::ImageEncoder;
        let image = image::RgbaImage::from_fn(2500, 2160, |x, y| {
            if (730..1760).contains(&x) && (130..1980).contains(&y) {
                image::Rgba([20, 80, 140, 255])
            } else {
                image::Rgba([255, 0, 0, 255])
            }
        });
        let mut png = vec![];
        image::codecs::png::PngEncoder::new(&mut png)
            .write_image(image.as_raw(), 2500, 2160, image::ExtendedColorType::Rgba8)
            .unwrap();
        let crop = prepare_photo(&png).unwrap();
        assert_eq!(crop.dimensions(), (618, 1110));
        assert_eq!(crop.get_pixel(309, 555).0, [20, 80, 140, 255]);
        assert_eq!(crop.get_pixel(0, 0).0, [20, 80, 140, 255]);
        assert!(prepare_photo(b"invalid download").is_err());
    }
}
