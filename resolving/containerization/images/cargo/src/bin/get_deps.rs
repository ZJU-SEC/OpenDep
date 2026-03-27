use std::{env, process};

use anyhow::{bail, Result};
use rust_deps::{resolve_deps_of_version_once, resolve_graph_of_version_once, test_registry};

fn main() {
    match run() {
        Ok(output) => println!("{output}"),
        Err(error) => {
            eprintln!("{error}");
            process::exit(1);
        }
    }
}

fn run() -> Result<String> {
    let args: Vec<String> = env::args().skip(1).collect();
    match args.as_slice() {
        [name, version] => resolve_deps_of_version_once(name.clone(), version.clone()),
        [mode, name, version] if mode == "full" => {
            let graph = resolve_graph_of_version_once(name, version)?;
            Ok(serde_json::to_string_pretty(&graph)?)
        }
        [mode, name, version] if mode == "release" => test_registry(name.clone(), version.clone()),
        _ => bail!(usage()),
    }
}

fn usage() -> &'static str {
    "Compatibility usage:\n  get_deps <name> <version>\n  get_deps full <name> <version>\n  get_deps release <name> <version>"
}
