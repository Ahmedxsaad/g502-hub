//! Native window actions drawn into the application's own header.
use super::{BG, BORDER, MUTED, RAISED, TEXT};
use eframe::egui::{self, Color32};
pub const CONTROLS_WIDTH: f32 = 118.;

pub fn fullscreen(ctx: &egui::Context) -> bool {
    ctx.data(|data| data.get_temp::<bool>(egui::Id::new("window_fullscreen")))
        .unwrap_or_else(|| ctx.input(|i| i.viewport().fullscreen.unwrap_or(false)))
}
pub fn set_fullscreen(ctx: &egui::Context, on: bool) {
    // Track our requested mode as some X11 window managers report fullscreen late.
    ctx.data_mut(|data| data.insert_temp(egui::Id::new("window_fullscreen"), on));
    ctx.send_viewport_cmd(egui::ViewportCommand::Fullscreen(on));
}
pub fn controls(ui: &mut egui::Ui, header: egui::Rect) -> bool {
    let ctx = ui.ctx().clone();
    let maximized = ctx.input(|i| i.viewport().maximized.unwrap_or(false));
    let fullscreen = fullscreen(&ctx);
    let left = header.right() - CONTROLS_WIDTH - 16.;
    let mut close = false;
    for (index, tip) in [
        "Minimize",
        if maximized || fullscreen {
            "Restore window"
        } else {
            "Maximize"
        },
        "Close window",
    ]
    .into_iter()
    .enumerate()
    {
        let rect = egui::Rect::from_min_size(
            egui::pos2(left + index as f32 * 40., header.top() + 16.),
            egui::vec2(34., 32.),
        );
        let response = ui.interact(
            rect,
            ui.id().with(("window_control", index)),
            egui::Sense::click(),
        );
        let active = response.hovered() || response.is_pointer_button_down_on();
        if active {
            ui.painter().rect_filled(
                rect,
                6.,
                if index == 2 {
                    Color32::from_rgb(180, 49, 62)
                } else {
                    RAISED
                },
            );
        }
        let stroke = egui::Stroke::new(1.4f32, if active { TEXT } else { MUTED });
        let c = rect.center();
        match index {
            0 => {
                ui.painter()
                    .line_segment([c + egui::vec2(-5., 3.), c + egui::vec2(5., 3.)], stroke);
            }
            1 if maximized || fullscreen => {
                let back = egui::Rect::from_min_size(c + egui::vec2(-2., -6.), egui::vec2(8., 8.));
                ui.painter()
                    .rect_stroke(back, 1., stroke, egui::StrokeKind::Inside);
                let front = egui::Rect::from_min_size(c + egui::vec2(-5., -3.), egui::vec2(8., 8.));
                ui.painter()
                    .rect_filled(front, 1., if active { RAISED } else { BG });
                ui.painter()
                    .rect_stroke(front, 1., stroke, egui::StrokeKind::Inside);
            }
            1 => {
                ui.painter().rect_stroke(
                    egui::Rect::from_center_size(c, egui::vec2(10., 10.)),
                    1.,
                    stroke,
                    egui::StrokeKind::Inside,
                );
            }
            _ => {
                ui.painter()
                    .line_segment([c + egui::vec2(-4., -4.), c + egui::vec2(4., 4.)], stroke);
                ui.painter()
                    .line_segment([c + egui::vec2(-4., 4.), c + egui::vec2(4., -4.)], stroke);
            }
        }
        if response.on_hover_text(tip).clicked() {
            match index {
                0 => ctx.send_viewport_cmd(egui::ViewportCommand::Minimized(true)),
                1 => {
                    if fullscreen {
                        set_fullscreen(&ctx, false);
                    } else {
                        ctx.send_viewport_cmd(egui::ViewportCommand::Maximized(!maximized));
                    }
                }
                _ => close = true,
            }
        }
    }
    ui.painter().line_segment(
        [
            egui::pos2(left - 12., header.top() + 23.),
            egui::pos2(left - 12., header.top() + 41.),
        ],
        egui::Stroke::new(1.0f32, BORDER),
    );
    close
}

pub fn drag_region(ui: &mut egui::Ui, rect: egui::Rect, id: &str) {
    let response = ui.interact(rect, ui.id().with(id), egui::Sense::click_and_drag());
    if response.double_clicked() {
        let maximized = ui.ctx().input(|i| i.viewport().maximized.unwrap_or(false));
        let fullscreen = fullscreen(ui.ctx());
        if fullscreen {
            set_fullscreen(ui.ctx(), false);
        } else {
            ui.ctx()
                .send_viewport_cmd(egui::ViewportCommand::Maximized(!maximized));
        }
    } else if response.drag_started() {
        ui.ctx().send_viewport_cmd(egui::ViewportCommand::StartDrag);
    }
}

pub fn resize_edges(ctx: &egui::Context) {
    if fullscreen(ctx) || ctx.input(|i| i.viewport().maximized == Some(true)) {
        return;
    }
    let Some(pos) = ctx.input(|i| i.pointer.hover_pos()) else {
        return;
    };
    let r = ctx.content_rect();
    let border = 5.;
    let corner = 12.;
    if !r.contains(pos) {
        return;
    }
    let left = pos.x < r.left() + border;
    let right = pos.x > r.right() - border;
    let top = pos.y < r.top() + border;
    let bottom = pos.y > r.bottom() - border;
    let nw = (left && pos.y < r.top() + corner) || (top && pos.x < r.left() + corner);
    let ne = (right && pos.y < r.top() + corner) || (top && pos.x > r.right() - corner);
    let sw = (left && pos.y > r.bottom() - corner) || (bottom && pos.x < r.left() + corner);
    let se = (right && pos.y > r.bottom() - corner) || (bottom && pos.x > r.right() - corner);
    use egui::{CursorIcon as C, ResizeDirection as D};
    let action = if nw {
        Some((D::NorthWest, C::ResizeNorthWest))
    } else if ne {
        Some((D::NorthEast, C::ResizeNorthEast))
    } else if sw {
        Some((D::SouthWest, C::ResizeSouthWest))
    } else if se {
        Some((D::SouthEast, C::ResizeSouthEast))
    } else if left {
        Some((D::West, C::ResizeWest))
    } else if right {
        Some((D::East, C::ResizeEast))
    } else if top {
        Some((D::North, C::ResizeNorth))
    } else if bottom {
        Some((D::South, C::ResizeSouth))
    } else {
        None
    };
    if let Some((direction, cursor)) = action {
        ctx.set_cursor_icon(cursor);
        if ctx.input(|i| i.pointer.button_pressed(egui::PointerButton::Primary)) {
            ctx.send_viewport_cmd(egui::ViewportCommand::BeginResize(direction));
        }
    }
}
