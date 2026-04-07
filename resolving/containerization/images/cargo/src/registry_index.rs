use anyhow::{anyhow, Context, Result};
use curl::easy::Easy;
use serde::Deserialize;
use std::collections::{BTreeSet, HashMap, HashSet};
use std::env;
use std::fs;
use std::path::PathBuf;
use std::time::Duration;

type FeatureMap = HashMap<String, Vec<String>>;

const DEFAULT_CRATES_IO_SPARSE_INDEX_BASE_URL: &str = "https://index.crates.io";
const DEFAULT_USER_AGENT: &str = "OpenDep-CargoResolver/1.0";

#[derive(Debug, Deserialize)]
struct RegistryDependency {
    name: String,
    #[serde(default)]
    optional: bool,
}

#[derive(Debug, Deserialize)]
struct RegistryIndexEntry {
    name: String,
    vers: String,
    #[serde(default)]
    features: Option<FeatureMap>,
    #[serde(default)]
    features2: Option<FeatureMap>,
    #[serde(default)]
    deps: Vec<RegistryDependency>,
}

impl RegistryIndexEntry {
    fn all_feature_names(&self) -> Vec<String> {
        collect_feature_names(
            [&self.features, &self.features2].into_iter().flatten(),
            self.deps
                .iter()
                .filter(|dependency| dependency.optional)
                .map(|dependency| dependency.name.as_str()),
        )
    }
}

pub fn collect_root_feature_names(crate_name: &str, version_num: &str) -> Result<Vec<String>> {
    match metadata_mode()?.as_str() {
        "indexed" => {
            let local_registry_dir = local_registry_dir()?;
            collect_root_feature_names_from_local_registry(&local_registry_dir, crate_name, version_num)
        }
        "online" => collect_root_feature_names_from_online_registry_index(crate_name, version_num),
        other => Err(anyhow!(
            "unsupported CARGO metadata mode `{other}`; expected `indexed` or `online`"
        )),
    }
}

fn collect_root_feature_names_from_local_registry(
    local_registry_dir: &PathBuf,
    crate_name: &str,
    version_num: &str,
) -> Result<Vec<String>> {
    let index_entry = load_registry_entry(local_registry_dir, crate_name, version_num)?;
    Ok(index_entry.all_feature_names())
}

fn collect_root_feature_names_from_online_registry_index(
    crate_name: &str,
    version_num: &str,
) -> Result<Vec<String>> {
    let entry_url = format!(
        "{}/{}",
        crates_io_sparse_index_base_url(),
        registry_entry_relative_path(crate_name).display()
    );
    let contents = fetch_text(&entry_url).with_context(|| {
        format!(
            "failed to fetch Cargo sparse index entry for `{crate_name}` version `{version_num}`"
        )
    })?;
    let index_entry = parse_registry_entry_contents(&contents, &entry_url, crate_name, version_num)?;
    Ok(index_entry.all_feature_names())
}

fn collect_feature_names<'a, I, J>(feature_maps: I, optional_dep_names: J) -> Vec<String>
where
    I: IntoIterator<Item = &'a FeatureMap>,
    J: IntoIterator<Item = &'a str>,
{
    let mut names = BTreeSet::new();
    let mut explicit_optional_deps = HashSet::new();

    for feature_map in feature_maps {
        for (feature_name, members) in feature_map {
            names.insert(feature_name.clone());
            for member in members {
                if let Some(dep_name) = member.strip_prefix("dep:") {
                    explicit_optional_deps.insert(dep_name.to_string());
                }
            }
        }
    }

    // Optional dependencies become implicit feature names unless a `dep:foo`
    // reference disables that shorthand in the package feature definitions.
    for dep_name in optional_dep_names {
        if !explicit_optional_deps.contains(dep_name) {
            names.insert(dep_name.to_string());
        }
    }

    names.into_iter().collect()
}

fn load_registry_entry(
    local_registry_dir: &PathBuf,
    crate_name: &str,
    version_num: &str,
) -> Result<RegistryIndexEntry> {
    load_registry_entry_from_index_root(&local_registry_dir.join("index"), crate_name, version_num)
}

