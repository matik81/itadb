use itadb_population_store::{audit, build};
use std::path::Path;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 && args.len() != 4 {
        eprintln!("usage: build-store INPUT_DIRECTORY OUTPUT_DIRECTORY [audit]");
        std::process::exit(2);
    }
    let action = if args.len() == 4 && args[3] == "audit" {
        audit
    } else {
        build
    };
    if let Err(error) = action(Path::new(&args[1]), Path::new(&args[2])) {
        eprintln!("Build refused: {error}");
        std::process::exit(1);
    }
}
