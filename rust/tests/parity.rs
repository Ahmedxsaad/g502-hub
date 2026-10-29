use g502_hub::{
    input,
    model::{self, Profile},
    parity,
};
use serde_json::{Value, json};
fn profile() -> Profile {
    let f: Value = serde_json::from_str(include_str!("fixtures/onboard-c08b.json")).unwrap();
    Profile::decode(&model::unhex(f["sectors"]["0x0001"].as_str().unwrap()).unwrap()).unwrap()
}
#[test]
fn dpi_insert_and_remove_preserve_default_sniper_and_active_levels() {
    let mut p = profile();
    p.dpi = [400, 800, 1600, 0, 0];
    p.default_dpi = 1;
    p.shift_dpi = 2;
    let active = parity::relevel(&mut p, &[(0, 400), (10, 600), (1, 800), (2, 1600)], 2);
    assert_eq!(p.dpi, [400, 600, 800, 1600, 0]);
    assert_eq!((p.default_dpi, p.shift_dpi, active), (2, 3, 3));
    let active = parity::relevel(&mut p, &[(1, 600), (2, 800), (3, 1600)], active);
    assert_eq!(p.dpi, [600, 800, 1600, 0, 0]);
    assert_eq!((p.default_dpi, p.shift_dpi, active), (1, 2, 2));
    let active = parity::relevel(&mut p, &[(0, 600), (2, 1600)], 1);
    assert_eq!((p.default_dpi, p.shift_dpi, active), (0, 1, 0));
}
#[test]
fn ui_catalogues_match_extracted_python_reference() {
    let reference: Value =
        serde_json::from_str(include_str!("fixtures/python-ui-contract.json")).unwrap();
    let media: Vec<_> = parity::MEDIA.iter().map(|(key, _)| *key).collect();
    assert_eq!(json!(media), reference["media"]);
    let labels: Vec<_> = parity::SHORTCUTS.iter().map(|(label, _)| *label).collect();
    let expected: Vec<_> = reference["shortcuts"]
        .as_array()
        .unwrap()
        .iter()
        .map(|s| s[0].clone())
        .collect();
    assert_eq!(json!(labels), json!(expected));
    for (native, python) in parity::templates()
        .iter()
        .zip(reference["templates"].as_array().unwrap())
    {
        for (key, value) in python.as_object().unwrap() {
            assert_eq!(&native[key], value, "{key}");
        }
    }
    assert_eq!(
        parity::templates().len(),
        reference["templates"].as_array().unwrap().len()
    );
}
#[test]
fn shortcuts_use_the_users_keyboard_layout() {
    let fr = input::typing_table("fr").unwrap();
    let binding = input::binding(&parity::shortcut_binding("ctrl+a", &fr)).unwrap();
    assert_eq!(binding, [128, 2, 1, 20]);
    let us = input::typing_table("us").unwrap();
    assert_eq!(
        input::binding(&parity::shortcut_binding("ctrl+a", &us)).unwrap(),
        [128, 2, 1, 4]
    );
}
#[test]
fn invalid_onboard_macro_cannot_pass_validation() {
    let m = json!({"target":"mouse","mode":"once","steps":vec![json!({"kind":"click","args":{"button":"left"}});50]});
    assert!(parity::macro_size(&m, &Default::default()).is_err());
}
#[test]
fn lighting_and_audio_match_python_numeric_reference() {
    use g502_hub::{audio, effects};
    let f: Value =
        serde_json::from_str(include_str!("fixtures/python-effects-contract.json")).unwrap();
    let number = |v: &Value| v.as_f64().unwrap() as f32;
    let rgb = |v: &Value| std::array::from_fn(|i| number(&v[i]));
    let close = |a: [f32; 3], b: [f32; 3]| {
        for i in 0..3 {
            assert!((a[i] - b[i]).abs() < 0.0001, "{a:?} != {b:?}");
        }
    };
    for v in f["adjust"].as_array().unwrap() {
        close(
            effects::adjust(
                rgb(&v["rgb"]),
                number(&v["saturation"]),
                number(&v["brightness"]),
            ),
            rgb(&v["expected"]),
        );
    }
    for v in f["wave"].as_array().unwrap() {
        close(
            effects::wave(
                number(&v["t"]),
                number(&v["period"]),
                v["zone"].as_u64().unwrap() as usize,
                0.8,
                0.7,
                v["reverse"].as_bool().unwrap(),
            ),
            rgb(&v["expected"]),
        );
    }
    for v in f["audio"].as_array().unwrap() {
        let a = &v["values"];
        let data = effects::CaptureData {
            level: number(&a[0]),
            bass: number(&a[1]),
            mid: number(&a[2]),
            treble: number(&a[3]),
            centroid: number(&a[4]),
            beat: a[5].as_bool().unwrap(),
            ..Default::default()
        };
        let colors = effects::audio_colors(
            v["style"].as_str().unwrap(),
            &data,
            [0.2, 0.4, 0.8],
            1.3,
            &mut 0.,
        );
        for i in 0..2 {
            close(colors[i], rgb(&v["expected"][i]));
        }
    }
    for v in f["analyzer"].as_array().unwrap() {
        let frequency = v["frequency"].as_f64().unwrap();
        let samples: Vec<_> = (0..8192)
            .map(|i| {
                ((std::f64::consts::TAU * frequency * i as f64 / 44100.).sin() * 16000.) as i16
            })
            .collect();
        let out = audio::Analyzer::default().feed(&samples).unwrap();
        for (i, value) in [out.level, out.bass, out.mid, out.treble, out.centroid]
            .into_iter()
            .enumerate()
        {
            assert!(
                (value - number(&v["expected"][i])).abs() < 0.0001,
                "frequency {frequency}, band {i}: {value} != {}",
                v["expected"][i]
            );
        }
        assert_eq!(out.beat, v["beat"].as_bool().unwrap());
    }
}

