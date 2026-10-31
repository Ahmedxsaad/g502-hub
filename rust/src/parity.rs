//! Shared behavior ported from the original settings pages.
use crate::{input, model::Profile};
use anyhow::{Context, Result, ensure};
use serde_json::{Value, json};
use std::collections::HashMap;
pub const BUTTON_NAMES: &[&str] = &[
    "G1 · Left click",
    "G2 · Right click",
    "G3 · Wheel click",
    "G4 · Back",
    "G5 · Forward",
    "G6 · Sniper",
    "G7 · Front left",
    "G8 · Behind G7",
    "G9 · Behind wheel",
    "Wheel tilt right",
    "Wheel tilt left",
];
pub const MEDIA: &[(&str, &str)] = &[
    ("play-pause", "Play / pause"),
    ("next-track", "Next track"),
    ("prev-track", "Previous track"),
    ("stop", "Stop"),
    ("mute", "Mute"),
    ("volume-up", "Volume up"),
    ("volume-down", "Volume down"),
    ("browser-back", "Browser back"),
    ("browser-forward", "Browser forward"),
    ("browser-refresh", "Browser refresh"),
    ("browser-home", "Browser home"),
    ("browser-search", "Browser search"),
    ("file-browser", "File browser"),
    ("calculator", "Calculator"),
    ("mail", "Mail"),
    ("brightness-up", "Brightness up"),
    ("brightness-down", "Brightness down"),
];
pub const SHORTCUTS: &[(&str, &str)] = &[
    ("Copy", "ctrl+c"),
    ("Paste", "ctrl+v"),
    ("Cut", "ctrl+x"),
    ("Undo", "ctrl+z"),
    ("Redo", "ctrl+shift+z"),
    ("Select all", "ctrl+a"),
    ("Save", "ctrl+s"),
    ("Find", "ctrl+f"),
    ("New tab", "ctrl+t"),
    ("Close tab", "ctrl+w"),
    ("Reopen tab", "ctrl+shift+t"),
    ("Next tab", "ctrl+tab"),
    ("Previous tab", "ctrl+shift+tab"),
    ("Switch window", "alt+tab"),
    ("Show desktop", "meta+d"),
    ("Lock screen", "meta+l"),
    ("Screenshot", "printscreen"),
    ("Escape", "esc"),
    ("Enter", "enter"),
    ("Delete", "delete"),
];
pub fn shortcut_binding(combo: &str, typing: &HashMap<char, (u8, u16)>) -> String {
    if let Some(key) = combo.rsplit('+').next().filter(|k| k.len() == 1) {
        if let Some((_, code)) = typing.get(&key.chars().next().unwrap()) {
            if let Some((usage, _)) = input::keys::HID_EVDEV.iter().find(|(_, ev)| ev == code) {
                if let Ok((mods, _)) = input::combo(combo) {
                    return input::describe_binding([128, 2, mods, *usage as u8]);
                }
            }
        }
    }
    format!("key:{combo}")
}
pub fn dpi_range(payload: &[u8]) -> Result<[u16; 3]> {
    let mut plain = vec![];
    let mut step = 1;
    for v in payload
        .chunks_exact(2)
        .map(|p| u16::from_be_bytes([p[0], p[1]]))
    {
        if v == 0 {
            break;
        }
        if v >> 13 == 7 {
            step = v & 0x1fff;
        } else {
            plain.push(v);
        }
    }
    let lo = *plain.iter().min().context("No sensor DPI values")?;
    let hi = *plain.iter().max().unwrap();
    ensure!(lo > 0 && step > 0 && hi >= lo, "Invalid sensor DPI range");
    Ok([lo, hi, step])
}
pub fn quantize(dpi: f32, range: [u16; 3]) -> u16 {
    let [lo, hi, step] = range;
    ((dpi / step.max(1) as f32).round() * step.max(1) as f32).clamp(lo as f32, hi as f32) as u16
}
/// Original indices are retained through insertions so default/sniper/active follow their DPI.
pub fn relevel(profile: &mut Profile, values: &[(usize, u16)], active: usize) -> usize {
    let find = |old: usize| values.iter().position(|(slot, _)| *slot == old);
    let default = find(profile.default_dpi as usize).unwrap_or(0);
    let shift = find(profile.shift_dpi as usize).unwrap_or(0);
    profile.dpi = std::array::from_fn(|i| values.get(i).map(|(_, v)| *v).unwrap_or(0));
    profile.default_dpi = default as u8;
    profile.shift_dpi = shift as u8;
    find(active).unwrap_or(default)
}
pub fn macro_size(m: &Value, typing: &HashMap<char, (u8, u16)>) -> Result<Option<usize>> {
    ensure!(
        m["steps"].as_array().is_some_and(|s| !s.is_empty()),
        "Add at least one step."
    );
    let events = input::expand(m, typing)?;
    if m["target"] == "mouse" {
        ensure!(
            m["mode"].as_str().unwrap_or("once") == "once",
            "Macros saved on the mouse play once per press"
        );
        Ok(Some(input::onboard_macro(&events)?.len()))
    } else {
        Ok(None)
    }
}
pub fn templates() -> Vec<Value> {
    [("YouTube", "media", "youtube", "color", "#ff0000"), ("Netflix", "media", "netflix", "color", "#e50914"),
     ("Twitch", "media", "twitch", "color", "#9146ff"), ("Spotify", "media", "spotify", "audio", "#14b4ff"),
     ("Any Steam game", "game", "any", "art", "#14b4ff"), ("Counter-Strike 2", "game", "730", "game", "#14b4ff"),
     ("Dota 2", "game", "570", "game", "#14b4ff")].into_iter().map(|(name, trigger, value, lighting, color)|
        json!({"name":name,"trigger":trigger,"value":value,"lighting":lighting,"color":color,"period_ms":4000,"slot":null,"enabled":true})).collect()
}
pub fn macro_on(
    settings: &Value,
    slot: usize,
    layer: usize,
    button: usize,
    binding: &str,
) -> Option<String> {
    if let Some(id) = settings["app_macros"][format!("{slot}:{layer}:{button}")].as_str() {
        return Some(id.into());
    }
    let raw = input::binding(binding).ok()?;
    if raw[0] < 128 {
        if let Some(pages) = settings["macro_pages"].as_object() {
            return pages
                .iter()
                .find(|(_, page)| page.as_u64() == Some(raw[1] as u64))
                .map(|(id, _)| id.clone());
        }
    }
    None
}
pub fn assignment_label(
    settings: &Value,
    slot: usize,
    layer: usize,
    button: usize,
    binding: &str,
) -> String {
    if let Some(id) = macro_on(settings, slot, layer, button, binding) {
        if let Some(m) = settings["macros"]
            .as_array()
            .and_then(|items| items.iter().find(|m| m["id"] == id))
        {
            return format!(
                "Macro “{}”, {}",
                m["name"].as_str().unwrap_or("Macro"),
                if m["target"] == "mouse" {
                    "saved on the mouse"
                } else {
                    "run by the app"
                }
            );
        }
    }
    binding.into()
}
pub fn remember(items: &mut Vec<String>, value: &str) {
    if value.is_empty() {
        return;
    }
    items.retain(|v| v != value);
    items.insert(0, value.into());
    items.truncate(12);
}
pub fn trigger_description(rule: &Value, games: &[Value]) -> String {
    let value = rule["value"].as_str().unwrap_or("");
    match rule["trigger"].as_str().unwrap_or("") {
        "game" if value == "any" => "While any game is running".into(),
        "game" => format!(
            "While {} is running",
            games
                .iter()
                .find(|g| g["appid"].to_string() == value || g["appid"].as_str() == Some(value))
                .and_then(|g| g["name"].as_str())
                .map(str::to_owned)
                .unwrap_or(format!("Steam app {value}"))
        ),
        "app" => format!("While {value} is in front"),
        "title" => format!("While a window title contains “{value}”"),
        _ => format!("While playing media contains “{value}”"),
    }
}
pub fn action_description(rule: &Value) -> String {
    let kind = rule["lighting"].as_str().unwrap_or("");
    let label = match kind {
        "color" => "Color",
        "breathing" => "Breathing",
        "art" => "Cover art colors",
        "game" => "Game-driven",
        "screen" => "Screen sampler",
        "audio" => "Audio visualizer",
        "wave" => "Color wave",
        "dpi" => "DPI colors",
        _ => "",
    };
    let mut parts = vec![];
    if !label.is_empty() {
        parts.push(if ["color", "breathing"].contains(&kind) {
            format!("{label} {}", rule["color"].as_str().unwrap_or("#14b4ff"))
        } else {
            label.into()
        });
    }
    if let Some(slot) = rule["slot"].as_u64().filter(|n| *n > 0) {
        parts.push(format!("profile slot {slot}"));
    }
    if parts.is_empty() {
        "nothing yet".into()
    } else {
        parts.join(", ")
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn sensor_ranges_and_rounding() {
        assert_eq!(
            dpi_range(&[0, 100, 0xe0, 50, 0x64, 0, 0, 0]).unwrap(),
            [100, 25600, 50]
        );
        assert_eq!(quantize(477., [100, 25600, 50]), 500);
        assert!(dpi_range(&[0, 0]).is_err());
    }
    #[test]
    fn macro_storage_constraints_and_media_catalogue() {
        let mut m = json!({"mode":"once","target":"mouse","steps":[{"kind":"click","args":{"button":"left"}}]});
        assert_eq!(macro_size(&m, &HashMap::new()).unwrap(), Some(7));
        m["mode"] = json!("toggle");
        assert!(macro_size(&m, &HashMap::new()).is_err());
        m["steps"] = json!([]);
        assert!(macro_size(&m, &HashMap::new()).is_err());
        for (key, _) in MEDIA {
            assert!(input::binding(&format!("media:{key}")).is_ok(), "{key}");
        }
        for (_, key) in SHORTCUTS {
            assert!(input::combo(key).is_ok(), "{key}");
        }
    }
    #[test]
    fn recent_values_and_templates() {
        let mut items = vec![];
        for n in 0..20 {
            remember(&mut items, &n.to_string());
        }
        remember(&mut items, "12");
        assert_eq!(items.len(), 12);
        assert_eq!(items[0], "12");
        assert_eq!(items.iter().filter(|v| *v == "12").count(), 1);
        assert_eq!(templates().len(), 7);
    }
}
