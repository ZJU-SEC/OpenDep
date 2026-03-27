use cargo::core::registry::PackageRegistry;
use cargo::core::resolver::{CliFeatures, HasDevUnits, Resolve};
use cargo::core::{Shell, Workspace};
use cargo::ops;
use cargo::util::Config;

use std::env;
use std::fs::{self, File};
use std::io::Write;
use std::path::{Path, PathBuf};

use anyhow::Result;

pub fn resolve_with_all_features(name: &str, version_num: &str) -> Result<Resolve> {
    let current_dir = env::current_dir()?;
    let workspace_dir = workspace_dir(&current_dir);
    ensure_workspace_layout(&workspace_dir)?;
    let manifest_path = workspace_dir.join("Cargo.toml");
    let features = collect_enabled_features(name, version_num, &current_dir, &manifest_path)?;
    run_resolve(name, version_num, &features, &current_dir, &manifest_path)
}

pub fn format_virt_toml_file(name: &str, version_num: &str, features: &[String]) -> String {
    let mut file = String::from(
        r#"[package]
name = "dep"
version = "0.1.0"
edition = "2021"
[dependencies]"#,
    );
    file.push('\n');
    file.push_str(&format!(
        "{} = {}version = \"={}\", features = [",
        name, "{", version_num
    ));
    for feature in features {
        file.push_str(&format!("\"{}\",", feature));
    }
    file.push_str("]}");
    file
}

fn collect_enabled_features(
    name: &str,
    version_num: &str,
    current_dir: &Path,
    manifest_path: &Path,
) -> Result<Vec<String>> {
    let resolve = run_resolve(name, version_num, &[], current_dir, manifest_path)?;
    let mut features = Vec::new();

    if let Ok(resolved_pkg) = resolve.query(&format!("{}:{}", name, version_num)) {
        for feature in resolve.summary(resolved_pkg).features().keys() {
            features.push(feature.to_string());
        }
    }

    Ok(features)
}

fn ensure_workspace_layout(workspace_dir: &Path) -> Result<()> {
    fs::create_dir_all(workspace_dir.join("src"))?;
    let stub_main = workspace_dir.join("src").join("main.rs");
    if !stub_main.exists() {
        File::create(&stub_main)?.write_all(b"fn main() {}\n")?;
    }
    Ok(())
}

fn run_resolve(
    name: &str,
    version_num: &str,
    features: &[String],
    current_dir: &Path,
    manifest_path: &Path,
) -> Result<Resolve> {
    let file = format_virt_toml_file(name, version_num, features);
    File::create(manifest_path)?.write_all(file.as_bytes())?;

    let config = Config::new(
        Shell::new(),
        current_dir.to_path_buf(),
        workspace_dir(current_dir).into(),
    );
    let ws = Workspace::new(manifest_path, &config)?;
    let mut registry = PackageRegistry::new(ws.config())?;
    let resolve = ops::resolve_with_previous(
        &mut registry,
        &ws,
        &CliFeatures::new_all(true),
        HasDevUnits::No,
        None,
        None,
        &[],
        true,
    )?;

    Ok(resolve)
}

fn workspace_dir(current_dir: &Path) -> PathBuf {
    if let Ok(workdir) = env::var("CARGO_RESOLVER_WORKDIR") {
        return PathBuf::from(workdir);
    }
    env::temp_dir()
        .join("cargo-resolver-job-once")
        .join(sanitize_path_component(current_dir))
}

fn sanitize_path_component(path: &Path) -> String {
    path.display()
        .to_string()
        .replace(std::path::MAIN_SEPARATOR, "_")
        .replace(':', "_")
}
