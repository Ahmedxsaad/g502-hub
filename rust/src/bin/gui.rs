#[path = "gui/mouse.rs"]
mod mouse;
use eframe::egui::{self, Color32, RichText};
use g502_hub_rust::{config, effects, input, ipc, model::Profile, service::Snapshot};
use serde_json::{Value, json};
use std::{
    path::PathBuf,
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
        mpsc,
    },
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
const BG: Color32 = Color32::from_rgb(14, 15, 18);
const PANEL: Color32 = Color32::from_rgb(22, 24, 28);
const RAISED: Color32 = Color32::from_rgb(30, 33, 38);
const BORDER: Color32 = Color32::from_rgb(42, 46, 53);
const MUTED: Color32 = Color32::from_rgb(139, 144, 153);
const TEXT: Color32 = Color32::from_rgb(233, 234, 236);
const ACCENT: Color32 = Color32::from_rgb(20, 180, 255);
const TABS: &[(&str, &str)] = &[
    ("light", "LIGHTSYNC"),
    ("buttons", "ASSIGNMENTS"),
    ("sens", "SENSITIVITY"),
    ("profiles", "PROFILES"),
    ("macros", "MACROS"),
    ("rules", "GAMES & APPS"),
    ("settings", "SETTINGS"),
    ("about", "ABOUT"),
];
fn bold(size: f32) -> egui::FontId {
    egui::FontId::new(size, egui::FontFamily::Name("bold".into()))
}
fn spaced(text: &str, size: f32, color: Color32, spacing: f32) -> egui::text::LayoutJob {
    let mut job = egui::text::LayoutJob::default();
    job.append(
        text,
        0.,
        egui::TextFormat {
            font_id: bold(size),
            color,
            extra_letter_spacing: spacing,
            ..Default::default()
        },
    );
    job
}
fn section(ui: &mut egui::Ui, text: &str) {
    ui.add_space(6.);
    ui.label(spaced(&text.to_uppercase(), 11., MUTED, 1.5));
}
fn segments(ui: &mut egui::Ui, selected: &mut usize, labels: &[&str]) {
    ui.horizontal(|ui| {
        ui.spacing_mut().item_spacing.x = 0.;
        for (i, label) in labels.iter().enumerate() {
            let galley = ui.painter().layout_job(spaced(
                &label.to_uppercase(),
                11.,
                if i == *selected { TEXT } else { MUTED },
                1.2,
            ));
            let (r, response) = ui
                .allocate_exact_size(egui::vec2(galley.size().x + 20., 38.), egui::Sense::click());
            if response.clicked() {
                *selected = i;
            }
            ui.painter()
                .galley(r.center() - galley.size() / 2., galley, TEXT);
            if i == *selected {
                ui.painter().line_segment(
                    [r.left_bottom(), r.right_bottom()],
                    egui::Stroke::new(2.0f32, ACCENT),
                );
            }
        }
    });
}
fn choice(ui: &mut egui::Ui, label: &str, selected: bool, width: f32) -> egui::Response {
    let (r, response) = ui.allocate_exact_size(egui::vec2(width, 36.), egui::Sense::click());
    ui.painter().rect_filled(
        r,
        4.,
        if selected {
            Color32::from_rgb(16, 41, 58)
        } else if response.hovered() {
            Color32::from_rgb(38, 42, 48)
        } else {
            RAISED
        },
    );
    ui.painter().rect_stroke(
        r,
        4.,
        egui::Stroke::new(1.0f32, if selected { ACCENT } else { BORDER }),
        egui::StrokeKind::Inside,
    );
    ui.painter().text(
        r.left_center() + egui::vec2(12., 0.),
        egui::Align2::LEFT_CENTER,
        label,
        egui::FontId::proportional(13.),
        TEXT,
    );
    response.widget_info(|| {
        egui::WidgetInfo::selected(egui::WidgetType::Button, ui.is_enabled(), selected, label)
    });
    response
}
trait ThemedCheckbox {
    fn themed_checkbox(&mut self, value: &mut bool, label: impl Into<String>) -> egui::Response;
}
impl ThemedCheckbox for egui::Ui {
    fn themed_checkbox(&mut self, value: &mut bool, label: impl Into<String>) -> egui::Response {
        let label = label.into();
        let galley = self.painter().layout(
            label.clone(),
            egui::FontId::proportional(13.),
            TEXT,
            (self.available_width() - 24.).max(20.),
        );
        let (r, mut response) = self.allocate_exact_size(
            egui::vec2(
                (galley.size().x + 24.).min(self.available_width()),
                galley.size().y.max(18.),
            ),
            egui::Sense::click(),
        );
        if response.clicked() {
            *value = !*value;
            response.mark_changed();
        }
        let box_r = egui::Rect::from_min_size(
            r.min + egui::vec2(0., (r.height() - 18.) / 2.),
            egui::vec2(18., 18.),
        );
        self.painter()
            .rect_filled(box_r, 3., if *value { ACCENT } else { RAISED });
        self.painter().rect_stroke(
            box_r,
            3.,
            egui::Stroke::new(
                1.0f32,
                if *value || response.hovered() {
                    ACCENT
                } else {
                    MUTED
                },
            ),
            egui::StrokeKind::Inside,
        );
        if *value {
            let c = box_r.min;
            self.painter().add(egui::Shape::line(
                vec![
                    c + egui::vec2(4., 9.),
                    c + egui::vec2(7.5, 12.5),
                    c + egui::vec2(14., 5.),
                ],
                egui::Stroke::new(2.0f32, BG),
            ));
        }
        self.painter().galley(
            r.min + egui::vec2(24., (r.height() - galley.size().y) / 2.),
            galley,
            TEXT,
        );
        response.widget_info(|| {
            egui::WidgetInfo::selected(
                egui::WidgetType::Checkbox,
                self.is_enabled(),
                *value,
                label.clone(),
            )
        });
        response
    }
}
fn choices(ui: &mut egui::Ui, id: &str, value: &mut Value, items: &[(&str, &str)], cols: usize) {
    let width = (ui.available_width() - 6. * (cols - 1) as f32) / cols as f32;
    egui::Grid::new(id)
        .num_columns(cols)
        .spacing([6., 6.])
        .show(ui, |ui| {
            for (i, (key, label)) in items.iter().enumerate() {
                if choice(ui, label, value.as_str() == Some(*key), width).clicked() {
                    *value = (*key).into();
                }
                if i % cols == cols - 1 {
                    ui.end_row();
                }
            }
        });
}
fn glow(p: &egui::Painter, center: egui::Pos2, radius: f32, rgb: [u8; 3]) {
    let mut mesh = egui::Mesh::default();
    // Additive premultiplied color reproduces QPainter's CompositionMode_Plus.
    let rings = [(0., 90f32), (0.45, 28.), (1., 0.)];
    for (fraction, alpha) in rings {
        for i in 0..64 {
            let a = i as f32 * std::f32::consts::TAU / 64.;
            mesh.colored_vertex(
                center + egui::vec2(a.cos(), a.sin()) * radius * fraction,
                Color32::from_rgba_premultiplied(
                    (rgb[0] as f32 * alpha / 255.) as u8,
                    (rgb[1] as f32 * alpha / 255.) as u8,
                    (rgb[2] as f32 * alpha / 255.) as u8,
                    0,
                ),
            );
        }
    }
    for ring in 0..2u32 {
        for i in 0..64u32 {
            let a = ring * 64 + i;
            let b = ring * 64 + (i + 1) % 64;
            mesh.add_triangle(a, b, a + 64);
            mesh.add_triangle(b, b + 64, a + 64);
        }
    }
    p.add(egui::Shape::mesh(mesh));
}
fn color_picker(ui: &mut egui::Ui, rgb: &mut [u8; 3], saved: &mut Vec<String>) -> bool {
    let before = *rgb;
    let mut picked = false;
    let mut hsv = egui::ecolor::Hsva::from(Color32::from_rgb(rgb[0], rgb[1], rgb[2]));
    let (area, _) =
        ui.allocate_exact_size(egui::vec2(ui.available_width(), 220.), egui::Sense::hover());
    let rect = egui::Rect::from_center_size(area.center(), egui::vec2(220., 220.));
    let c = rect.center();
    let radius = 109.;
    let response = ui.interact(rect, ui.id().with("wheel"), egui::Sense::click_and_drag());
    if response.clicked() || response.dragged() {
        picked = true;
        if let Some(pos) = response.interact_pointer_pos() {
            let d = pos - c;
            hsv.h = (-d.y).atan2(d.x).rem_euclid(std::f32::consts::TAU) / std::f32::consts::TAU;
            hsv.s = (d.length() / radius).min(1.);
        }
    }
    let mut mesh = egui::Mesh::default();
    for ring in 0..=16 {
        let sat = ring as f32 / 16.;
        for i in 0..128 {
            let hue = i as f32 / 128.;
            let a = hue * std::f32::consts::TAU;
            mesh.colored_vertex(
                c + egui::vec2(a.cos(), -a.sin()) * radius * sat,
                Color32::from(egui::ecolor::Hsva::new(hue, sat, hsv.v, 1.)),
            );
        }
    }
    for ring in 0..16u32 {
        for i in 0..128u32 {
            let a = ring * 128 + i;
            let b = ring * 128 + (i + 1) % 128;
            mesh.add_triangle(a, b, a + 128);
            mesh.add_triangle(b, b + 128, a + 128);
        }
    }
    ui.painter().add(egui::Shape::mesh(mesh));
    let a = hsv.h * std::f32::consts::TAU;
    let pos = c + egui::vec2(a.cos(), -a.sin()) * hsv.s * radius;
    ui.painter().circle_stroke(
        pos,
        9.,
        egui::Stroke::new(4.0f32, Color32::from_black_alpha(120)),
    );
    ui.painter()
        .circle_stroke(pos, 9., egui::Stroke::new(2.5f32, Color32::WHITE));
    let (bar, response) = ui.allocate_exact_size(
        egui::vec2(ui.available_width(), 24.),
        egui::Sense::click_and_drag(),
    );
    let bar = bar.shrink2(egui::vec2(9., 4.));
    if response.clicked() || response.dragged() {
        picked = true;
        if let Some(pos) = response.interact_pointer_pos() {
            hsv.v = ((pos.x - bar.left()) / bar.width()).clamp(0., 1.);
        }
    }
    let mut gradient = egui::Mesh::default();
    gradient.colored_vertex(bar.left_top(), Color32::BLACK);
    gradient.colored_vertex(bar.left_bottom(), Color32::BLACK);
    let full: Color32 = egui::ecolor::Hsva::new(hsv.h, hsv.s, 1., 1.).into();
    gradient.colored_vertex(bar.right_top(), full);
    gradient.colored_vertex(bar.right_bottom(), full);
    gradient.add_triangle(0, 1, 2);
    gradient.add_triangle(1, 2, 3);
    ui.painter().add(egui::Shape::mesh(gradient));
    ui.painter().circle_filled(
        egui::pos2(bar.left() + bar.width() * hsv.v, bar.center().y),
        7.,
        TEXT,
    );
    let color: Color32 = hsv.into();
    if picked {
        *rgb = [color.r(), color.g(), color.b()];
    }
    ui.horizontal(|ui| {
        let (r, _) = ui.allocate_exact_size(egui::vec2(32., 32.), egui::Sense::hover());
        ui.painter().rect_filled(r, 4., color);
        let id = ui.id().with("hex");
        let mut text = ui
            .data_mut(|d| d.get_temp::<String>(id))
            .unwrap_or_else(|| format!("#{:02x}{:02x}{:02x}", rgb[0], rgb[1], rgb[2]));
        let response = ui.add(
            egui::TextEdit::singleline(&mut text)
                .desired_width(74.)
                .char_limit(7),
        );
        if response.changed() && text.len() == 7 && text.starts_with('#') && text.is_ascii() {
            if let Ok(n) = u32::from_str_radix(&text[1..], 16) {
                *rgb = [(n >> 16) as u8, (n >> 8) as u8, n as u8];
            }
        }
        if response.has_focus() {
            ui.data_mut(|d| d.insert_temp(id, text));
        } else {
            ui.data_mut(|d| d.remove::<String>(id));
        }
        for (i, label) in ["R", "G", "B"].iter().enumerate() {
            ui.add_sized(
                [60., 30.],
                egui::DragValue::new(&mut rgb[i])
                    .range(0..=255)
                    .prefix(format!("{label}  ")),
            );
        }
    });
    let swatch = |ui: &mut egui::Ui, color: [u8; 3]| {
        let (r, response) = ui.allocate_exact_size(egui::vec2(24., 24.), egui::Sense::click());
        ui.painter().circle_filled(
            r.center(),
            12.,
            Color32::from_rgb(color[0], color[1], color[2]),
        );
        ui.painter().circle_stroke(
            r.center(),
            11.5,
            egui::Stroke::new(1.0f32, if response.hovered() { TEXT } else { BORDER }),
        );
        response
    };
    ui.horizontal(|ui| {
        for color in [
            [255, 0, 0],
            [255, 106, 0],
            [255, 212, 0],
            [61, 220, 132],
            [0, 255, 213],
            [20, 180, 255],
            [47, 75, 255],
            [128, 0, 255],
            [255, 47, 214],
            [255, 255, 255],
        ] {
            if swatch(ui, color).clicked() {
                *rgb = color;
            }
        }
    });
    section(ui, "My colors");
    let mut remove = None;
    ui.horizontal_wrapped(|ui| {
        for (i, hex) in saved.iter().enumerate() {
            if let Ok(n) = u32::from_str_radix(hex.trim_start_matches('#'), 16) {
                let color = [(n >> 16) as u8, (n >> 8) as u8, n as u8];
                let response = swatch(ui, color);
                if response.clicked() {
                    *rgb = color;
                }
                if response.secondary_clicked() {
                    remove = Some(i);
                }
            }
        }
        if saved.len() < 10 && ui.small_button("+").clicked() {
            saved.push(format!("#{:02x}{:02x}{:02x}", rgb[0], rgb[1], rgb[2]));
        }
    });
    if let Some(i) = remove {
        saved.remove(i);
    }
    *rgb != before
}
fn thin_slider(ui: &mut egui::Ui, value: &mut u16, min: u16, max: u16) -> bool {
    let (r, response) = ui.allocate_exact_size(
        egui::vec2(ui.available_width(), 22.),
        egui::Sense::click_and_drag(),
    );
    let a = r.left() + 7.;
    let b = r.right() - 7.;
    let mut changed = false;
    if response.clicked() || response.dragged() {
        if let Some(pos) = response.interact_pointer_pos() {
            let next = (min as f32 + (max - min) as f32 * ((pos.x - a) / (b - a)).clamp(0., 1.))
                .round() as u16;
            changed = next != *value;
            *value = next;
        }
    }
    let x = a + (b - a) * ((*value as f32 - min as f32) / (max - min) as f32).clamp(0., 1.);
    let y = r.center().y;
    ui.painter().line_segment(
        [egui::pos2(a, y), egui::pos2(b, y)],
        egui::Stroke::new(4.0f32, BORDER),
    );
    ui.painter().line_segment(
        [egui::pos2(a, y), egui::pos2(x, y)],
        egui::Stroke::new(4.0f32, ACCENT),
    );
    ui.painter().circle_filled(egui::pos2(x, y), 7., TEXT);
    changed
}
fn rail_button(ui: &mut egui::Ui, key: &str, label: &str, selected: bool) -> bool {
    let (r, response) = ui.allocate_exact_size(egui::vec2(92., 65.), egui::Sense::click());
    let p = ui.painter();
    let color = if selected || response.hovered() {
        TEXT
    } else {
        MUTED
    };
    if response.hovered() {
        p.rect_filled(r, 0., PANEL);
    }
    if selected {
        p.rect_filled(
            egui::Rect::from_min_size(r.min, egui::vec2(3., 65.)),
            0.,
            ACCENT,
        );
    }
    let c = r.center_top() + egui::vec2(0., 23.);
    let stroke = egui::Stroke::new(1.6f32, color);
    let line = |a: [f32; 2], b: [f32; 2]| {
        p.line_segment(
            [c + egui::vec2(a[0], a[1]), c + egui::vec2(b[0], b[1])],
            stroke,
        );
    };
    match key {
        "light" | "settings" => {
            p.circle_stroke(c, if key == "light" { 4.5 } else { 6.5 }, stroke);
            if key == "settings" {
                p.circle_stroke(c, 2.5, stroke);
            }
            for i in 0..8 {
                let a = i as f32 * std::f32::consts::TAU / 8.;
                line(
                    [a.cos() * 7.5, a.sin() * 7.5],
                    [a.cos() * 11., a.sin() * 11.],
                );
            }
        }
        "sens" => {
            p.circle_stroke(c, 8., stroke);
            p.circle_stroke(c, 2., stroke);
            for i in 0..4 {
                let a = i as f32 * std::f32::consts::TAU / 4.;
                line([a.cos() * 5., a.sin() * 5.], [a.cos() * 12., a.sin() * 12.]);
            }
        }
        "buttons" => {
            p.rect_stroke(
                egui::Rect::from_center_size(c, egui::vec2(12., 21.)),
                6.,
                stroke,
                egui::StrokeKind::Inside,
            );
            line([0., -10.], [0., -2.]);
            line([-6., -2.], [6., -2.]);
        }
        "profiles" => {
            for y in [-7., 0., 7.] {
                p.rect_stroke(
                    egui::Rect::from_center_size(c + egui::vec2(0., y), egui::vec2(18., 5.)),
                    1.5,
                    stroke,
                    egui::StrokeKind::Inside,
                );
            }
        }
        "macros" => {
            for y in [-6., 0., 6.] {
                line([-10., y], [0., y]);
            }
            p.add(egui::Shape::closed_line(
                vec![
                    c + egui::vec2(3., -5.),
                    c + egui::vec2(11., 0.),
                    c + egui::vec2(3., 5.),
                ],
                stroke,
            ));
        }
        "rules" => {
            p.rect_stroke(
                egui::Rect::from_center_size(c, egui::vec2(22., 13.)),
                6.,
                stroke,
                egui::StrokeKind::Inside,
            );
            line([-7., 0.], [-1., 0.]);
            line([-4., -3.], [-4., 3.]);
            p.circle_filled(c + egui::vec2(4., -2.), 1.4, color);
            p.circle_filled(c + egui::vec2(7., 2.), 1.4, color);
        }
        _ => {
            p.circle_stroke(c, 9., stroke);
            line([0., -1.], [0., 6.]);
            p.circle_filled(c + egui::vec2(0., -5.), 1., color);
        }
    }
    let mut job = spaced(label, 10., color, 1.);
    job.sections[0].format.font_id = egui::FontId::proportional(10.);
    let galley = p.layout_job(job);
    p.galley(
        r.center_top() + egui::vec2(-galley.size().x / 2., 38.),
        galley,
        color,
    );
    response
        .on_hover_cursor(egui::CursorIcon::PointingHand)
        .clicked()
}
#[derive(Default)]
struct Updates {
    snapshot: Option<Snapshot>,
    write_done: Option<bool>,
    prefixes: Option<Vec<Value>>,
    games: Option<Vec<Value>>,
    message: Option<(bool, String)>,
}
struct App {
    prefixes: Vec<Value>,
    games: Vec<Value>,
    bridge_path: String,
    tab: String,
    slot: usize,
    draft: Option<Profile>,
    bindings: [Vec<String>; 2],
    dirty: bool,
    pending_write: bool,
    write_failed: bool,
    edit_signature: String,
    edit_since: Instant,
    profile_names: Vec<String>,
    profile_action: Option<(String, Value, String)>,
    profile_file_dialog: bool,
    file_operation: String,
    picked_file: Arc<Mutex<Option<(String, usize, Option<String>)>>>,
    step_selected: usize,
    step_tab: usize,
    step_text: String,
    step_wait: u64,
    snap: Snapshot,
    settings: Value,
    tx: mpsc::Sender<(String, Value)>,
    updates: Arc<Mutex<Updates>>,
    animate_live: Arc<AtomicBool>,
    photo: Option<egui::TextureHandle>,
    led_masks: Vec<egui::TextureHandle>,
    layer: usize,
    light_mode: usize,
    light_zone: usize,
    same_zones: bool,
    selected_button: usize,
    button_category: usize,
    editing_library: bool,
    macro_id: String,
    macro_draft: Value,
    rule_id: String,
    rule_draft: Value,
    close_after_save: bool,
    path: String,
    recording: bool,
    record_at: Option<Instant>,
    message: String,
    failed: bool,
    settings_text: String,
    screenshot: Option<PathBuf>,
    started: Instant,
    screenshot_sent: bool,
    smoke: bool,
    smoke_done: bool,
}
fn id() -> String {
    format!(
        "rust{:x}",
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_micros()
    )
}
fn new_macro() -> Value {
    json!({"id":id(),"name":"New macro","mode":"once","target":"app","gap_ms":0,"steps":[]})
}
fn new_rule() -> Value {
    json!({"id":id(),"name":"New rule","trigger":"game","value":"any","lighting":"color","color":"#14b4ff","period_ms":4000,"slot":null,"enabled":true})
}
fn string(ui: &mut egui::Ui, v: &mut Value) -> bool {
    let mut s = v.as_str().unwrap_or("").to_string();
    let r = ui.add(egui::TextEdit::singleline(&mut s).desired_width(f32::INFINITY));
    if r.changed() {
        *v = s.into();
    }
    r.changed()
}
fn combo(
    ui: &mut egui::Ui,
    id: impl std::hash::Hash,
    v: &mut Value,
    values: &[(&str, &str)],
) -> bool {
    let before = v.clone();
    let mut selected = v.as_str().unwrap_or("").to_owned();
    egui::ComboBox::from_id_salt(id)
        .selected_text(
            values
                .iter()
                .find(|(k, _)| *k == selected)
                .map(|(_, label)| *label)
                .unwrap_or(&selected),
        )
        .show_ui(ui, |ui| {
            for (k, label) in values {
                ui.selectable_value(&mut selected, k.to_string(), *label);
            }
        });
    *v = selected.into();
    *v != before
}
fn number(ui: &mut egui::Ui, v: &mut Value, range: std::ops::RangeInclusive<f64>) -> bool {
    let mut n = v.as_f64().unwrap_or(*range.start());
    let changed = ui
        .add(egui::DragValue::new(&mut n).range(range).speed(0.05))
        .changed();
    if changed {
        *v = json!(n);
    }
    changed
}
impl App {
    fn new(cc: &eframe::CreationContext<'_>, screenshot: Option<PathBuf>, smoke: bool) -> Self {
        let mut visual = egui::Visuals::dark();
        visual.panel_fill = BG;
        visual.window_fill = PANEL;
        visual.extreme_bg_color = RAISED;
        visual.override_text_color = Some(TEXT);
        visual.selection.bg_fill = Color32::from_rgb(16, 41, 58);
        visual.selection.stroke = egui::Stroke::new(1.0f32, ACCENT);
        for widget in [
            &mut visual.widgets.inactive,
            &mut visual.widgets.active,
            &mut visual.widgets.hovered,
        ] {
            widget.bg_fill = RAISED;
            widget.weak_bg_fill = RAISED;
            widget.bg_stroke = egui::Stroke::new(1.0f32, BORDER);
            widget.corner_radius = 4.into();
        }
        visual.widgets.hovered.bg_fill = Color32::from_rgb(38, 42, 48);
        visual.widgets.active.bg_stroke.color = ACCENT;
        cc.egui_ctx.set_visuals(visual);
        let mut style = (*cc.egui_ctx.style()).clone();
        style.spacing.item_spacing = egui::vec2(6., 12.);
        style.spacing.button_padding = egui::vec2(12., 7.);
        style.spacing.interact_size.y = 30.;
        style.spacing.slider_width = 220.;
        for (kind, size) in [
            (egui::TextStyle::Body, 13.),
            (egui::TextStyle::Button, 13.),
            (egui::TextStyle::Heading, 16.),
            (egui::TextStyle::Small, 12.),
        ] {
            style.text_styles.insert(
                kind.clone(),
                if kind == egui::TextStyle::Heading {
                    bold(size)
                } else {
                    egui::FontId::proportional(size)
                },
            );
        }
        cc.egui_ctx.set_style(style);
        // Match Qt's installed fallback when Inter is unavailable; no runtime Qt dependency.
        for path in [
            "/usr/share/fonts/truetype/inter/Inter-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        ] {
            if let Ok(bytes) = std::fs::read(path) {
                let mut fonts = egui::FontDefinitions::default();
                fonts
                    .font_data
                    .insert("ui".into(), egui::FontData::from_owned(bytes).into());
                fonts
                    .families
                    .get_mut(&egui::FontFamily::Proportional)
                    .unwrap()
                    .insert(0, "ui".into());
                if let Ok(bytes) =
                    std::fs::read("/usr/share/fonts/truetype/noto/NotoSans-SemiBold.ttf")
                {
                    fonts
                        .font_data
                        .insert("bold".into(), egui::FontData::from_owned(bytes).into());
                    fonts.families.insert(
                        egui::FontFamily::Name("bold".into()),
                        vec!["bold".into(), "ui".into()],
                    );
                } else {
                    fonts
                        .families
                        .insert(egui::FontFamily::Name("bold".into()), vec!["ui".into()]);
                }
                if let Ok(bytes) = std::fs::read("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
                {
                    fonts
                        .font_data
                        .insert("symbols".into(), egui::FontData::from_owned(bytes).into());
                    for family in fonts.families.values_mut() {
                        family.push("symbols".into());
                    }
                }
                cc.egui_ctx.set_fonts(fonts);
                break;
            }
        }
        let (tx, rx) = mpsc::channel::<(String, Value)>();
        let updates = Arc::new(Mutex::new(Updates::default()));
        let shared = updates.clone();
        let animate_live = Arc::new(AtomicBool::new(false));
        let live_updates = animate_live.clone();
        let ctx = cc.egui_ctx.clone();
        std::thread::spawn(move || {
            loop {
                let mut write_done = None;
                match rx.recv_timeout(Duration::from_millis(
                    if live_updates.load(Ordering::Relaxed) {
                        33
                    } else {
                        300
                    },
                )) {
                    Ok((cmd, args)) => {
                        let result = ipc::request(&cmd, args);
                        if cmd == "write_profile" {
                            write_done = Some(result.is_ok());
                        }
                        match result {
                            Ok(v) if cmd == "bridge_prefixes" => {
                                shared.lock().unwrap().prefixes = v.as_array().cloned()
                            }
                            Ok(v) if cmd == "games" => {
                                shared.lock().unwrap().games = v.as_array().cloned()
                            }
                            Ok(_) => shared.lock().unwrap().message = Some((false, "Ready".into())),
                            Err(e) => shared.lock().unwrap().message = Some((true, e.to_string())),
                        }
                    }
                    Err(mpsc::RecvTimeoutError::Disconnected) => break,
                    Err(_) => {}
                }
                let snapshot = ipc::request("snapshot", json!({}))
                    .and_then(|v| Ok(serde_json::from_value::<Snapshot>(v)?));
                {
                    let mut update = shared.lock().unwrap();
                    match snapshot {
                        Ok(s) => update.snapshot = Some(s),
                        Err(e) => update.message = Some((true, e.to_string())),
                    }
                    if write_done.is_some() {
                        update.write_done = write_done;
                    }
                }
                ctx.request_repaint();
            }
        });
        let mut app = Self {
            prefixes: vec![],
            games: vec![],
            bridge_path: String::new(),
            tab: std::env::args()
                .position(|a| a == "--page")
                .and_then(|i| std::env::args().nth(i + 1))
                .unwrap_or("light".into()),
            slot: 1,
            draft: None,
            bindings: [vec![], vec![]],
            dirty: false,
            pending_write: false,
            write_failed: false,
            edit_signature: String::new(),
            edit_since: Instant::now(),
            profile_names: vec![],
            profile_action: None,
            profile_file_dialog: false,
            file_operation: "import_profile".into(),
            picked_file: Arc::new(Mutex::new(None)),
            step_selected: 0,
            step_tab: 0,
            step_text: String::new(),
            step_wait: 100,
            snap: Snapshot::default(),
            settings: json!({}),
            tx,
            updates,
            animate_live,
            photo: None,
            led_masks: vec![],
            layer: 0,
            light_mode: 0,
            light_zone: 0,
            same_zones: false,
            selected_button: 5,
            button_category: 0,
            editing_library: false,
            macro_id: String::new(),
            macro_draft: new_macro(),
            rule_id: String::new(),
            rule_draft: new_rule(),
            close_after_save: false,
            path: config::home()
                .join("Downloads/g502-profil.g502profile")
                .display()
                .to_string(),
            recording: false,
            record_at: None,
            message: "Connexion au service Rust…".into(),
            failed: false,
            settings_text: String::new(),
            screenshot,
            started: Instant::now(),
            screenshot_sent: false,
            smoke,
            smoke_done: false,
        };
        let photo = config::home().join(".local/share/g502-hub/g502-hero.png");
        if let Ok(image) = image::open(photo) {
            let mut image = image.to_rgba8();
            // Reproduce the original photo skin: smoked LEDs plus tintable masks.
            for (z, (x, y, w, h)) in [(112, 529, 41, 116), (202, 704, 98, 100)]
                .into_iter()
                .enumerate()
            {
                if image.width() < x + w || image.height() < y + h {
                    continue;
                }
                let mut mask = image::RgbaImage::new(w, h);
                for dy in 0..h {
                    for dx in 0..w {
                        let pixel = image.get_pixel_mut(x + dx, y + dy);
                        let [r, g, b, a] = pixel.0;
                        let rgb = [r as f32 / 255., g as f32 / 255., b as f32 / 255.];
                        let mx = rgb.iter().copied().fold(0f32, f32::max);
                        let mn = rgb.iter().copied().fold(1f32, f32::min);
                        let sat = (mx - mn) / mx.max(1e-6);
                        let strength = ((sat - 0.18) / 0.35).clamp(0., 1.)
                            * ((mx - 0.08) / 0.3).clamp(0., 1.)
                            * if rgb[2] - rgb[0].max(rgb[1]) * 0.55 > 0.05 {
                                1.
                            } else {
                                0.
                            };
                        let off = mx * 0.28 + 0.05;
                        for c in 0..3 {
                            pixel.0[c] = ((rgb[c] * (1. - strength)
                                + off * [0.94, 0.98, 1.][c] * strength)
                                * 255.) as u8;
                        }
                        pixel.0[3] = a;
                        mask.put_pixel(
                            dx,
                            dy,
                            image::Rgba([
                                255,
                                255,
                                255,
                                (strength * (0.55 + 0.45 * mx) * 255.) as u8,
                            ]),
                        );
                    }
                }
                app.led_masks.push(cc.egui_ctx.load_texture(
                    format!("LED {z}"),
                    egui::ColorImage::from_rgba_unmultiplied([w as usize, h as usize], &mask),
                    egui::TextureOptions::LINEAR,
                ));
            }
            let size = [image.width() as usize, image.height() as usize];
            app.photo = Some(cc.egui_ctx.load_texture(
                "G502 HERO",
                egui::ColorImage::from_rgba_unmultiplied(size, &image),
                egui::TextureOptions::LINEAR,
            ));
        }
        let _ = app.tx.send(("bridge_prefixes".into(), json!({})));
        let _ = app.tx.send(("games".into(), json!({})));
        app
    }
    fn send(&mut self, cmd: &str, args: Value) {
        let _ = self.tx.send((cmd.into(), args));
        self.message = "Traitement…".into();
        self.failed = false;
    }
    fn updates(&mut self) {
        let (snapshot, message, prefixes, games, write_done) = {
            let mut u = self.updates.lock().unwrap();
            (
                u.snapshot.take(),
                u.message.take(),
                u.prefixes.take(),
                u.games.take(),
                u.write_done.take(),
            )
        };
        if let Some(ok) = write_done {
            self.pending_write = false;
            self.write_failed = !ok;
            if !ok {
                self.dirty = true;
            }
        }
        if let Some(prefixes) = prefixes {
            self.prefixes = prefixes;
        }
        if let Some(games) = games {
            self.games = games;
        }
        if let Some(s) = snapshot {
            let initial = self.snap.settings.is_null();
            let config_changed = s.settings != self.snap.settings;
            if self.profile_names.is_empty() {
                self.profile_names = s
                    .profiles
                    .iter()
                    .map(|p| p.name.clone().unwrap_or_default())
                    .collect();
            }
            if !self.dirty && !self.pending_write && !self.write_failed && self.snap.slot != s.slot
            {
                self.slot = s.slot;
            }
            self.snap = s;
            if initial || config_changed {
                self.settings = self.snap.settings.clone();
                if !self.settings.is_object() {
                    self.settings = json!({});
                }
                let defaults = effects::defaults();
                if !self.settings["live"].is_object() {
                    self.settings["live"] = json!({"on":false,"effect":"wave","options":{}});
                }
                if !self.settings["live"]["options"].is_object() {
                    self.settings["live"]["options"] = json!({});
                }
                for (k, v) in defaults.as_object().unwrap() {
                    if !self.settings["live"]["options"][k].is_object() {
                        self.settings["live"]["options"][k] = v.clone();
                    } else {
                        for (key, value) in v.as_object().unwrap() {
                            if self.settings["live"]["options"][k][key].is_null() {
                                self.settings["live"]["options"][k][key] = value.clone();
                            }
                        }
                    }
                }
                self.settings_text =
                    serde_json::to_string_pretty(&self.settings).unwrap_or_default();
            }
            if !self.dirty && !self.pending_write && !self.write_failed {
                self.load_draft();
            }
        }
        if let Some((failed, message)) = message {
            self.failed = failed;
            self.message = message;
        }
    }
    fn load_draft(&mut self) {
        if let Some(p) = self
            .slot
            .checked_sub(1)
            .and_then(|n| self.snap.profiles.get(n))
        {
            if self.draft.is_none() {
                self.same_zones =
                    serde_json::to_value(&p.leds[0]).ok() == serde_json::to_value(&p.leds[1]).ok();
            }
            self.draft = Some(p.clone());
            self.bindings = [
                p.buttons
                    .iter()
                    .map(|&b| input::describe_binding(b))
                    .collect(),
                p.gshift
                    .iter()
                    .map(|&b| input::describe_binding(b))
                    .collect(),
            ];
        }
    }
    fn apply(&mut self) {
        if self.pending_write {
            return;
        }
        let Some(mut p) = self.draft.clone() else {
            return;
        };
        for layer in 0..2 {
            for (i, text) in self.bindings[layer].iter().enumerate() {
                match input::binding(text) {
                    Ok(b) => {
                        if layer == 0 {
                            p.buttons[i] = b
                        } else {
                            p.gshift[i] = b
                        }
                    }
                    Err(e) => {
                        self.failed = true;
                        self.message = format!("Button G{} : {e}", i + 1);
                        self.write_failed = true;
                        return;
                    }
                }
            }
        }
        match p.encode() {
            Ok(_) => {
                self.send("write_profile", json!({"slot":self.slot,"profile":p}));
                self.pending_write = true;
                self.write_failed = false;
                self.dirty = false;
            }
            Err(e) => {
                self.failed = true;
                self.message = e.to_string();
                self.write_failed = true;
            }
        }
    }
    fn header(&mut self, ui: &mut egui::Ui) {
        let r = ui.max_rect();
        let y = r.top();
        ui.painter().line_segment(
            [
                egui::pos2(r.left(), y + 63.5),
                egui::pos2(r.right(), y + 63.5),
            ],
            egui::Stroke::new(1.0f32, BORDER),
        );
        ui.painter().text(
            egui::pos2(r.left() + 24., y + 16.),
            egui::Align2::LEFT_CENTER,
            "G502 HERO",
            bold(13.),
            TEXT,
        );
        let subtitle = ui.painter().layout_job(spaced(
            &format!("ONBOARD MEMORY  ·  SLOT {}", self.snap.slot),
            11.,
            MUTED,
            1.5,
        ));
        ui.painter().galley(
            egui::pos2(r.left() + 24., y + 48. - subtitle.size().y / 2.),
            subtitle,
            MUTED,
        );
        let before = self.slot;
        let name = self
            .snap
            .profiles
            .get(self.slot.saturating_sub(1))
            .and_then(|p| p.name.as_deref())
            .filter(|s| !s.is_empty())
            .map(str::to_uppercase)
            .unwrap_or(format!("PROFILE {}", self.slot));
        ui.scope_builder(
            egui::UiBuilder::new()
                .max_rect(egui::Rect::from_min_size(
                    egui::pos2(r.center().x - 140., y + 14.),
                    egui::vec2(280., 36.),
                ))
                .layout(egui::Layout::top_down(egui::Align::LEFT)),
            |ui| {
                ui.spacing_mut().interact_size.y = 36.;
                ui.spacing_mut().button_padding = egui::vec2(16., 0.);
                for widget in [&mut ui.visuals_mut().widgets.inactive] {
                    widget.corner_radius = 17.into();
                    widget.weak_bg_fill = BG;
                }
                ui.visuals_mut().widgets.hovered.corner_radius = 17.into();
                ui.add_enabled_ui(!self.dirty && !self.pending_write, |ui| {
                    egui::ComboBox::from_id_salt("profile")
                        .width(280.)
                        .selected_text(spaced(
                            &format!("PROFILE {}:  {name}", self.slot),
                            11.,
                            TEXT,
                            1.2,
                        ))
                        .show_ui(ui, |ui| {
                            for (i, p) in self.snap.profiles.iter().enumerate() {
                                ui.selectable_value(
                                    &mut self.slot,
                                    i + 1,
                                    format!(
                                        "PROFILE {}:  {}",
                                        i + 1,
                                        p.name.as_deref().unwrap_or("Profile")
                                    ),
                                );
                            }
                        });
                });
            },
        );
        if self.slot != before {
            self.load_draft();
            self.send("activate", json!({"slot":self.slot}));
        }
        let mut status_right = r.right() - 24.;
        if let Some(p) = self.snap.profiles.get(self.snap.slot.saturating_sub(1)) {
            let dpi = p.dpi.get(self.snap.dpi_index).copied().unwrap_or(800);
            let galley = ui.painter().layout_job(spaced(
                &format!(
                    "{dpi} DPI   ·   LEVEL {}/{}",
                    self.snap.dpi_index + 1,
                    p.dpi.iter().filter(|&&v| v > 0 && v < 65535).count()
                ),
                11.,
                TEXT,
                1.,
            ));
            let pill = egui::Rect::from_min_size(
                egui::pos2(status_right - galley.size().x - 24., y + 18.),
                egui::vec2(galley.size().x + 24., 28.),
            );
            ui.painter().rect_filled(pill, 13., RAISED);
            ui.painter().rect_stroke(
                pill,
                13.,
                egui::Stroke::new(1.0f32, BORDER),
                egui::StrokeKind::Inside,
            );
            ui.painter()
                .galley(pill.center() - galley.size() / 2., galley, TEXT);
            status_right = pill.left() - 14.;
        }
        let status = if self.failed {
            self.message.as_str()
        } else if self.pending_write {
            "Saving…"
        } else if self.snap.connected {
            "Ready"
        } else {
            "Connecting…"
        };
        ui.painter()
            .with_clip_rect(egui::Rect::from_min_max(
                egui::pos2(r.center().x + 155., y),
                egui::pos2(status_right, y + 64.),
            ))
            .text(
                egui::pos2(status_right, y + 32.),
                egui::Align2::RIGHT_CENTER,
                status,
                egui::FontId::proportional(12.),
                if self.failed {
                    Color32::LIGHT_RED
                } else {
                    MUTED
                },
            );
    }
    fn device_view(&mut self, ui: &mut egui::Ui) {
        let (rect, response) = ui.allocate_exact_size(ui.available_size(), egui::Sense::click());
        let scale = (rect.width() / 990.).min(rect.height() / 1130.) * 0.96;
        let origin = rect.center() - egui::vec2(305., 555.) * scale;
        let at = |x: f32, y: f32| origin + egui::vec2(x, y) * scale;
        let pointer = if response.hovered() {
            response
                .hover_pos()
                .map(|p| egui::pos2((p.x - origin.x) / scale, (p.y - origin.y) / scale))
        } else {
            None
        };
        if let Some(photo) = &self.photo {
            ui.painter().image(
                photo.id(),
                egui::Rect::from_min_size(at(0., 0.), egui::vec2(618., 1110.) * scale),
                egui::Rect::from_min_max(egui::pos2(0., 0.), egui::pos2(1., 1.)),
                Color32::WHITE,
            );
        } else {
            ui.painter().text(
                rect.center(),
                egui::Align2::CENTER_CENTER,
                "G502 HERO",
                egui::FontId::proportional(30.),
                MUTED,
            );
        }
        for (zone, (x, y, w, h)) in [(112., 529., 41., 116.), (202., 704., 98., 100.)]
            .into_iter()
            .enumerate()
        {
            if let Some(mask) = self.led_masks.get(zone) {
                let mut rgb = [0, 0, 0];
                if let Some(colors) = self.snap.colors {
                    rgb = colors[zone];
                } else if let Some(led) = self.draft.as_ref().and_then(|p| p.leds.get(zone)) {
                    let time = self.started.elapsed().as_secs_f32();
                    rgb = match led.effect {
                        1 => led.color,
                        10 => {
                            let phase = (1.
                                - (std::f32::consts::TAU * time * 1000.
                                    / led.period_ms.max(100) as f32)
                                    .cos())
                                / 2.;
                            led.color.map(|c| (c as f32 * phase) as u8)
                        }
                        3 => {
                            let hue = (time * 1000. / led.period_ms.max(100) as f32) % 1.;
                            let c: Color32 = egui::ecolor::Hsva::new(hue, 1., 1., 1.).into();
                            [c.r(), c.g(), c.b()]
                        }
                        _ => [0, 0, 0],
                    };
                }
                if self.snap.colors.is_none() {
                    if let Some(led) = self.draft.as_ref().and_then(|p| p.leds.get(zone)) {
                        if [3, 10].contains(&led.effect) && led.intensity > 0 {
                            rgb = rgb
                                .map(|v| ((v as u16 * led.intensity as u16) / 100).min(255) as u8);
                        }
                    }
                }
                glow(
                    ui.painter(),
                    at(
                        if zone == 0 { 132. } else { 251. },
                        if zone == 0 { 586. } else { 754. },
                    ),
                    if zone == 0 { 70. * scale } else { 120. * scale },
                    rgb,
                );
                ui.painter().image(
                    mask.id(),
                    egui::Rect::from_min_size(at(x, y), egui::vec2(w, h) * scale),
                    egui::Rect::from_min_max(egui::pos2(0., 0.), egui::pos2(1., 1.)),
                    Color32::from_rgb(rgb[0], rgb[1], rgb[2]),
                );
            }
        }
        if self.tab == "light" {
            for (zone, label, x, y, end) in [
                (0, "DPI LIGHTS", 110., 586., -170.),
                (1, "LOGO", 308., 754., 780.),
            ] {
                let outline = mouse::led(zone);
                let hovered = pointer.is_some_and(|p| mouse::contains(&outline, p));
                if hovered {
                    ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
                }
                if hovered && response.clicked() {
                    self.light_zone = zone;
                    self.light_mode = 0;
                }
                let color = if self.light_zone == zone || self.same_zones || hovered {
                    ACCENT
                } else {
                    MUTED
                };
                let stroke = egui::Stroke::new(1.7f32, color);
                mouse::paint(
                    ui.painter(),
                    &outline,
                    origin,
                    scale,
                    Color32::TRANSPARENT,
                    stroke,
                );
                ui.painter()
                    .line_segment([at(x, y), at(end, y)], egui::Stroke::new(1.0f32, color));
                ui.painter().circle_filled(at(x, y), 3., color);
                ui.painter().text(
                    at(end, y - 12.),
                    if zone == 0 {
                        egui::Align2::LEFT_BOTTOM
                    } else {
                        egui::Align2::RIGHT_BOTTOM
                    },
                    label,
                    egui::FontId::proportional(14.),
                    color,
                );
            }
        }
        if self.tab == "buttons" {
            let buttons = mouse::buttons();
            let hovered = pointer.and_then(|p| mouse::hit(&buttons, p));
            if let Some(index) = hovered {
                ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
                if response.clicked() {
                    self.selected_button = index;
                }
                response.clone().on_hover_text_at_pointer(
                    self.bindings[self.layer]
                        .get(index)
                        .cloned()
                        .unwrap_or_default(),
                );
            }
            for button in &buttons {
                let selected = button.index == self.selected_button;
                let hover = hovered == Some(button.index);
                if selected || hover {
                    mouse::paint(
                        ui.painter(),
                        &button.outline,
                        origin,
                        scale,
                        Color32::from_rgba_unmultiplied(
                            20,
                            180,
                            255,
                            if selected { 70 } else { 40 },
                        ),
                        egui::Stroke::new(
                            if selected {
                                2.88 * scale
                            } else {
                                2.016 * scale
                            },
                            if selected {
                                ACCENT
                            } else {
                                Color32::from_rgb(74, 99, 120)
                            },
                        ),
                    );
                }
            }
            for button in &buttons {
                let c = at(button.badge.x, button.badge.y);
                let selected = button.index == self.selected_button;
                let hover = hovered == Some(button.index);
                if let Some(anchor) = button.anchor {
                    let a = at(anchor.x, anchor.y);
                    ui.painter().line_segment(
                        [c, a],
                        egui::Stroke::new(
                            1.728 * scale,
                            if selected {
                                ACCENT
                            } else {
                                Color32::from_rgb(92, 100, 112)
                            },
                        ),
                    );
                    ui.painter().circle_filled(
                        a,
                        3.696 * scale,
                        if selected { ACCENT } else { MUTED },
                    );
                }
                ui.painter().circle_filled(
                    c,
                    17. * scale,
                    if selected {
                        ACCENT
                    } else if hover {
                        Color32::from_rgb(45, 58, 71)
                    } else {
                        Color32::from_rgba_unmultiplied(20, 23, 27, 225)
                    },
                );
                ui.painter().circle_stroke(
                    c,
                    17. * scale,
                    egui::Stroke::new(
                        1.728 * scale,
                        if selected {
                            ACCENT
                        } else {
                            Color32::from_rgb(107, 115, 128)
                        },
                    ),
                );
                let label = match button.index {
                    9 => "›".into(),
                    10 => "‹".into(),
                    i => format!("G{}", i + 1),
                };
                ui.painter().text(
                    c,
                    egui::Align2::CENTER_CENTER,
                    label,
                    bold(if button.index >= 9 {
                        19. * scale
                    } else {
                        13. * scale
                    }),
                    if selected { BG } else { TEXT },
                );
            }
        }
    }
    fn sensitivity(&mut self, ui: &mut egui::Ui) {
        ui.label(RichText::new("Up to 5 DPI levels. G7/G8 step through them by default; the sniper level applies while DPI shift is held.").size(12.).color(MUTED));
        let Some(p) = self.draft.as_mut() else {
            return;
        };
        let (r, _) =
            ui.allocate_exact_size(egui::vec2(ui.available_width(), 96.), egui::Sense::hover());
        let left = r.left() + 14.;
        let width = r.width() - 28.;
        let y = r.top() + 40.;
        let x = |dpi: u16| left + width * ((dpi.max(100) as f32 / 100.).ln() / (256f32).ln());
        ui.painter().line_segment(
            [egui::pos2(left, y), egui::pos2(left + width, y)],
            egui::Stroke::new(4.0f32, BORDER),
        );
        for tick in [100, 400, 800, 1600, 3200, 6400, 12800, 25600] {
            let tx = x(tick);
            ui.painter().line_segment(
                [egui::pos2(tx, y + 6.), egui::pos2(tx, y + 10.)],
                egui::Stroke::new(1.0f32, MUTED),
            );
            ui.painter().text(
                egui::pos2(tx, y + 20.),
                egui::Align2::CENTER_CENTER,
                if tick >= 10000 {
                    format!("{}k", tick / 1000)
                } else {
                    tick.to_string()
                },
                egui::FontId::proportional(10.),
                MUTED,
            );
        }
        let levels: Vec<_> = p
            .dpi
            .iter()
            .enumerate()
            .filter(|(_, v)| **v > 0 && **v < 65535)
            .map(|(i, v)| (i, *v))
            .collect();
        for (n, (i, dpi)) in levels.iter().enumerate() {
            let c = egui::pos2(x(*dpi), y);
            let response = ui.interact(
                egui::Rect::from_center_size(c, egui::vec2(24., 30.)),
                ui.id().with(("dpi", i)),
                egui::Sense::drag(),
            );
            if response.dragged() {
                if let Some(pos) = response.interact_pointer_pos() {
                    p.dpi[*i] = ((100. * 256f32.powf(((pos.x - left) / width).clamp(0., 1.)) / 50.)
                        .round()
                        * 50.)
                        .clamp(100., 25600.) as u16;
                    self.dirty = true;
                }
            }
            if p.shift_dpi as usize == *i {
                ui.painter().circle_stroke(
                    c,
                    13.,
                    egui::Stroke::new(2.0f32, Color32::from_rgb(255, 90, 95)),
                );
            }
            let default = p.default_dpi as usize == *i;
            ui.painter()
                .circle_filled(c, 9., if default { ACCENT } else { RAISED });
            ui.painter().circle_stroke(
                c,
                9.,
                egui::Stroke::new(1.4f32, if default { ACCENT } else { MUTED }),
            );
            ui.painter().text(
                c,
                egui::Align2::CENTER_CENTER,
                (n + 1).to_string(),
                egui::FontId::proportional(10.),
                if default { BG } else { TEXT },
            );
            if *i == self.snap.dpi_index {
                ui.painter().text(
                    c - egui::vec2(0., 25.),
                    egui::Align2::CENTER_CENTER,
                    format!("{}", p.dpi[*i]),
                    egui::FontId::proportional(10.),
                    ACCENT,
                );
            }
        }
        section(ui, "DPI levels");
        for (n, (i, _)) in levels.iter().enumerate() {
            ui.horizontal(|ui| {
                ui.add_sized(
                    [48., 30.],
                    egui::Label::new(RichText::new(format!("Level {}", n + 1)).color(
                        if *i == self.snap.dpi_index {
                            ACCENT
                        } else {
                            TEXT
                        },
                    )),
                );
                self.dirty |= ui
                    .add_sized(
                        [94., 30.],
                        egui::DragValue::new(&mut p.dpi[*i])
                            .range(100..=25600)
                            .speed(50.)
                            .suffix(" DPI"),
                    )
                    .changed();
                if ui
                    .add(egui::Button::new(RichText::new("Default").color(
                        if p.default_dpi as usize == *i {
                            ACCENT
                        } else {
                            TEXT
                        },
                    )))
                    .clicked()
                {
                    p.default_dpi = *i as u8;
                    self.dirty = true;
                }
                if ui
                    .add(egui::Button::new(RichText::new("Sniper").color(
                        if p.shift_dpi as usize == *i {
                            Color32::from_rgb(255, 90, 95)
                        } else {
                            TEXT
                        },
                    )))
                    .clicked()
                {
                    p.shift_dpi = *i as u8;
                    self.dirty = true;
                }
                if ui
                    .add_enabled(levels.len() > 1, egui::Button::new("×").frame(false))
                    .clicked()
                {
                    p.dpi[*i] = 0;
                    let first = levels.iter().find(|(s, _)| s != i).unwrap().0 as u8;
                    if p.default_dpi as usize == *i {
                        p.default_dpi = first;
                    }
                    if p.shift_dpi as usize == *i {
                        p.shift_dpi = first;
                    }
                    self.dirty = true;
                }
            });
        }
        if ui
            .add_enabled(
                levels.len() < 5,
                egui::Button::new("+  Add level").min_size(egui::vec2(ui.available_width(), 32.)),
            )
            .clicked()
        {
            if let Some(i) = p.dpi.iter().position(|v| *v == 0 || *v == 65535) {
                p.dpi[i] = levels
                    .last()
                    .map(|(_, v)| v.saturating_mul(2).min(25600))
                    .unwrap_or(800);
                self.dirty = true;
            }
        }
        section(ui, "Report rate");
        ui.horizontal(|ui| {
            let w = (ui.available_width() - 18.) / 4.;
            for (ms, label) in [(8, "125 Hz"), (4, "250 Hz"), (2, "500 Hz"), (1, "1000 Hz")] {
                if choice(ui, label, p.rate_ms == ms, w).clicked() {
                    p.rate_ms = ms;
                    self.dirty = true;
                }
            }
        });
        ui.label(
            RichText::new("1000 Hz is the most responsive. Lower rates use slightly less CPU.")
                .size(12.)
                .color(MUTED),
        );
    }
    fn buttons(&mut self, ui: &mut egui::Ui) {
        segments(ui, &mut self.layer, &["Primary", "G-Shift"]);
        ui.label(
            RichText::new("Click a button on the mouse to change its assignment.")
                .size(12.)
                .color(MUTED),
        );
        if self.bindings[self.layer].len() <= self.selected_button {
            return;
        }
        egui::Frame::new()
            .fill(RAISED)
            .stroke(egui::Stroke::new(1.0f32, BORDER))
            .corner_radius(6)
            .inner_margin(14)
            .show(ui, |ui| {
                ui.set_min_width(ui.available_width());
                ui.label(
                    RichText::new(format!("G{}", self.selected_button + 1))
                        .size(16.)
                        .family(egui::FontFamily::Name("bold".into())),
                );
                ui.label(&self.bindings[self.layer][self.selected_button]);
                ui.horizontal(|ui| {
                    if ui.button("Restore default").clicked() {
                        let defaults = [
                            "left",
                            "right",
                            "middle",
                            "back",
                            "forward",
                            "dpi-shift",
                            "dpi-down",
                            "dpi-up",
                            "profile-cycle",
                            "tilt-right",
                            "tilt-left",
                        ];
                        self.bindings[self.layer][self.selected_button] =
                            defaults[self.selected_button].into();
                        self.dirty = true;
                    }
                    if ui.button("Disable").clicked() {
                        self.bindings[self.layer][self.selected_button] = "disabled".into();
                        self.dirty = true;
                    }
                });
            });
        segments(
            ui,
            &mut self.button_category,
            &["Commands", "Keys", "Media", "Macros"],
        );
        let groups: &[(&str, &[(&str, &str)])] = &[
            (
                "Mouse",
                &[
                    ("left", "Left click"),
                    ("right", "Right click"),
                    ("middle", "Middle click"),
                    ("back", "Back"),
                    ("forward", "Forward"),
                ],
            ),
            (
                "Scroll",
                &[
                    ("tilt-left", "Scroll left"),
                    ("tilt-right", "Scroll right"),
                    ("scroll-up", "Scroll up"),
                    ("scroll-down", "Scroll down"),
                ],
            ),
            (
                "Sensitivity",
                &[
                    ("dpi-up", "DPI up"),
                    ("dpi-down", "DPI down"),
                    ("dpi-cycle", "DPI cycle"),
                    ("dpi-default", "DPI default"),
                    ("dpi-shift", "DPI shift (sniper)"),
                ],
            ),
            (
                "Profiles",
                &[
                    ("profile-next", "Next profile"),
                    ("profile-prev", "Previous profile"),
                    ("profile-cycle", "Cycle profiles"),
                ],
            ),
            ("Layers", &[("gshift", "G-Shift (hold)")]),
        ];
        let selected = &mut self.bindings[self.layer][self.selected_button];
        if self.button_category == 0 {
            for (title, items) in groups {
                section(ui, title);
                let w = (ui.available_width() - 6.) / 2.;
                egui::Grid::new(title).num_columns(2).show(ui, |ui| {
                    for (i, (key, label)) in items.iter().enumerate() {
                        if choice(ui, label, selected == key, w).clicked() {
                            *selected = (*key).into();
                            self.dirty = true;
                        }
                        if i % 2 == 1 {
                            ui.end_row();
                        }
                    }
                });
            }
        } else if self.button_category == 1 {
            section(ui, "Shortcut");
            ui.label("Enter a key or combination, e.g. key:ctrl+c");
            self.dirty |= ui.text_edit_singleline(selected).changed();
            for (key, label) in [
                ("key:ctrl+c", "Copy"),
                ("key:ctrl+v", "Paste"),
                ("key:ctrl+z", "Undo"),
                ("key:ctrl+s", "Save"),
            ] {
                if choice(ui, label, selected == key, ui.available_width()).clicked() {
                    *selected = key.into();
                    self.dirty = true;
                }
            }
        } else if self.button_category == 2 {
            for key in [
                "play-pause",
                "next-track",
                "prev-track",
                "stop",
                "mute",
                "volume-up",
                "volume-down",
                "browser-back",
                "browser-forward",
                "calculator",
            ] {
                let value = format!("media:{key}");
                if choice(ui, key, *selected == value, ui.available_width()).clicked() {
                    *selected = value;
                    self.dirty = true;
                }
            }
        } else {
            let items = self.settings["macros"]
                .as_array()
                .cloned()
                .unwrap_or_default();
            for m in items {
                if choice(
                    ui,
                    m["name"].as_str().unwrap_or("Macro"),
                    false,
                    ui.available_width(),
                )
                .clicked()
                {
                    self.send("assign_macro",json!({"id":m["id"],"slot":self.slot,"layer":self.layer,"button":self.selected_button}));
                }
            }
            if ui.button("Create a macro").clicked() {
                self.tab = "macros".into();
                self.editing_library = true;
                self.macro_draft = new_macro();
                self.macro_id.clear();
            }
        }
    }
    fn lighting(&mut self, ui: &mut egui::Ui) {
        let mut saved: Vec<String> = self.settings["colors"]
            .as_array()
            .map(|a| {
                a.iter()
                    .filter_map(|v| v.as_str().map(str::to_owned))
                    .collect()
            })
            .unwrap_or_default();
        let old_saved = saved.clone();
        segments(ui, &mut self.light_mode, &["On the mouse", "Live effects"]);
        if self.light_mode == 0 {
            ui.label(
                RichText::new(
                    "Saved on the mouse, so it works without this app and on any computer.",
                )
                .size(12.)
                .color(MUTED),
            );
            segments(ui, &mut self.light_zone, &["DPI lights", "Logo"]);
            let link_changed = ui
                .themed_checkbox(&mut self.same_zones, "Same effect on both zones")
                .changed();

            if let Some(p) = &mut self.draft {
                let led = &mut p.leds[self.light_zone];
                let before = led.clone();
                section(ui, "Effect");
                let w = (ui.available_width() - 6.) / 2.;
                egui::Grid::new("onboard_effects")
                    .spacing([6., 6.])
                    .num_columns(2)
                    .show(ui, |ui| {
                        for (i, (n, label)) in [
                            (1, "Fixed"),
                            (10, "Breathing"),
                            (3, "Color cycle"),
                            (0, "Off"),
                        ]
                        .iter()
                        .enumerate()
                        {
                            if choice(ui, label, led.effect == *n, w).clicked() {
                                led.effect = *n;
                            }
                            if i % 2 == 1 {
                                ui.end_row();
                            }
                        }
                    });
                if [1, 10].contains(&led.effect) {
                    section(ui, "Color");
                    color_picker(ui, &mut led.color, &mut saved);
                }
                if [3, 10].contains(&led.effect) {
                    ui.horizontal(|ui| {
                        section(ui, "Rate");
                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            ui.label(RichText::new(format!("{} ms", led.period_ms)).color(MUTED));
                        });
                    });
                    ui.spacing_mut().slider_width = ui.available_width();
                    thin_slider(ui, &mut led.period_ms, 100, 20000);
                    let mut brightness = if led.intensity == 0 {
                        100
                    } else {
                        led.intensity
                    };
                    ui.horizontal(|ui| {
                        section(ui, "Brightness");
                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            ui.label(RichText::new(format!("{brightness} %")).color(MUTED));
                        });
                    });
                    if {
                        let mut n = brightness as u16;
                        let changed = thin_slider(ui, &mut n, 1, 100);
                        brightness = n as u8;
                        changed
                    } {
                        led.intensity = if brightness == 100 { 0 } else { brightness };
                    }
                }
                if serde_json::to_value(&before).ok() != serde_json::to_value(&*led).ok()
                    || (link_changed && self.same_zones)
                {
                    self.dirty = true;
                    if self.same_zones {
                        p.leds[1 - self.light_zone] = p.leds[self.light_zone].clone();
                    }
                }
            }
            if old_saved != saved {
                self.settings["colors"] = json!(saved);
                self.send("settings", self.settings.clone());
            }
            return;
        }
        ui.label(
            RichText::new("Live effects run in the background while the service is active.")
                .size(12.)
                .color(MUTED),
        );
        section(ui, "Effect");
        let effect = self.settings["live"]["effect"]
            .as_str()
            .unwrap_or("wave")
            .to_string();
        let mut next = self.settings["live"]["effect"].clone();
        let width = (ui.available_width() - 6.) / 2.;
        egui::Grid::new("live_effect_choices")
            .num_columns(2)
            .show(ui, |ui| {
                for (i, (key, label)) in [
                    ("screen", "Screen sampler"),
                    ("audio", "Audio visualizer"),
                    ("wave", "Color wave"),
                    ("dpi", "DPI colors"),
                ]
                .iter()
                .enumerate()
                {
                    if choice(ui, label, next.as_str() == Some(*key), width).clicked() {
                        next = (*key).into();
                    }
                    if i % 2 == 1 {
                        ui.end_row();
                    }
                }
            });
        let on = self.settings["live"]["on"].as_bool().unwrap_or(false);
        if next.as_str() != Some(&effect) {
            self.settings["live"]["effect"] = next.clone();
            self.send("lighting", json!({"on":on,"effect":next}));
        }
        if ui.button(if on { "Turn off" } else { "Turn on" }).clicked() {
            self.send("lighting", json!({"on":!on,"effect":next}));
        }
        let kind = next.as_str().unwrap_or("wave").to_string();
        let mut changed = false;
        if let Some(o) = self.settings["live"]["options"].get_mut(&kind) {
            match kind.as_str() {
                "wave" => {
                    ui.horizontal(|ui| {
                        ui.label("Period (s)");
                        changed |= number(ui, &mut o["period"], 0.5..=30.);
                    });
                    let mut reverse = o["reverse"].as_bool().unwrap_or(false);
                    if ui
                        .themed_checkbox(&mut reverse, "Reverse direction")
                        .changed()
                    {
                        o["reverse"] = reverse.into();
                        changed = true;
                    }
                }
                "audio" => {
                    changed |= combo(
                        ui,
                        "audio_style",
                        &mut o["style"],
                        &[
                            ("pulse", "Pulse"),
                            ("spectrum", "Spectrum"),
                            ("rainbow", "Rainbow beat"),
                        ],
                    );
                    ui.horizontal(|ui| {
                        ui.label("Sensitivity");
                        changed |= number(ui, &mut o["sensitivity"], 0.1..=5.);
                        ui.label("Color");
                        changed |= string(ui, &mut o["color"]);
                    });
                }
                "screen" => {
                    for (key, label) in [("dpi_area", "DPI lights"), ("logo_area", "Logo")] {
                        ui.horizontal(|ui| {
                            ui.label(label);
                            changed |= combo(
                                ui,
                                key,
                                &mut o[key],
                                &[
                                    ("screen", "Entire screen"),
                                    ("center", "Center"),
                                    ("left", "Left"),
                                    ("right", "Right"),
                                    ("top", "Top"),
                                    ("bottom", "Bottom"),
                                ],
                            );
                        });
                    }
                    ui.horizontal(|ui| {
                        ui.label("Smoothing");
                        changed |= number(ui, &mut o["smoothing"], 0.0..=1.0);
                    });
                }
                "dpi" => {
                    if let Some(colors) = o["colors"].as_array_mut() {
                        for (i, c) in colors.iter_mut().enumerate() {
                            ui.horizontal(|ui| {
                                ui.label(format!("Niveau {}", i + 1));
                                changed |= string(ui, c);
                            });
                        }
                    }
                }
                _ => {}
            }
            if kind != "dpi" {
                ui.horizontal(|ui| {
                    ui.label("Brightness");
                    changed |= number(ui, &mut o["brightness"], 0.0..=1.0);
                });
            }
        }
        if changed {
            self.send("settings", self.settings.clone());
        }
    }
    fn library_panel(&mut self, ui: &mut egui::Ui) {
        let macros = self.tab == "macros";
        ui.label(RichText::new(if macros {"Saved on the mouse, a macro plays on any computer. Run by G502 Hub, it can also type text and repeat while you hold the button."} else {"Make the mouse react to what you're doing: a game, an app, a YouTube video or an anime. The first rule that matches wins; when none does, your normal lighting and profile come back."}).size(12.).color(MUTED));
        if !macros {
            egui::Frame::new()
                .fill(RAISED)
                .stroke(egui::Stroke::new(1.0f32, BORDER))
                .corner_radius(6)
                .inner_margin(14)
                .show(ui, |ui| {
                    ui.set_min_width(ui.available_width());
                    section(ui, "Right now");
                    ui.label(
                        RichText::new(if self.snap.context.app.is_empty() {
                            "No active application detected".into()
                        } else {
                            format!(
                                "In front: {} — {}",
                                self.snap.context.app, self.snap.context.title
                            )
                        })
                        .color(MUTED),
                    );
                    for m in &self.snap.context.media {
                        if m.status == "Playing" {
                            ui.label(
                                RichText::new(format!("Playing: {} — {}", m.title, m.artist))
                                    .color(MUTED),
                            );
                        }
                    }
                    if let Some(r) = &self.snap.active_rule {
                        ui.label(
                            RichText::new(format!("Rule: {}", r["name"].as_str().unwrap_or("")))
                                .color(ACCENT),
                        );
                    }
                });
        }
        section(ui, if macros { "Your macros" } else { "Rules" });
        let key = if macros { "macros" } else { "rules" };
        let items = self.settings[key].as_array().cloned().unwrap_or_default();
        for (index, item) in items.iter().enumerate() {
            let id = item["id"].as_str().unwrap_or("").to_string();
            let name = item["name"].as_str().unwrap_or("Untitled");
            let active = !macros
                && self
                    .snap
                    .active_rule
                    .as_ref()
                    .map(|r| r["id"] == id)
                    .unwrap_or(false);
            egui::Frame::new()
                .fill(RAISED)
                .stroke(egui::Stroke::new(
                    1.0f32,
                    if active { ACCENT } else { BORDER },
                ))
                .corner_radius(6)
                .inner_margin(14)
                .show(ui, |ui| {
                    ui.set_min_width(ui.available_width());
                    ui.horizontal(|ui| {
                        ui.label(
                            RichText::new(name)
                                .size(14.)
                                .family(egui::FontFamily::Name("bold".into())),
                        );
                        if active {
                            ui.colored_label(ACCENT, "ACTIVE");
                        }
                    });
                    if macros {
                        ui.label(
                            RichText::new(format!(
                                "{} steps · {}",
                                item["steps"].as_array().map(Vec::len).unwrap_or(0),
                                if item["target"] == "mouse" {
                                    "Saved on the mouse"
                                } else {
                                    "Run by G502 Hub"
                                }
                            ))
                            .color(MUTED),
                        );
                    } else {
                        ui.label(
                            RichText::new(format!(
                                "While {} matches “{}”",
                                item["trigger"].as_str().unwrap_or("app"),
                                item["value"].as_str().unwrap_or("")
                            ))
                            .color(MUTED),
                        );
                        let mut enabled = item["enabled"].as_bool().unwrap_or(true);
                        if ui.themed_checkbox(&mut enabled, "Enabled").changed() {
                            self.settings["rules"][index]["enabled"] = enabled.into();
                            self.send("settings", self.settings.clone());
                        }
                    }
                    ui.horizontal(|ui| {
                        if ui.button("Edit").clicked() {
                            self.editing_library = true;
                            if macros {
                                self.macro_id = id.clone();
                                self.macro_draft = item.clone();
                            } else {
                                self.rule_id = id.clone();
                                self.rule_draft = item.clone();
                            }
                        }
                        if !macros {
                            for (label, delta) in [("Up", -1isize), ("Down", 1)] {
                                let to = index as isize + delta;
                                if ui
                                    .add_enabled(
                                        to >= 0 && to < items.len() as isize,
                                        egui::Button::new(label),
                                    )
                                    .clicked()
                                {
                                    self.settings["rules"]
                                        .as_array_mut()
                                        .unwrap()
                                        .swap(index, to as usize);
                                    self.send("settings", self.settings.clone());
                                }
                            }
                        }
                        if ui.button("Delete").clicked() {
                            if macros {
                                self.send("delete_macro", json!({"id":id}));
                            } else {
                                self.settings["rules"]
                                    .as_array_mut()
                                    .unwrap()
                                    .retain(|r| r["id"] != id);
                                self.send("settings", self.settings.clone());
                            }
                        }
                    });
                });
        }
        if ui
            .add_sized(
                [ui.available_width(), 34.],
                egui::Button::new(
                    RichText::new(if macros {
                        "+  New macro"
                    } else {
                        "+  Add rule"
                    })
                    .color(BG),
                )
                .fill(ACCENT),
            )
            .clicked()
        {
            self.editing_library = true;
            if macros {
                self.macro_id.clear();
                self.macro_draft = new_macro();
            } else {
                self.rule_id.clear();
                self.rule_draft = new_rule();
            }
        }
    }
    fn choose_profile_file(&mut self, operation: &str, slot: usize, ctx: &egui::Context) {
        let shared = self.picked_file.clone();
        let ctx = ctx.clone();
        let operation = operation.to_owned();
        std::thread::spawn(move || {
            let mut command = std::process::Command::new("zenity");
            command
                .arg("--file-selection")
                .arg(if operation == "restore" {
                    "--file-filter=G502 backups | *.json"
                } else {
                    "--file-filter=G502 profiles | *.g502profile"
                });
            if operation == "export_profile" {
                command
                    .args(["--save", "--confirm-overwrite", "--title=Export profile"])
                    .arg(format!(
                        "--filename={}",
                        config::home()
                            .join(format!("Downloads/G502-profile-{slot}.g502profile"))
                            .display()
                    ));
            } else {
                command.arg("--title=Import profile");
            }
            let output = command.output();
            match output {
                Ok(result) if result.status.success() => {
                    let path = String::from_utf8_lossy(&result.stdout).trim().to_string();
                    if !path.is_empty() {
                        *shared.lock().unwrap() = Some((operation, slot, Some(path)));
                    }
                }
                Ok(_) => {}
                Err(_) => {
                    *shared.lock().unwrap() = Some((operation, slot, None));
                }
            }
            ctx.request_repaint();
        });
    }
    fn profile_cards(&mut self, ui: &mut egui::Ui) {
        ui.heading("Onboard memory");
        ui.label(RichText::new("These 5 profiles live on the mouse and work on any computer. G9 switches between the included ones.").color(MUTED));
        ui.add_space(4.);
        let profiles = self.snap.profiles.clone();
        let width = (ui.available_width() - 24.) / 2.;
        egui::Grid::new("profile_cards").num_columns(2).spacing([14.,14.]).show(ui,|ui|{
            for (i,p) in profiles.iter().enumerate(){let slot=i+1;
                egui::Frame::new().fill(RAISED).stroke(egui::Stroke::new(1.0f32,if slot==self.snap.slot{ACCENT}else{BORDER})).corner_radius(6).inner_margin(14).show(ui,|ui|{
                    ui.with_layout(egui::Layout::top_down(egui::Align::LEFT),|ui|{
                        ui.set_width(width-30.);ui.spacing_mut().item_spacing.y=8.;ui.spacing_mut().interact_size.y=18.;
                        ui.horizontal(|ui|{ui.label(spaced(&format!("SLOT {slot}"),11.,MUTED,1.5));ui.with_layout(egui::Layout::right_to_left(egui::Align::Center),|ui|{if slot==self.snap.slot{ui.label(spaced("ACTIVE",11.,ACCENT,1.));}});});
                        if let Some(name)=self.profile_names.get_mut(i){let response=ui.add_enabled(!self.pending_write&&(!self.dirty||self.slot==slot),egui::TextEdit::singleline(name).hint_text(format!("Profile {slot}")).margin(egui::vec2(8.,6.)).char_limit(24).desired_width(f32::INFINITY));if response.lost_focus()&&name!=p.name.as_deref().unwrap_or("") {let name=name.clone();self.slot=slot;self.load_draft();if let Some(d)=&mut self.draft{d.name=Some(name);self.dirty=true;}}}
                        ui.label(RichText::new(format!("{} Hz  ·  {} DPI",1000/p.rate_ms.max(1)as usize,p.dpi.iter().filter(|&&v|v>0&&v<65535).map(u16::to_string).collect::<Vec<_>>().join(" / "))).size(12.).color(MUTED));
                        ui.horizontal(|ui|{for(z,led)in p.leds.iter().enumerate(){let(r,_)=ui.allocate_exact_size(egui::vec2(12.,12.),egui::Sense::hover());ui.painter().circle_filled(r.center(),6.,if led.effect==3{ACCENT}else{Color32::from_rgb(led.color[0],led.color[1],led.color[2])});ui.label(RichText::new(format!("{}: {}",if z==0{"DPI"}else{"Logo"},match led.effect{0=>"off",1=>"fixed",3=>"color cycle",10=>"breathing",_=>"effect"})).size(12.).color(MUTED));}});
                        let mut enabled=self.snap.directory.as_ref().and_then(|d|d.entries.get(i)).map(|e|e.enabled).unwrap_or(true);
                        if ui.themed_checkbox(&mut enabled,"Included when G9 cycles profiles").changed(){self.send("profile_enabled",json!({"slot":slot,"enabled":enabled}));}
                        ui.add_enabled_ui(!self.dirty&&!self.pending_write,|ui|{ui.horizontal(|ui|{
                            if slot!=self.snap.slot&&ui.add(egui::Button::new(RichText::new("Activate").color(BG)).fill(ACCENT)).clicked(){self.slot=slot;self.load_draft();self.send("activate",json!({"slot":slot}));}
                            ui.menu_button("More  ▾",|ui|{
                                if ui.button("Export to a file…").clicked(){self.choose_profile_file("export_profile",slot,ui.ctx());ui.close();}
                                if ui.button("Import from a file…").clicked(){self.choose_profile_file("import_profile",slot,ui.ctx());ui.close();}
                                ui.separator();if ui.button("Reset to factory profile").clicked(){self.profile_action=Some(("reset_profile".into(),json!({"slot":slot}),format!("Replace slot {slot} with its factory profile?")));ui.close();}
                                ui.menu_button("Copy this profile to",|ui|{for other in 1..=profiles.len(){if other!=slot&&ui.button(format!("Slot {other}")).clicked(){self.profile_action=Some(("copy_profile".into(),json!({"from":slot,"to":other}),format!("Overwrite slot {other} with slot {slot}?")));ui.close();}}});
                            });
                        });});
                    });
                });if i%2==1{ui.end_row();}
            }
        });
    }
    fn record(&mut self, ctx: &egui::Context) {
        if !self.recording {
            return;
        }
        let events = ctx.input(|i| i.events.clone());
        for e in events {
            if let egui::Event::Key {
                key,
                physical_key,
                pressed,
                repeat,
                modifiers,
                ..
            } = e
            {
                if key == egui::Key::Escape {
                    self.recording = false;
                    break;
                }
                if repeat {
                    continue;
                }
                let key = physical_key.unwrap_or(key);
                let mut name = format!("{key:?}").to_lowercase();
                name = match name.as_str() {
                    "arrowup" => "up",
                    "arrowdown" => "down",
                    "arrowleft" => "left",
                    "arrowright" => "right",
                    "escape" => "esc",
                    "backspace" => "backspace",
                    "space" => "space",
                    "enter" => "enter",
                    "pageup" => "pageup",
                    "pagedown" => "pagedown",
                    n if n.starts_with("num") => &n[3..],
                    n => n,
                }
                .to_string();
                let mut combo = String::new();
                if modifiers.ctrl {
                    combo.push_str("ctrl+");
                }
                if modifiers.shift {
                    combo.push_str("shift+");
                }
                if modifiers.alt {
                    combo.push_str("alt+");
                }
                if modifiers.mac_cmd || modifiers.command && !modifiers.ctrl {
                    combo.push_str("meta+");
                }
                combo.push_str(&name);
                if input::combo(&combo).is_err() {
                    continue;
                }
                let now = Instant::now();
                if let Some(last) = self.record_at {
                    let ms = now.duration_since(last).as_millis();
                    if ms >= 20 {
                        self.macro_draft["steps"]
                            .as_array_mut()
                            .unwrap()
                            .push(json!({"kind":"delay","args":{"ms":ms.min(600000)}}));
                    }
                }
                self.record_at = Some(now);
                self.macro_draft["steps"].as_array_mut().unwrap().push(
                    json!({"kind":if pressed{"key-down"}else{"key-up"},"args":{"combo":combo}}),
                );
            }
        }
    }
    fn macros(&mut self, ui: &mut egui::Ui) {
        section(ui, "Name");
        string(ui, &mut self.macro_draft["name"]);
        section(ui, "Runs");
        choices(
            ui,
            "target",
            &mut self.macro_draft["target"],
            &[("mouse", "Saved on the mouse"), ("app", "Run by G502 Hub")],
            2,
        );
        section(ui, "Plays");
        choices(
            ui,
            "mode",
            &mut self.macro_draft["mode"],
            &[
                ("once", "Once per press"),
                ("while-held", "Repeats while held"),
                ("toggle", "Press to start, again to stop"),
            ],
            1,
        );
        section(ui, "Steps");
        let steps = self.macro_draft["steps"]
            .as_array()
            .cloned()
            .unwrap_or_default();
        egui::Frame::new()
            .fill(RAISED)
            .corner_radius(4)
            .inner_margin(8)
            .show(ui, |ui| {
                egui::ScrollArea::vertical()
                    .id_salt("macro_steps")
                    .max_height(170.)
                    .min_scrolled_height(160.)
                    .show(ui, |ui| {
                        ui.set_min_width(ui.available_width());
                        for (i, step) in steps.iter().enumerate() {
                            let args = &step["args"];
                            let label = match step["kind"].as_str().unwrap_or("") {
                                "key" | "key-down" | "key-up" => format!(
                                    "{}  {}",
                                    step["kind"].as_str().unwrap(),
                                    args["combo"].as_str().unwrap_or("")
                                ),
                                "text" => format!("Type: {}", args["text"].as_str().unwrap_or("")),
                                "delay" => format!("Wait {} ms", args["ms"]),
                                "click" | "button-down" | "button-up" => format!(
                                    "{} {}",
                                    step["kind"].as_str().unwrap(),
                                    args["button"].as_str().unwrap_or("")
                                ),
                                "media" => format!("Media: {}", args["key"].as_str().unwrap_or("")),
                                _ => format!("{} {}", step["kind"].as_str().unwrap_or(""), args),
                            };
                            if ui
                                .selectable_label(self.step_selected == i, label)
                                .clicked()
                            {
                                self.step_selected = i;
                            }
                        }
                    });
            });
        ui.horizontal(|ui| {
            if ui
                .add_enabled(
                    self.step_selected > 0 && self.step_selected < steps.len(),
                    egui::Button::new("Up"),
                )
                .clicked()
            {
                self.macro_draft["steps"]
                    .as_array_mut()
                    .unwrap()
                    .swap(self.step_selected, self.step_selected - 1);
                self.step_selected -= 1;
            }
            if ui
                .add_enabled(
                    self.step_selected + 1 < steps.len(),
                    egui::Button::new("Down"),
                )
                .clicked()
            {
                self.macro_draft["steps"]
                    .as_array_mut()
                    .unwrap()
                    .swap(self.step_selected, self.step_selected + 1);
                self.step_selected += 1;
            }
            if ui
                .add_enabled(
                    self.step_selected < steps.len(),
                    egui::Button::new("Remove"),
                )
                .clicked()
            {
                self.macro_draft["steps"]
                    .as_array_mut()
                    .unwrap()
                    .remove(self.step_selected);
                self.step_selected = self.step_selected.saturating_sub(1);
            }
        });
        section(ui, "Add a step");
        segments(
            ui,
            &mut self.step_tab,
            &["Key", "Text", "Wait", "Mouse", "Media"],
        );
        let mut add = None;
        match self.step_tab {
            0 => {
                ui.add(
                    egui::TextEdit::singleline(&mut self.step_text)
                        .hint_text("Key or shortcut, e.g. ctrl+c")
                        .desired_width(f32::INFINITY),
                );
                if ui.button("Add key").clicked() {
                    match input::combo(&self.step_text) {
                        Ok(_) => add = Some(json!({"kind":"key","args":{"combo":self.step_text}})),
                        Err(e) => {
                            self.failed = true;
                            self.message = e.to_string();
                        }
                    }
                }
                if ui
                    .button(if self.recording {
                        "Stop recording (Esc)"
                    } else {
                        "Record keys"
                    })
                    .clicked()
                {
                    self.recording = !self.recording;
                    self.record_at = None;
                }
                ui.label(
                    RichText::new("Recording keeps the waits between your key presses.")
                        .size(12.)
                        .color(MUTED),
                );
            }
            1 => {
                ui.add(
                    egui::TextEdit::singleline(&mut self.step_text)
                        .hint_text("Text to type, e.g. gg wp")
                        .desired_width(f32::INFINITY),
                );
                if ui
                    .add_enabled(!self.step_text.is_empty(), egui::Button::new("Add text"))
                    .clicked()
                {
                    add = Some(json!({"kind":"text","args":{"text":self.step_text}}));
                }
            }
            2 => {
                ui.add(
                    egui::DragValue::new(&mut self.step_wait)
                        .range(1..=60000)
                        .suffix(" ms"),
                );
                if ui.button("Add wait").clicked() {
                    add = Some(json!({"kind":"delay","args":{"ms":self.step_wait}}));
                }
            }
            3 => {
                let w = (ui.available_width() - 6.) / 2.;
                egui::Grid::new("macro_mouse")
                    .num_columns(2)
                    .show(ui, |ui| {
                        for (i, (key, label)) in [
                            ("left", "Left click"),
                            ("right", "Right click"),
                            ("middle", "Middle click"),
                            ("back", "Back"),
                            ("forward", "Forward"),
                        ]
                        .iter()
                        .enumerate()
                        {
                            if choice(ui, label, false, w).clicked() {
                                add = Some(json!({"kind":"click","args":{"button":key}}));
                            }
                            if i % 2 == 1 {
                                ui.end_row();
                            }
                        }
                    });
                ui.horizontal(|ui| {
                    for (label, amount) in [("Scroll up", 1), ("Scroll down", -1)] {
                        if ui.button(label).clicked() {
                            add = Some(json!({"kind":"scroll","args":{"amount":amount}}));
                        }
                    }
                });
            }
            _ => {
                for key in [
                    "play-pause",
                    "next",
                    "previous",
                    "stop",
                    "volume-up",
                    "volume-down",
                    "mute",
                ] {
                    if choice(ui, key, false, ui.available_width()).clicked() {
                        add = Some(json!({"kind":"media","args":{"key":key}}));
                    }
                }
            }
        }
        if let Some(step) = add {
            self.macro_draft["steps"].as_array_mut().unwrap().push(step);
        }
        ui.add_space(12.);
        ui.horizontal(|ui| {
            if ui
                .add(egui::Button::new(RichText::new("Save macro").color(BG)).fill(ACCENT))
                .clicked()
            {
                self.recording = false;
                self.macro_id = self.macro_draft["id"].as_str().unwrap_or("").into();
                self.send("save_macro", self.macro_draft.clone());
                self.editing_library = false;
            }
            if ui.button("Cancel").clicked() {
                self.recording = false;
                self.editing_library = false;
            }
        });
    }
    fn rules(&mut self, ui: &mut egui::Ui) {
        section(ui, "Name");
        string(ui, &mut self.rule_draft["name"]);
        section(ui, "When");
        choices(
            ui,
            "trigger",
            &mut self.rule_draft["trigger"],
            &[
                ("game", "A game is running"),
                ("app", "An app is in front"),
                ("title", "Window title contains"),
                ("media", "Playing media contains"),
            ],
            2,
        );
        if self.rule_draft["trigger"] == "game" {
            let current = self.rule_draft["value"].as_str().unwrap_or("any");
            let label = self
                .games
                .iter()
                .find(|g| g["appid"].as_str() == Some(current) || g["appid"].to_string() == current)
                .and_then(|g| g["name"].as_str())
                .unwrap_or(if current == "any" {
                    "Any game"
                } else {
                    current
                })
                .to_string();
            egui::ComboBox::from_id_salt("rule_game")
                .width(ui.available_width())
                .selected_text(label)
                .show_ui(ui, |ui| {
                    if ui
                        .selectable_label(self.rule_draft["value"] == "any", "Any game")
                        .clicked()
                    {
                        self.rule_draft["value"] = "any".into();
                    }
                    for game in &self.games {
                        if ui
                            .selectable_label(false, game["name"].as_str().unwrap_or("Game"))
                            .clicked()
                        {
                            self.rule_draft["value"] = game["appid"]
                                .as_str()
                                .map(str::to_owned)
                                .unwrap_or_else(|| game["appid"].to_string())
                                .into();
                        }
                    }
                });
        } else {
            string(ui, &mut self.rule_draft["value"]);
            ui.label(
                RichText::new(if self.rule_draft["trigger"] == "app" {
                    "Matches the app exactly."
                } else {
                    "Matches text in the title, ignoring case."
                })
                .size(12.)
                .color(MUTED),
            );
        }
        section(ui, "Lighting");
        if self.rule_draft["lighting"].is_null() {
            self.rule_draft["lighting"] = "".into();
        }
        choices(
            ui,
            "rule_lighting",
            &mut self.rule_draft["lighting"],
            &[
                ("", "Don't change"),
                ("color", "Color"),
                ("breathing", "Breathing"),
                ("art", "Cover art colors"),
                ("game", "Game-driven"),
                ("screen", "Screen sampler"),
                ("audio", "Audio visualizer"),
                ("wave", "Color wave"),
                ("dpi", "DPI colors"),
            ],
            2,
        );
        if ["color", "breathing"].contains(&self.rule_draft["lighting"].as_str().unwrap_or("")) {
            let hex = self.rule_draft["color"].as_str().unwrap_or("#14b4ff");
            let mut rgb = [20, 180, 255];
            if hex.len() == 7 {
                for (i, c) in rgb.iter_mut().enumerate() {
                    *c = u8::from_str_radix(&hex[1 + i * 2..3 + i * 2], 16).unwrap_or(*c);
                }
            }
            let mut saved: Vec<String> = self.settings["colors"]
                .as_array()
                .map(|a| {
                    a.iter()
                        .filter_map(|v| v.as_str().map(str::to_owned))
                        .collect()
                })
                .unwrap_or_default();
            let old_saved = saved.clone();
            if color_picker(ui, &mut rgb, &mut saved) {
                self.rule_draft["color"] =
                    format!("#{:02x}{:02x}{:02x}", rgb[0], rgb[1], rgb[2]).into();
            }
            if old_saved != saved {
                self.settings["colors"] = json!(saved);
                self.send("settings", self.settings.clone());
            }
        }
        if self.rule_draft["lighting"] == "breathing" {
            section(ui, "Breathing speed");
            let mut n = self.rule_draft["period_ms"].as_u64().unwrap_or(4000) as u16;
            if thin_slider(ui, &mut n, 1000, 12000) {
                self.rule_draft["period_ms"] = n.into();
            }
        }
        section(ui, "Profile slot");
        ui.label(RichText::new("Switch to an onboard profile (its DPI levels, buttons and report rate) while the rule matches.").size(12.).color(MUTED));
        let width = (ui.available_width() - 12.) / 3.;
        egui::Grid::new("rule_slot").num_columns(3).show(ui, |ui| {
            for i in 0..6 {
                let label = if i == 0 {
                    "Don't change".into()
                } else {
                    format!("Slot {i}")
                };
                if choice(
                    ui,
                    &label,
                    self.rule_draft["slot"].as_u64().unwrap_or(0) == i,
                    width,
                )
                .clicked()
                {
                    self.rule_draft["slot"] = if i == 0 { Value::Null } else { i.into() };
                }
                if i % 3 == 2 {
                    ui.end_row();
                }
            }
        });
        ui.add_space(12.);
        ui.horizontal(|ui| {
            if ui
                .add(egui::Button::new(RichText::new("Save rule").color(BG)).fill(ACCENT))
                .clicked()
            {
                if !self.settings["rules"].is_array() {
                    self.settings["rules"] = json!([]);
                }
                self.rule_id = self.rule_draft["id"].as_str().unwrap_or("").into();
                let mut draft = self.rule_draft.clone();
                if draft["lighting"] == "" {
                    draft["lighting"] = Value::Null;
                }
                let list = self.settings["rules"].as_array_mut().unwrap();
                if let Some(i) = list.iter().position(|r| r["id"] == self.rule_id) {
                    list[i] = draft;
                } else {
                    list.push(draft);
                }
                self.send("settings", self.settings.clone());
                self.editing_library = false;
            }
            if ui.button("Cancel").clicked() {
                self.editing_library = false;
            }
        });
    }
    fn settings_page(&mut self, ui: &mut egui::Ui) {
        section(ui, "Startup");
        let mut auto = config::autostart_path().exists();
        if ui
            .themed_checkbox(&mut auto, "Start G502 Hub in the background when I log in")
            .changed()
        {
            if let Err(e) = config::autostart(auto) {
                self.failed = true;
                self.message = e.to_string();
            }
        }

        ui.label(format!(
            "PID : {} · {}",
            self.snap.pid,
            if self.snap.connected {
                "Souris connectée"
            } else {
                "En attente de la souris"
            }
        ));
        for f in &self.snap.firmware {
            ui.label(f);
        }
        ui.separator();
        let mut osd = self.settings["osd"].as_bool().unwrap_or(true);
        if ui
            .themed_checkbox(&mut osd, "Show DPI and profile changes on screen")
            .changed()
        {
            self.settings["osd"] = osd.into();
            self.send("settings", self.settings.clone());
        }
        ui.horizontal_wrapped(|ui| {
            ui.label("Keyboard layout");
            let mut layout = self.settings["keyboard_layout"]
                .as_str()
                .map(str::to_owned)
                .unwrap_or_else(input::layout);
            let response = ui.text_edit_singleline(&mut layout);
            if response.changed() {
                self.settings["keyboard_layout"] = layout.clone().into();
            }
            if response.lost_focus()
                && self.settings["keyboard_layout"] != self.snap.settings["keyboard_layout"]
            {
                self.settings["keyboard_layout"] = layout.into();
                self.send("settings", self.settings.clone());
            }
        });
        ui.label(
            RichText::new("Keyboard layout used for text macros (e.g. fr, us, be).")
                .small()
                .color(Color32::GRAY),
        );
        if ui.button("Refresh mouse").clicked() {
            self.send("refresh", json!({}));
            self.dirty = false;
        }
        ui.label(format!("Réglages : {}", config::config_dir().display()));
        ui.label(format!(
            "Sauvegardes : {}",
            config::data_dir().join("backups").display()
        ));
        ui.label("Closing this window frees the settings interface. Macros, rules and live lighting continue in the background.");
        if ui.button("Quit G502 Hub completely").clicked() {
            let _ = ipc::request("stop", json!({}));
            ui.ctx().send_viewport_cmd(egui::ViewportCommand::Close);
        }
        ui.separator();
        ui.collapsing("LIGHTSYNC bridge for Proton games", |ui| {
            ui.label("Close the game before changing its Wine prefix.");
            egui::ComboBox::from_id_salt("proton_prefix")
                .selected_text("Choose a Steam prefix…")
                .show_ui(ui, |ui| {
                    for p in &self.prefixes {
                        if ui
                            .selectable_label(false, p["name"].as_str().unwrap_or("Jeu"))
                            .clicked()
                        {
                            self.bridge_path = p["path"].as_str().unwrap_or("").into();
                        }
                    }
                });
            ui.text_edit_singleline(&mut self.bridge_path);
            ui.horizontal_wrapped(|ui| {
                if ui.button("Install LIGHTSYNC").clicked() {
                    self.send("bridge_install", json!({"path":self.bridge_path}));
                }
                if ui.button("Remove LIGHTSYNC").clicked() {
                    self.send("bridge_remove", json!({"path":self.bridge_path}));
                }
                if ui.button("Refresh").clicked() {
                    self.send("bridge_prefixes", json!({}));
                }
            });
        });
        ui.separator();
        ui.collapsing("Advanced settings (import / export)", |ui| {
            ui.add(
                egui::TextEdit::multiline(&mut self.settings_text)
                    .code_editor()
                    .desired_rows(15)
                    .desired_width(f32::INFINITY),
            );
            if ui.button("Apply advanced settings").clicked() {
                match serde_json::from_str::<Value>(&self.settings_text) {
                    Ok(v) => self.send("settings", v),
                    Err(e) => {
                        self.message = e.to_string();
                        self.failed = true;
                    }
                }
            }
        });
    }
}
impl eframe::App for App {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.updates();
        let picked = self.picked_file.lock().unwrap().take();
        if let Some((cmd, slot, path)) = picked {
            if let Some(path) = path {
                if cmd == "export_profile" {
                    self.send(&cmd, json!({"slot":slot,"path":path}));
                } else {
                    self.profile_action = Some((
                        cmd.clone(),
                        json!({"slot":slot,"path":path}),
                        if cmd == "restore" {
                            "Restore all mouse profiles from this backup?".into()
                        } else {
                            format!("Replace slot {slot} with the selected file?")
                        },
                    ));
                }
            } else {
                self.slot = slot;
                self.file_operation = cmd;
                self.profile_file_dialog = true;
            }
        }
        self.record(ctx);
        egui::TopBottomPanel::top("topbar")
            .exact_height(64.)
            .frame(egui::Frame::new().fill(BG).inner_margin(0))
            .show(ctx, |ui| self.header(ui));
        egui::SidePanel::left("navigation")
            .exact_width(92.)
            .resizable(false)
            .frame(egui::Frame::new().fill(BG).inner_margin(0))
            .show(ctx, |ui| {
                let rail = ui.max_rect();
                ui.painter().line_segment(
                    [rail.right_top(), rail.right_bottom()],
                    egui::Stroke::new(1.0f32, BORDER),
                );
                ui.spacing_mut().item_spacing.y = 4.;
                ui.add_space(16.);
                for (key, label) in &TABS[..6] {
                    if rail_button(ui, key, label, self.tab == *key) {
                        self.tab = (*key).into();
                        self.editing_library = false;
                    }
                }
                ui.with_layout(egui::Layout::bottom_up(egui::Align::LEFT), |ui| {
                    ui.add_space(16.);
                    for (key, label) in TABS[6..].iter().rev() {
                        if rail_button(ui, key, label, self.tab == *key) {
                            self.tab = (*key).into();
                            self.editing_library = false;
                        }
                    }
                });
            });
        let wide = matches!(self.tab.as_str(), "profiles" | "about");
        egui::SidePanel::left("settings_panel").exact_width(410.).resizable(false).frame(egui::Frame::new().fill(PANEL).stroke(egui::Stroke::new(1.0f32,BORDER)).inner_margin(egui::Margin::symmetric(22,22))).show(ctx,|ui| {
            if self.tab!="profiles" {ui.heading(match self.tab.as_str(){"light"=>"Lighting","sens"=>"Sensitivity","buttons"=>"Assignments","profiles"=>"Onboard profiles","macros"=>if self.editing_library{"Macro"}else{"Macros"},"rules"=>if self.editing_library{"Rule"}else{"Games & apps"},"about"=>"About",_=>"Settings"});ui.add_space(12.);}

            if self.write_failed {ui.colored_label(Color32::LIGHT_RED,&self.message);ui.horizontal(|ui|{if ui.button("Retry").clicked(){self.write_failed=false;self.apply();}if ui.button("Discard").clicked(){self.dirty=false;self.write_failed=false;self.load_draft();}});}
            egui::ScrollArea::vertical().id_salt(("side",&self.tab)).auto_shrink([false,false]).show(ui,|ui| {
                if !self.snap.connected && self.tab!="about" {ui.label("Waiting for the G502 HERO…");}
                else {match self.tab.as_str(){"sens"=>self.sensitivity(ui),"buttons"=>self.buttons(ui),"light"=>self.lighting(ui),"settings"=>self.settings_page(ui),"profiles"=>{section(ui,"Device");ui.label("G502 HERO");ui.label(format!("Firmware {}",self.snap.firmware.join(" / ")));section(ui,"Backups");ui.label(RichText::new("A full backup is taken automatically before the first change each session.").color(MUTED));if ui.add_sized([ui.available_width(),34.],egui::Button::new("Back up now")).clicked(){self.send("backup",json!({}));}ui.add_space(10.);if ui.add_sized([ui.available_width(),34.],egui::Button::new("Restore a backup…")).clicked(){self.choose_profile_file("restore",self.slot,ui.ctx());}if ui.add_sized([ui.available_width(),34.],egui::Button::new("Open backups folder")).clicked(){let _=std::process::Command::new("xdg-open").arg(config::data_dir().join("backups")).spawn();}},"macros"|"rules"=>{if self.editing_library {if ui.button("<  Back").clicked(){self.editing_library=false;self.recording=false;}if self.tab=="macros" {self.macros(ui);}else{self.rules(ui);}}else{self.library_panel(ui);}},"about"=>{ui.label("G502 Hub");ui.label(RichText::new("A native settings app for the Logitech G502 HERO.").color(MUTED));section(ui,"Version");ui.label("Rust · 0.1.0 · experimental");ui.hyperlink_to("Original project","https://github.com/Ahmedxsaad/g502-hub");},_=>{}}}
            });
        });
        egui::CentralPanel::default().frame(egui::Frame::new().fill(BG).inner_margin(if wide {24}else{0})).show(ctx,|ui|{
            if !self.snap.connected {ui.centered_and_justified(|ui|{ui.label("Connect your G502 HERO to get started");});return;}
            if wide {egui::ScrollArea::vertical().id_salt(("center",&self.tab)).show(ui,|ui|{match self.tab.as_str(){"profiles"=>self.profile_cards(ui),"macros"=>{ui.heading("Macro editor");ui.add_space(18.);self.macros(ui);},"rules"=>{ui.heading("Automatic rules");ui.add_space(18.);self.rules(ui);},_=>{ui.heading("G502 Hub");ui.label("Native Rust interface and background service");ui.add_space(20.);ui.label("Based on Ahmed Saad's G502 Hub. Licensed under GPL-3.0-or-later.");}}});}
            else {self.device_view(ui);}
        });
        if let Some((cmd, args, prompt)) = self.profile_action.clone() {
            egui::Window::new("Confirm profile change")
                .collapsible(false)
                .resizable(false)
                .show(ctx, |ui| {
                    ui.label(prompt);
                    ui.label("Your backup keeps the current profile.");
                    ui.horizontal(|ui| {
                        if ui.button("Confirm").clicked() {
                            self.send(&cmd, args);
                            self.profile_action = None;
                        }
                        if ui.button("Cancel").clicked() {
                            self.profile_action = None;
                        }
                    });
                });
        }
        if self.profile_file_dialog {
            egui::Window::new("Profile file")
                .collapsible(false)
                .show(ctx, |ui| {
                    ui.label("Profile file (.g502profile)");
                    ui.text_edit_singleline(&mut self.path);
                    ui.horizontal(|ui| {
                        if ui.button("Choose").clicked() {
                            self.profile_action = Some((
                                "import_profile".into(),
                                json!({"slot":self.slot,"path":self.path}),
                                format!("Replace slot {} with the selected file?", self.slot),
                            ));
                            self.profile_file_dialog = false;
                        }
                        if ui.button("Cancel").clicked() {
                            self.profile_file_dialog = false;
                        }
                    });
                });
        }
        if self.dirty {
            let signature =
                serde_json::to_string(&(&self.draft, &self.bindings)).unwrap_or_default();
            if signature != self.edit_signature {
                self.edit_signature = signature;
                self.edit_since = Instant::now();
                self.write_failed = false;
            }
            if !self.pending_write
                && !self.write_failed
                && !ctx.input(|i| i.pointer.any_down())
                && !ctx.wants_keyboard_input()
                && self.edit_since.elapsed() > Duration::from_millis(350)
            {
                self.apply();
            }
        }
        if ctx.input(|i| i.viewport().close_requested()) && (self.dirty || self.pending_write) {
            ctx.send_viewport_cmd(egui::ViewportCommand::CancelClose);
            self.close_after_save = true;
            if !self.pending_write && !self.write_failed {
                self.apply();
            }
        }
        if self.close_after_save && !self.dirty && !self.pending_write && !self.write_failed {
            ctx.send_viewport_cmd(egui::ViewportCommand::Close);
        }
        if self.screenshot.is_some()
            && !self.screenshot_sent
            && self.started.elapsed() > Duration::from_secs(2)
            && self.snap.connected
        {
            ctx.send_viewport_cmd(egui::ViewportCommand::Screenshot(egui::UserData::default()));
            self.screenshot_sent = true;
        }
        let screenshot = ctx.input(|i| {
            i.events.iter().find_map(|e| {
                if let egui::Event::Screenshot { image, .. } = e {
                    Some(image.clone())
                } else {
                    None
                }
            })
        });
        if let (Some(path), Some(image)) = (&self.screenshot, screenshot) {
            let bytes: Vec<_> = image.pixels.iter().flat_map(|p| p.to_array()).collect();
            let _ = image::save_buffer(
                path,
                &bytes,
                image.size[0] as u32,
                image.size[1] as u32,
                image::ColorType::Rgba8,
            );
            if self.smoke {
                eprintln!(
                    "UI smoke: {} frames in {:.2}s",
                    ctx.cumulative_frame_nr(),
                    self.started.elapsed().as_secs_f64()
                );
                ctx.send_viewport_cmd(egui::ViewportCommand::Close);
            }
        }
        if self.smoke
            && self.screenshot.is_none()
            && !self.smoke_done
            && self.started.elapsed() > Duration::from_secs(3)
            && self.snap.connected
        {
            self.smoke_done = true;
            ctx.send_viewport_cmd(egui::ViewportCommand::Close);
        }
        if self.smoke && self.started.elapsed() > Duration::from_secs(20) {
            ctx.send_viewport_cmd(egui::ViewportCommand::Close);
        }
        let preview_visible = self.snap.connected
            && !matches!(self.tab.as_str(), "profiles" | "about")
            && ctx.input(|i| i.viewport().minimized != Some(true));
        self.animate_live.store(
            preview_visible && self.snap.colors.is_some(),
            Ordering::Relaxed,
        );
        let saved_animation = self.snap.colors.is_none()
            && self
                .draft
                .as_ref()
                .is_some_and(|p| p.leds.iter().any(|led| [3, 10].contains(&led.effect)));
        ctx.request_repaint_after(Duration::from_millis(
            if preview_visible && (saved_animation || self.snap.colors.is_some()) {
                33
            } else {
                300
            },
        ));
    }
}
fn main() {
    let args: Vec<_> = std::env::args().collect();
    let result = (|| -> anyhow::Result<()> {
        if args.iter().any(|a| a == "--take-over") {
            ipc::stop_python()?;
        }
        ipc::ensure_service()?;
        if args.iter().any(|a| a == "--background") {
            return Ok(());
        }
        let screenshot = args
            .iter()
            .position(|a| a == "--screenshot")
            .and_then(|i| args.get(i + 1))
            .map(PathBuf::from);
        let smoke = args.iter().any(|a| a == "--smoke-test");
        let options = eframe::NativeOptions {
            viewport: egui::ViewportBuilder::default()
                .with_title("G502 Hub Rust")
                .with_app_id("g502-hub-rust")
                .with_inner_size([1280., 800.])
                .with_min_inner_size([1100., 700.]),
            ..Default::default()
        };
        eframe::run_native(
            "G502 Hub Rust",
            options,
            Box::new(move |cc| Ok(Box::new(App::new(cc, screenshot, smoke)))),
        )
        .map_err(|e| anyhow::anyhow!("{e}"))?;
        Ok(())
    })();
    if let Err(e) = result {
        eprintln!("{e:#}");
        std::process::exit(1);
    }
}