#[test]
fn screen_regions_and_cover_palette_match_python() {
    use g502_hub::effects;
    let f: Value =
        serde_json::from_str(include_str!("fixtures/python-effects-contract.json")).unwrap();
    let frame: Vec<u8> = (0..36)
        .flat_map(|y| (0..64).flat_map(move |x| [x * 3, y * 5, (x + y) * 2]))
        .collect();
    for v in f["sample"].as_array().unwrap() {
        let color = effects::sample(
            &frame,
            v["area"].as_str().unwrap(),
            v["vivid"].as_bool().unwrap(),
        );
        for i in 0..3 {
            assert!(
                (color[i] - v["expected"][i].as_f64().unwrap() as f32).abs() < 0.0001,
                "{} vivid {}",
                v["area"],
                v["vivid"]
            );
        }
    }
    let pixels: Vec<[u8; 3]> = f["palette"]["pixels"]
        .as_array()
        .unwrap()
        .iter()
        .map(|p| std::array::from_fn(|i| p[i].as_u64().unwrap() as u8))
        .collect();
    let palette = effects::palette(&pixels);
    for z in 0..2 {
        for i in 0..3 {
            assert!(
                (palette[z][i] - f["palette"]["expected"][z][i].as_f64().unwrap() as f32).abs()
                    < 0.0001
            );
        }
    }
}
#[test]
fn game_events_match_python_sequences() {
    use g502_hub::effects::GameFx;
    let frames: Value =
        serde_json::from_str(include_str!("fixtures/python-gsi-contract.json")).unwrap();
    let mut cs2 = GameFx::default();
    let mut dota = GameFx::default();
    for frame in frames.as_array().unwrap() {
        let game = frame["game"].as_str().unwrap();
        let fx = if game == "cs2" { &mut cs2 } else { &mut dota };
        let colors = fx
            .colors(game, &frame["data"], frame["t"].as_f64().unwrap() as f32)
            .unwrap();
        for z in 0..2 {
            for i in 0..3 {
                let expected = frame["expected"][z][i].as_f64().unwrap() as f32;
                assert!(
                    (colors[z][i] - expected).abs() < 0.0002,
                    "{game} t={} zone {z} channel {i}: {} != {expected}",
                    frame["t"],
                    colors[z][i]
                );
            }
        }
    }
}
#[test]
fn assigned_macros_display_names_instead_of_disabled() {
    let settings = json!({"macros":[{"id":"text","name":"Write text","target":"app"},{"id":"click","name":"Click","target":"mouse"}],"app_macros":{"1:0:8":"text"},"macro_pages":{"click":6}});
    assert_eq!(
        parity::assignment_label(&settings, 1, 0, 8, "disabled"),
        "Macro “Write text”, run by the app"
    );
    assert_eq!(
        parity::assignment_label(&settings, 1, 0, 4, "raw:00060000"),
        "Macro “Click”, saved on the mouse"
    );
    assert_eq!(
        parity::assignment_label(&settings, 1, 0, 5, "disabled"),
        "disabled"
    );
}
#[test]
fn text_expands_to_complete_azerty_keyboard_events() {
    let typing = input::typing_table("fr+latin9").unwrap();
    let m = json!({"mode":"once","target":"app","steps":[{"kind":"text","args":{"text":"Bonjour 123 @ test.fr\n"}}]});
    let events = input::expand(&m, &typing).unwrap();
    let mut held = std::collections::HashMap::<u16, usize>::new();
    let keys = input::device_keys();
    for event in events {
        if let input::Event::Key(code, down) = event {
            assert!(keys.contains(&code));
            let n = held.entry(code).or_default();
            if down {
                *n += 1;
            } else {
                assert!(*n > 0);
                *n -= 1;
            }
        }
    }
    assert!(held.values().all(|n| *n == 0));
    assert!(
        !keys.contains(&116),
        "No power button capability on the macro keyboard"
    );
}
