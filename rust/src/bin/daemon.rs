use g502_hub::{ipc, service};
use serde_json::json;
fn main() {
    let args: Vec<_> = std::env::args().collect();
    let result = if args.iter().any(|a| a == "--status") {
        ipc::request("snapshot", json!({}))
            .map(|v| println!("{}", serde_json::to_string_pretty(&v).unwrap()))
    } else if args.iter().any(|a| a == "--stop") {
        ipc::request("stop", json!({})).map(|_| ())
    } else {
        service::run()
    };
    if let Err(e) = result {
        eprintln!("{e:#}");
        std::process::exit(1);
    }
}
