use anyhow::{Result, bail, ensure};
use serde::{Deserialize, Serialize};

pub fn crc16(data: &[u8]) -> u16 {
    data.iter().fold(0xffffu16, |mut crc, &b| {
        crc ^= (b as u16) << 8;
        for _ in 0..8 {
            crc = if crc & 0x8000 != 0 {
                (crc << 1) ^ 0x1021
            } else {
                crc << 1
            };
        }
        crc
    })
}
pub fn sealed(mut data: Vec<u8>) -> Result<Vec<u8>> {
    ensure!(data.len() >= 2, "Sector too short");
    let n = data.len();
    let crc = crc16(&data[..n - 2]).to_be_bytes();
    data[n - 2..].copy_from_slice(&crc);
    Ok(data)
}
pub fn crc_ok(data: &[u8]) -> bool {
    data.len() >= 2
        && crc16(&data[..data.len() - 2])
            == u16::from_be_bytes([data[data.len() - 2], data[data.len() - 1]])
}
pub fn hex(data: &[u8]) -> String {
    data.iter().map(|x| format!("{x:02x}")).collect()
}
pub fn unhex(text: &str) -> Result<Vec<u8>> {
    ensure!(text.len().is_multiple_of(2), "Invalid hex length");
    text.as_bytes()
        .chunks(2)
        .map(|p| Ok(u8::from_str_radix(std::str::from_utf8(p)?, 16)?))
        .collect()
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Led {
    pub effect: u8,
    pub color: [u8; 3],
    pub period_ms: u16,
    pub intensity: u8,
    pub raw: Vec<u8>,
}
impl Default for Led {
    fn default() -> Self {
        Self {
            effect: 0,
            color: [0; 3],
            period_ms: 8000,
            intensity: 0,
            raw: vec![0; 11],
        }
    }
}
impl Led {
    pub fn decode(raw: &[u8]) -> Result<Self> {
        ensure!(raw.len() == 11, "Invalid LED block");
        Ok(Self {
            effect: raw[0],
            color: [raw[1], raw[2], raw[3]],
            period_ms: match raw[0] {
                10 => u16::from_be_bytes([raw[4], raw[5]]),
                3 => u16::from_be_bytes([raw[6], raw[7]]),
                _ => 8000,
            },
            intensity: match raw[0] {
                10 => raw[7],
                3 => raw[8],
                _ => 0,
            },
            raw: raw.to_vec(),
        })
    }
    pub fn encode(&self) -> [u8; 11] {
        let mut out = [0; 11];
        if self.raw.len() == 11 && self.raw[0] == self.effect {
            out.copy_from_slice(&self.raw);
        }
        out[0] = self.effect;
        match self.effect {
            1 => out[1..4].copy_from_slice(&self.color),
            10 => {
                out[1..4].copy_from_slice(&self.color);
                out[4..6].copy_from_slice(&self.period_ms.to_be_bytes());
                out[7] = self.intensity;
            }
            3 => {
                out[6..8].copy_from_slice(&self.period_ms.to_be_bytes());
                out[8] = self.intensity;
            }
            _ => {}
        }
        out
    }
    pub fn fixed(rgb: [u8; 3]) -> Self {
        Self {
            effect: 1,
            color: rgb,
            ..Default::default()
        }
    }
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Profile {
    pub rate_ms: u8,
    pub default_dpi: u8,
    pub shift_dpi: u8,
    pub dpi: [u16; 5],
    pub color: [u8; 3],
    pub angle_snapping: u8,
    pub buttons: Vec<[u8; 4]>,
    pub gshift: Vec<[u8; 4]>,
    pub name: Option<String>,
    pub leds: Vec<Led>,
    pub alt_leds: Vec<Led>,
    pub raw: Vec<u8>,
}
impl Profile {
    pub fn decode(raw: &[u8]) -> Result<Self> {
        ensure!(raw.len() >= 254, "Profile too short");
        let bytes = &raw[160..208];
        let name = if bytes.iter().all(|&b| b == 255) {
            None
        } else {
            Some(String::from_utf16_lossy(
                &bytes
                    .chunks_exact(2)
                    .map(|p| u16::from_le_bytes([p[0], p[1]]))
                    .take_while(|&c| c != 0)
                    .collect::<Vec<_>>(),
            ))
        };
        Ok(Self {
            rate_ms: raw[0],
            default_dpi: raw[1],
            shift_dpi: raw[2],
            dpi: std::array::from_fn(|i| u16::from_le_bytes([raw[3 + i * 2], raw[4 + i * 2]])),
            color: [raw[13], raw[14], raw[15]],
            angle_snapping: raw[17],
            buttons: raw[32..96]
                .chunks_exact(4)
                .map(|p| p.try_into().unwrap())
                .collect(),
            gshift: raw[96..160]
                .chunks_exact(4)
                .map(|p| p.try_into().unwrap())
                .collect(),
            name,
            leds: vec![Led::decode(&raw[208..219])?, Led::decode(&raw[219..230])?],
            alt_leds: vec![Led::decode(&raw[230..241])?, Led::decode(&raw[241..252])?],
            raw: raw.to_vec(),
        })
    }
    pub fn encode(&self) -> Result<Vec<u8>> {
        ensure!(
            self.raw.len() >= 254
                && self.buttons.len() == 16
                && self.gshift.len() == 16
                && self.leds.len() == 2
                && self.alt_leds.len() == 2,
            "Invalid profile structure"
        );
        ensure!(
            [1, 2, 4, 8].contains(&self.rate_ms),
            "Report interval must be 1, 2, 4 or 8 ms"
        );
        ensure!(
            self.default_dpi < 5 && self.shift_dpi < 5,
            "Invalid DPI slot"
        );
        ensure!(
            self.dpi.iter().any(|&d| d != 0 && d != 65535),
            "Enable at least one DPI level"
        );
        ensure!(
            self.dpi
                .iter()
                .all(|&d| d == 0 || d == 65535 || (100..=25600).contains(&d)),
            "DPI must be 100–25600"
        );
        let mut raw = self.raw.clone();
        raw[0] = self.rate_ms;
        raw[1] = self.default_dpi;
        raw[2] = self.shift_dpi;
        for (i, d) in self.dpi.iter().enumerate() {
            raw[3 + i * 2..5 + i * 2].copy_from_slice(&d.to_le_bytes());
        }
        raw[13..16].copy_from_slice(&self.color);
        raw[17] = self.angle_snapping;
        for (i, b) in self.buttons.iter().chain(self.gshift.iter()).enumerate() {
            raw[32 + i * 4..36 + i * 4].copy_from_slice(b);
        }
        raw[160..208].fill(if self.name.is_some() { 0 } else { 255 });
        if let Some(name) = &self.name {
            let mut units = Vec::new();
            for c in name.chars() {
                let mut pair = [0; 2];
                let u = c.encode_utf16(&mut pair);
                if units.len() + u.len() > 24 {
                    break;
                }
                units.extend_from_slice(u);
            }
            for (i, c) in units.iter().enumerate() {
                raw[160 + 2 * i..162 + 2 * i].copy_from_slice(&c.to_le_bytes());
            }
        }
        for (i, led) in self.leds.iter().chain(self.alt_leds.iter()).enumerate() {
            raw[208 + i * 11..219 + i * 11].copy_from_slice(&led.encode());
        }
        sealed(raw)
    }
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Entry {
    pub sector: u16,
    pub enabled: bool,
    pub flag: u8,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Directory {
    pub entries: Vec<Entry>,
    pub terminator: [u8; 4],
    pub raw: Vec<u8>,
}
impl Directory {
    pub fn decode(raw: &[u8]) -> Result<Option<Self>> {
        ensure!(raw.len() >= 6, "Directory too short");
        if raw[..raw.len() - 2].iter().all(|&b| b == 0)
            || raw[..raw.len() - 2].iter().all(|&b| b == 255)
        {
            return Ok(None);
        }
        let mut entries = vec![];
        for p in raw[..raw.len() - 2].chunks_exact(4) {
            let sector = u16::from_be_bytes([p[0], p[1]]);
            if sector == 65535 {
                return Ok(Some(Self {
                    entries,
                    terminator: p.try_into().unwrap(),
                    raw: raw.to_vec(),
                }));
            }
            entries.push(Entry {
                sector,
                enabled: p[2] != 0,
                flag: p[3],
            });
        }
        bail!("Directory has no terminator")
    }
    pub fn encode(&self) -> Result<Vec<u8>> {
        ensure!(
            self.entries.iter().any(|e| e.enabled),
            "At least one profile must remain enabled"
        );
        let mut raw = self.raw.clone();
        ensure!(
            (self.entries.len() + 1) * 4 + 2 <= raw.len(),
            "Directory overflow"
        );
        for (i, e) in self.entries.iter().enumerate() {
            raw[i * 4..i * 4 + 2].copy_from_slice(&e.sector.to_be_bytes());
            raw[i * 4 + 2] = u8::from(e.enabled);
            raw[i * 4 + 3] = e.flag;
        }
        let end = self.entries.len() * 4;
        raw[end..end + 4].copy_from_slice(&self.terminator);
        sealed(raw)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn known_crc() {
        assert_eq!(crc16(b"123456789"), 0x29b1);
    }
    #[test]
    fn crc_rejects_damage() {
        let mut d = sealed(vec![7; 256]).unwrap();
        assert!(crc_ok(&d));
        d[0] ^= 1;
        assert!(!crc_ok(&d));
    }
    #[test]
    fn led_unknown_preserved() {
        let raw = [10, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
        assert_eq!(Led::decode(&raw).unwrap().encode(), raw);
    }
    #[test]
    fn malformed_data_rejected() {
        assert!(Profile::decode(&[0; 30]).is_err());
        assert!(Directory::decode(&[0; 3]).is_err());
        assert!(unhex("é").is_err());
    }
}