fn load_registry_entry_from_index_root(
    index_root: &PathBuf,
    crate_name: &str,
    version_num: &str,
) -> Result<RegistryIndexEntry> {
    let entry_path = index_root.join(registry_entry_relative_path(crate_name));
    let contents = fs::read_to_string(&entry_path).with_context(|| {
        format!(
            "failed to read Cargo registry index entry for `{crate_name}` at {}",
            entry_path.display()
        )
    })?;

    parse_registry_entry_contents(&contents, &entry_path.display().to_string(), crate_name, version_num)
}

fn parse_registry_entry_contents(
    contents: &str,
    source: &str,
    crate_name: &str,
    version_num: &str,
) -> Result<RegistryIndexEntry> {
    for line in contents.lines() {
        let entry: RegistryIndexEntry = serde_json::from_str(line).with_context(|| {
            format!("failed to parse Cargo registry index JSON for `{crate_name}` at {source}")
        })?;
        if entry.vers == version_num && entry.name.eq_ignore_ascii_case(crate_name) {
            return Ok(entry);
        }
    }

    Err(anyhow!(
        "Cargo registry index entry for `{crate_name}` version `{version_num}` was not found in {source}"
    ))
}

fn fetch_text(url: &str) -> Result<String> {
    let mut easy = Easy::new();
    easy.url(url)?;
    easy.follow_location(true)?;
    easy.useragent(&crates_io_user_agent())?;
    easy.timeout(Duration::from_secs(30))?;
    easy.connect_timeout(Duration::from_secs(10))?;

    let mut body = Vec::new();
    {
        let mut transfer = easy.transfer();
        transfer.write_function(|data| {
            body.extend_from_slice(data);
            Ok(data.len())
        })?;
        transfer.perform()?;
    }

    let status_code = easy.response_code()?;
    if status_code != 200 {
        return Err(anyhow!(
            "crates.io sparse index returned status {status_code} for {url}"
        ));
    }

    String::from_utf8(body).with_context(|| format!("failed to decode Cargo sparse index response from {url}"))
}

fn crates_io_sparse_index_base_url() -> String {
    env::var("CARGO_CRATES_IO_SPARSE_INDEX_BASE_URL")
        .ok()
        .map(|value| value.trim().trim_end_matches('/').to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| DEFAULT_CRATES_IO_SPARSE_INDEX_BASE_URL.to_string())
}

fn crates_io_user_agent() -> String {
    env::var("CARGO_CRATES_IO_USER_AGENT")
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| DEFAULT_USER_AGENT.to_string())
}

fn metadata_mode() -> Result<String> {
    if let Ok(mode) = env::var("CARGO_METADATA_MODE") {
        let normalized = normalize_metadata_mode(&mode);
        if !normalized.is_empty() {
            return Ok(normalized);
        }
    }
    if let Ok(mode) = env::var("CARGO_REGISTRY_MODE") {
        let normalized = normalize_metadata_mode(&mode);
        if !normalized.is_empty() {
            return Ok(normalized);
        }
    }
    Ok(String::from("indexed"))
}

fn normalize_metadata_mode(mode: &str) -> String {
    match mode.trim().to_ascii_lowercase().as_str() {
        "local-registry" => String::from("indexed"),
        "crates.io" => String::from("online"),
        normalized => normalized.to_string(),
    }
}

fn local_registry_dir() -> Result<PathBuf> {
    if let Ok(path) = env::var("CARGO_LOCAL_REGISTRY_DIR") {
        return Ok(PathBuf::from(path));
    }
    if let Ok(root) = env::var("CARGO_SHARED_DATA_ROOT") {
        return Ok(PathBuf::from(root).join("local-registry"));
    }
    if let Ok(root) = env::var("CARGO_PREPROCESS_DATA_ROOT") {
        return Ok(PathBuf::from(root).join("local-registry"));
    }
    if let Ok(runtime_root) = env::var("CARGO_RUNTIME_ROOT") {
        return Ok(PathBuf::from(runtime_root).join("local-registry"));
    }
    Ok(env::current_dir()?.join("local-registry"))
}

fn registry_entry_relative_path(crate_name: &str) -> PathBuf {
    let normalized_name = crate_name.to_ascii_lowercase();
    match normalized_name.len() {
        0 => PathBuf::new(),
        1 => PathBuf::from("1").join(normalized_name),
        2 => PathBuf::from("2").join(normalized_name),
        3 => PathBuf::from("3")
            .join(&normalized_name[0..1])
            .join(normalized_name),
        _ => PathBuf::from(&normalized_name[0..2])
            .join(&normalized_name[2..4])
            .join(normalized_name),
    }
}

