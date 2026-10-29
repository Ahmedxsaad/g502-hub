//! Same Hann-window FFT, gain, gate, release and beat detector as Python's Analyzer.
use crate::effects::CaptureData;
use rustfft::{FftPlanner, num_complex::Complex};
use std::sync::Arc;
pub struct Analyzer {
    fft: Arc<dyn rustfft::Fft<f64>>,
    window: Vec<f64>,
    buf: Vec<f64>,
    peaks: [f64; 4],
    out: [f64; 4],
    centroid: f64,
    history: Vec<f64>,
    history_i: usize,
    history_full: bool,
    since_beat: f64,
}
impl Default for Analyzer {
    fn default() -> Self {
        Self {
            fft: FftPlanner::new().plan_fft_forward(1024),
            window: (0..1024)
                .map(|i| 0.5 - 0.5 * (std::f64::consts::TAU * i as f64 / 1023.).cos())
                .collect(),
            buf: vec![],
            peaks: [10f64.powf(-50. / 20.); 4],
            out: [0.; 4],
            centroid: 0.,
            history: vec![0.; 86],
            history_i: 0,
            history_full: false,
            since_beat: 0.15,
        }
    }
}
impl Analyzer {
    pub fn feed(&mut self, samples: &[i16]) -> Option<CaptureData> {
        self.buf.extend(samples.iter().map(|n| *n as f64 / 32768.));
        let mut result = None;
        let mut beat = false;
        while self.buf.len() >= 1024 {
            let mut spectrum: Vec<_> = self.buf[..1024]
                .iter()
                .zip(&self.window)
                .map(|(s, w)| Complex::new(s * w, 0.))
                .collect();
            self.fft.process(&mut spectrum);
            let norm = self.window.iter().sum::<f64>() / 2.;
            let mut values = [0f64; 4];
            let mut csum = 0.;
            let mut cweight = 0.;
            for (i, n) in spectrum.iter().take(513).enumerate() {
                let f = i as f64 * 44100. / 1024.;
                let power = n.norm_sqr() / norm.powi(2);
                for (b, (lo, hi)) in [(20., 10000.), (20., 150.), (150., 2000.), (2000., 10000.)]
                    .into_iter()
                    .enumerate()
                {
                    if f >= lo && f < hi {
                        values[b] += power;
                    }
                }
                if (50. ..=8000.).contains(&f) {
                    csum += power;
                    cweight += f * power;
                }
            }
            let floor = 10f64.powf(-50. / 20.);
            let peak_decay = 0.5f64.powf(1. / (5. * 44100. / 512.));
            let release = (-1f64 / (0.12 * 44100. / 512.)).exp();
            for b in 0..4 {
                values[b] = values[b].sqrt();
                let relative = if b == 0 {
                    0.
                } else {
                    self.peaks[0] * 10f64.powf(-24. / 20.)
                };
                self.peaks[b] = values[b]
                    .max(self.peaks[b] * peak_decay)
                    .max(floor)
                    .max(relative);
                let db = 20. * values[b].max(1e-12).log10();
                let gate = ((db + 50.) / 6.).clamp(0., 1.);
                let target = (values[b] / self.peaks[b]).min(1.) * gate;
                self.out[b] = target.max(self.out[b] * release);
            }
            if values[0] > floor && csum > 0. {
                let c = ((cweight / csum / 50.).ln() / (8000f64 / 50.).ln()).clamp(0., 1.);
                self.centroid += (c - self.centroid) * 0.3;
            }
            let history = if self.history_full {
                &self.history[..]
            } else {
                &self.history[..self.history_i]
            };
            let average = if history.is_empty() {
                0.
            } else {
                history.iter().sum::<f64>() / history.len() as f64
            };
            self.since_beat += 512. / 44100.;
            let hit = history.len() >= 4
                && values[1] > floor * 2.
                && values[1].powi(2) > 2. * average
                && self.since_beat >= 0.15;
            if hit {
                self.since_beat = 0.;
            }
            beat |= hit;
            self.history[self.history_i] = values[1].powi(2);
            self.history_i = (self.history_i + 1) % self.history.len();
            self.history_full |= self.history_i == 0;
            result = Some(CaptureData {
                updated: Some(std::time::Instant::now()),
                level: self.out[0] as f32,
                bass: self.out[1] as f32,
                mid: self.out[2] as f32,
                treble: self.out[3] as f32,
                centroid: self.centroid as f32,
                beat,
                ..Default::default()
            });
            self.buf.drain(..512);
        }
        result
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn silence_and_pitch_follow_reference_bands() {
        let mut a = Analyzer::default();
        let silent = a.feed(&[0; 2048]).unwrap();
        assert_eq!(silent.level, 0.);
        assert!(!silent.beat);
        for (freq, band) in [(86., 0), (1000., 1), (6000., 2)] {
            let mut a = Analyzer::default();
            let samples: Vec<_> = (0..8192)
                .map(|i| ((std::f64::consts::TAU * freq * i as f64 / 44100.).sin() * 16000.) as i16)
                .collect();
            let out = a.feed(&samples).unwrap();
            let levels = [out.bass, out.mid, out.treble];
            assert!(levels[band] > 0.95);
            assert!(out.level > 0.95);
        }
    }
}
