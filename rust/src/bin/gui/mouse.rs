//! Photo-space outlines from the original G502 Hub photo skin.
//! Rendering and hit testing share these paths, including the narrow thumb buttons.
use eframe::egui::{self, Pos2};

pub struct Button {
    pub index: usize,
    pub outline: Vec<Pos2>,
    pub badge: Pos2,
    pub anchor: Option<Pos2>,
}
fn polygon(points: &[(f32, f32)]) -> Vec<Pos2> {
    points.iter().map(|&(x, y)| egui::pos2(x, y)).collect()
}
fn circle(x: f32, y: f32, r: f32) -> Vec<Pos2> {
    (0..64)
        .map(|i| {
            let a = i as f32 * std::f32::consts::TAU / 64.;
            egui::pos2(x + r * a.cos(), y + r * a.sin())
        })
        .collect()
}
fn rounded(x: f32, y: f32, w: f32, h: f32, r: f32) -> Vec<Pos2> {
    let mut points = vec![];
    for (cx, cy, start) in [
        (x + w - r, y + r, -90.),
        (x + w - r, y + h - r, 0.),
        (x + r, y + h - r, 90.),
        (x + r, y + r, 180.),
    ] {
        for i in 0..=12 {
            let a = (start + i as f32 * 7.5).to_radians();
            points.push(egui::pos2(cx + r * a.cos(), cy + r * a.sin()));
        }
    }
    points
}
pub fn buttons() -> Vec<Button> {
    let make = |index, outline, badge, anchor| Button {
        index,
        outline,
        badge,
        anchor,
    };
    vec![
        make(10, circle(276., 322., 17.), egui::pos2(276., 322.), None),
        make(9, circle(432., 322., 17.), egui::pos2(432., 322.), None),
        make(
            2,
            rounded(318., 236., 68., 166., 22.),
            egui::pos2(352., 318.),
            None,
        ),
        make(
            8,
            rounded(336., 520., 54., 58., 8.),
            egui::pos2(363., 548.),
            None,
        ),
        make(
            7,
            polygon(&[(108., 258.), (162., 246.), (165., 330.), (102., 338.)]),
            egui::pos2(136., 294.),
            None,
        ),
        make(
            6,
            polygon(&[(100., 342.), (165., 334.), (163., 402.), (94., 396.)]),
            egui::pos2(132., 368.),
            None,
        ),
        make(
            5,
            polygon(&[(82., 398.), (95., 392.), (101., 437.), (86., 444.)]),
            egui::pos2(-70., 400.),
            Some(egui::pos2(91., 418.)),
        ),
        make(
            4,
            polygon(&[
                (79., 446.),
                (96., 436.),
                (109., 600.),
                (99., 613.),
                (85., 603.),
            ]),
            egui::pos2(-70., 520.),
            Some(egui::pos2(93., 525.)),
        ),
        make(
            3,
            polygon(&[
                (100., 628.),
                (114., 620.),
                (140., 700.),
                (151., 772.),
                (141., 778.),
                (124., 712.),
            ]),
            egui::pos2(-70., 690.),
            Some(egui::pos2(124., 695.)),
        ),
        make(
            0,
            polygon(&[
                (168., 163.),
                (298., 88.),
                (300., 505.),
                (232., 540.),
                (166., 520.),
                (160., 400.),
            ]),
            egui::pos2(232., 300.),
            None,
        ),
        make(
            1,
            polygon(&[
                (402., 88.),
                (522., 150.),
                (562., 250.),
                (575., 400.),
                (565., 515.),
                (470., 560.),
                (402., 505.),
            ]),
            egui::pos2(482., 300.),
            None,
        ),
    ]
}
pub fn led(zone: usize) -> Vec<Pos2> {
    if zone == 0 {
        rounded(110., 527., 45., 120., 12.)
    } else {
        circle(251., 754., 56.)
    }
}
fn cross(a: Pos2, b: Pos2, c: Pos2) -> f32 {
    (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)
}
pub fn contains(path: &[Pos2], p: Pos2) -> bool {
    let mut inside = false;
    for i in 0..path.len() {
        let a = path[i];
        let b = path[(i + 1) % path.len()];
        if cross(a, b, p).abs() < 0.001 && (p - a).dot(p - b) <= 0. {
            return true;
        }
        if (a.y > p.y) != (b.y > p.y) && p.x < (b.x - a.x) * (p.y - a.y) / (b.y - a.y) + a.x {
            inside = !inside;
        }
    }
    inside
}
pub fn hit(buttons: &[Button], p: Pos2) -> Option<usize> {
    buttons
        .iter()
        .find(|b| p.distance(b.badge) <= 17. || contains(&b.outline, p))
        .map(|b| b.index)
}
/// Ear clipping also handles the concave thumb outlines without filling their bounding boxes.
pub fn triangles(path: &[Pos2]) -> Vec<[usize; 3]> {
    let area: f32 = path
        .iter()
        .zip(path.iter().cycle().skip(1))
        .take(path.len())
        .map(|(a, b)| a.x * b.y - b.x * a.y)
        .sum();
    let sign = area.signum();
    let mut remaining: Vec<_> = (0..path.len()).collect();
    let mut out = vec![];
    while remaining.len() > 3 {
        let mut ear = None;
        for i in 0..remaining.len() {
            let a = remaining[(i + remaining.len() - 1) % remaining.len()];
            let b = remaining[i];
            let c = remaining[(i + 1) % remaining.len()];
            if cross(path[a], path[b], path[c]) * sign <= 0.0001 {
                continue;
            }
            if remaining.iter().any(|&v| {
                v != a
                    && v != b
                    && v != c
                    && cross(path[a], path[b], path[v]) * sign >= 0.
                    && cross(path[b], path[c], path[v]) * sign >= 0.
                    && cross(path[c], path[a], path[v]) * sign >= 0.
            }) {
                continue;
            }
            ear = Some((i, [a, b, c]));
            break;
        }
        let Some((i, triangle)) = ear else {
            break;
        };
        out.push(triangle);
        remaining.remove(i);
    }
    if remaining.len() == 3 {
        out.push([remaining[0], remaining[1], remaining[2]]);
    }
    out
}
pub fn paint(
    painter: &egui::Painter,
    path: &[Pos2],
    origin: Pos2,
    scale: f32,
    fill: egui::Color32,
    stroke: egui::Stroke,
) {
    let points: Vec<_> = path.iter().map(|p| origin + p.to_vec2() * scale).collect();
    if fill != egui::Color32::TRANSPARENT {
        let mut mesh = egui::Mesh::default();
        for &p in &points {
            mesh.colored_vertex(p, fill);
        }
        for [a, b, c] in triangles(path) {
            mesh.add_triangle(a as u32, b as u32, c as u32);
        }
        painter.add(egui::Shape::mesh(mesh));
    }
    painter.add(egui::Shape::closed_line(points, stroke));
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn every_button_responds_on_its_body_and_badge() {
        let all = buttons();
        for b in &all {
            assert_eq!(hit(&all, b.badge), Some(b.index));
            if let Some(p) = b.anchor {
                assert_eq!(hit(&all, p), Some(b.index));
            }
        }
        assert_eq!(hit(&all, egui::pos2(220., 180.)), Some(0));
        assert_eq!(hit(&all, egui::pos2(500., 450.)), Some(1));
        assert_eq!(hit(&all, egui::pos2(350., 250.)), Some(2));
    }
    #[test]
    fn background_and_shape_corners_are_not_buttons() {
        let all = buttons();
        for p in [
            egui::pos2(170., 90.),
            egui::pos2(570., 90.),
            egui::pos2(318., 236.),
            egui::pos2(310., 450.),
            egui::pos2(-87., 383.),
            egui::pos2(200., 700.),
        ] {
            assert_eq!(hit(&all, p), None, "{p:?}");
        }
        assert!(!contains(&led(1), egui::pos2(300., 800.)));
        assert!(!contains(&led(0), egui::pos2(110., 527.)));
    }
    #[test]
    fn triangulation_preserves_every_outline_area() {
        for b in buttons() {
            let path = b.outline;
            let area: f32 = path
                .iter()
                .zip(path.iter().cycle().skip(1))
                .take(path.len())
                .map(|(a, b)| a.x * b.y - b.x * a.y)
                .sum::<f32>()
                .abs()
                / 2.;
            let tris = triangles(&path);
            assert_eq!(tris.len(), path.len() - 2);
            let filled: f32 = tris
                .iter()
                .map(|&[a, b, c]| cross(path[a], path[b], path[c]).abs() / 2.)
                .sum();
            assert!(
                (area - filled).abs() < 1.,
                "{}: {area} vs {filled}",
                b.index
            );
        }
    }
}