#[cfg(test)]
mod tests {
    use super::{
        collect_root_feature_names_from_local_registry,
        load_registry_entry_from_index_root,
        registry_entry_relative_path,
    };
    use std::fs;
    use std::path::{Path, PathBuf};
    use std::process;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn make_temp_dir(label: &str) -> PathBuf {
        let unique = format!(
            "opendep-cargo-registry-index-test-{}-{}-{}",
            label,
            process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("system time should be after UNIX_EPOCH")
                .as_nanos()
        );
        let path = std::env::temp_dir().join(unique);
        fs::create_dir_all(&path).expect("temp dir should be created");
        path
    }

    fn write_entry(registry_root: &Path, crate_name: &str, entry_json: &str) {
        let entry_path = registry_root
            .join("index")
            .join(registry_entry_relative_path(crate_name));
        if let Some(parent) = entry_path.parent() {
            fs::create_dir_all(parent).expect("entry parent should be created");
        }
        fs::write(&entry_path, entry_json).expect("entry JSON should be written");
    }

    #[test]
    fn maps_crate_names_to_registry_index_paths() {
        assert_eq!(registry_entry_relative_path("a"), PathBuf::from("1").join("a"));
        assert_eq!(registry_entry_relative_path("ab"), PathBuf::from("2").join("ab"));
        assert_eq!(
            registry_entry_relative_path("abc"),
            PathBuf::from("3").join("a").join("abc")
        );
        assert_eq!(
            registry_entry_relative_path("Tokio"),
            PathBuf::from("to").join("ki").join("tokio")
        );
    }

    #[test]
    fn merges_feature_maps_and_implicit_optional_dependency_features() {
        let registry_root = make_temp_dir("implicit-optional");
        write_entry(
            &registry_root,
            "anyhow",
            r#"{"name":"anyhow","vers":"1.0.56","features":{"default":["std"],"std":[]},"features2":null,"deps":[{"name":"backtrace","optional":true},{"name":"syn","optional":false}]}"#,
        );

        let features = collect_root_feature_names_from_local_registry(&registry_root, "anyhow", "1.0.56")
            .expect("features should load");

        assert_eq!(features, vec!["backtrace", "default", "std"]);
        fs::remove_dir_all(registry_root).expect("temp dir should be removed");
    }

    #[test]
    fn dep_syntax_disables_implicit_optional_dependency_feature() {
        let registry_root = make_temp_dir("dep-syntax");
        write_entry(
            &registry_root,
            "demo",
            r#"{"name":"demo","vers":"0.1.0","features":{"default":[]},"features2":{"codec":["dep:serde"]},"deps":[{"name":"serde","optional":true},{"name":"chrono","optional":true}]}"#,
        );

        let features = collect_root_feature_names_from_local_registry(&registry_root, "demo", "0.1.0")
            .expect("features should load");

        assert_eq!(features, vec!["chrono", "codec", "default"]);
        fs::remove_dir_all(registry_root).expect("temp dir should be removed");
    }

    #[test]
    fn preserves_dependency_alias_names_from_registry_index() {
        let index_root = make_temp_dir("renamed-optional");
        let entry_path = index_root.join(registry_entry_relative_path("rand"));
        if let Some(parent) = entry_path.parent() {
            fs::create_dir_all(parent).expect("entry parent should be created");
        }
        fs::write(
            &entry_path,
            r#"{"name":"rand","vers":"0.8.5","features":{"default":["std","std_rng"],"simd_support":["packed_simd"],"std":[]},"features2":null,"deps":[{"name":"packed_simd","optional":true},{"name":"rand_chacha","optional":true}]}"#,
        )
        .expect("entry JSON should be written");

        let entry = load_registry_entry_from_index_root(&index_root, "rand", "0.8.5")
            .expect("registry entry should load");

        assert_eq!(
            entry.all_feature_names(),
            vec!["default", "packed_simd", "rand_chacha", "simd_support", "std"]
        );
        fs::remove_dir_all(index_root).expect("temp dir should be removed");
    }
}
