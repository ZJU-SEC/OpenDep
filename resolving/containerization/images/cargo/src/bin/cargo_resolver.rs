use std::{env, process};

use anyhow::{bail, Context, Result};
use rust_deps::resolve_graph_of_version_once;

struct CliConfig {
    name: String,
    version: String,
    output_format: String,
    pretty: bool,
}

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
    let config = parse_args(env::args().skip(1).collect())?;
    let graph = resolve_graph_of_version_once(&config.name, &config.version)?;

    match config.output_format.as_str() {
        "graph" | "full" => {
            if config.pretty {
                Ok(serde_json::to_string_pretty(&graph)?)
            } else {
                Ok(serde_json::to_string(&graph)?)
            }
        }
        other => bail!("unsupported format `{other}`; expected `graph` or `full`"),
    }
}

fn parse_args(args: Vec<String>) -> Result<CliConfig> {
    let mut iter = args.into_iter();
    match iter.next().as_deref() {
        Some("resolve") => {}
        _ => bail!(usage()),
    }

    let mut output_format = String::from("full");
    let mut pretty = false;
    let mut positional = Vec::new();

    while let Some(arg) = iter.next() {
        if arg == "--pretty" {
            pretty = true;
            continue;
        }
        if arg == "--json" {
            continue;
        }
        if arg == "--format" {
            output_format = iter.next().context("`--format` requires a value")?;
            continue;
        }
        if let Some(value) = arg.strip_prefix("--format=") {
            output_format = value.to_string();
            continue;
        }
        if arg.starts_with("--") {
            bail!("unknown option `{arg}`\n\n{}", usage());
        }
        positional.push(arg);
    }

    if positional.len() != 2 {
        bail!(usage());
    }

    Ok(CliConfig {
        name: positional.remove(0),
        version: positional.remove(0),
        output_format,
        pretty,
    })
}

fn usage() -> &'static str {
    "Usage:\n  cargo_resolver resolve <name> <version> [--format graph|full] [--json] [--pretty]"
}
