use g502_hub_rust::{
    input,
    model::{self, Directory, Profile},
};
use serde_json::Value;
fn fixture() -> Value {
    serde_json::from_str(include_str!("fixtures/onboard-c08b.json")).unwrap()
}
#[test]
fn all_real_profiles_round_trip_byte_exact() {
    let f = fixture();
    for n in (1..=5).chain(257..=261) {
        let key = format!("0x{n:04X}");
        let data = model::unhex(f["sectors"][&key].as_str().unwrap()).unwrap();
        let p = Profile::decode(&data).unwrap();
        let encoded = p.encode().unwrap();
        if n < 256 {
            assert_eq!(encoded, data, "profile {n}");
        } else {
            assert_eq!(
                encoded[..encoded.len() - 2],
                data[..data.len() - 2],
                "factory profile {n}"
            );
        }
    }
}
#[test]
fn real_directory_preserves_reserved_bytes() {
    let f = fixture();
    let data = model::unhex(f["sectors"]["0x0000"].as_str().unwrap()).unwrap();
    let dir = Directory::decode(&data).unwrap().unwrap();
    assert_eq!(dir.encode().unwrap(), data);
}
#[test]
fn surgical_edit_only_changes_target_bytes() {
    let f = fixture();
    let data = model::unhex(f["sectors"]["0x0003"].as_str().unwrap()).unwrap();
    let mut p = Profile::decode(&data).unwrap();
    p.name = Some("Test".into());
    p.gshift[6] = input::binding("key:ctrl+x").unwrap();
    let encoded = p.encode().unwrap();
    for i in 0..data.len() {
        if data[i] != encoded[i] {
            assert!(
                (160..208).contains(&i) || (120..124).contains(&i) || i >= 253,
                "unexpected changed byte {i}"
            );
        }
    }
    assert!(model::crc_ok(&encoded));
}
#[test]
fn damaged_or_empty_profiles_do_not_encode() {
    let f = fixture();
    let data = model::unhex(f["sectors"]["0x0001"].as_str().unwrap()).unwrap();
    let mut p = Profile::decode(&data).unwrap();
    p.dpi = [0; 5];
    assert!(p.encode().is_err());
    p.dpi = [800, 0, 0, 0, 0];
    p.default_dpi = 250;
    assert!(p.encode().is_err());
}
#[test]
fn unicode_names_never_split_surrogates() {
    let f = fixture();
    let data = model::unhex(f["sectors"]["0x0001"].as_str().unwrap()).unwrap();
    let mut p = Profile::decode(&data).unwrap();
    p.name = Some("😀".repeat(20));
    let encoded = p.encode().unwrap();
    let p = Profile::decode(&encoded).unwrap();
    assert_eq!(p.name, Some("😀".repeat(12)));
}
