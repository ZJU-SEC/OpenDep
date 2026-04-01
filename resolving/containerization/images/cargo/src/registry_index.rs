use anyhow::{anyhow, Context, Result};
use serde::Deserialize;
use std::collections::{BTreeSet, HashMap, HashSet};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

type FeatureMap = HashMap<String, Vec<String>>;

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
        let mut names = BTreeSet::new();
        let mut explicit_optional_deps = HashSet::new();

        for feature_map in [&self.features, &self.features2] {
            if let Some(feature_map) = feature_map {
                for (feature_name, members) in feature_map {
                    names.insert(feature_name.clone());
                    for member in members {
                        if let Some(dep_name) = member.strip_prefix("dep:") {
                            explicit_optional_deps.insert(dep_name.to_string());
                        }
                    }
                }
            }
        }

        // Optional dependencies become implicit feature names unless a `dep:foo`
        // reference disables that shorthand in the package feature definitions.
        for dep in &self.deps {
            if dep.optional && !explicit_optional_deps.contains(&dep.name) {
                names.insert(dep.name.clone());
            }
        }

        names.into_iter().collect()
    }
}

pub fn collect_root_feature_names(crate_name: &str, version_num: &str) -> Result<Vec<String>> {
    let local_registry_dir = local_registry_dir()?;
    collect_root_feature_names_from_dir(&local_registry_dir, crate_name, version_num)
}

fn collect_root_feature_names_from_dir(
    local_registry_dir: &Path,
    crate_name: &str,
    version_num: &str,
) -> Result<Vec<String>> {
    let index_entry = load_registry_entry(local_registry_dir, crate_name, version_num)?;
    Ok(index_entry.all_feature_names())
}

fn load_registry_entry(
    local_registry_dir: &Path,
    crate_name: &str,
    version_num: &str,
) -> Result<RegistryIndexEntry> {
    let entry_path = local_registry_dir
        .join("index")
        .join(registry_entry_relative_path(crate_name));
    let contents = fs::read_to_string(&entry_path).with_context(|| {
        format!(
            "failed to read Cargo registry index entry for `{crate_name}` at {}",
            entry_path.display()
        )
    })?;

    for line in contents.lines() {
        let entry: RegistryIndexEntry = serde_json::from_str(line).with_context(|| {
            format!(
                "failed to parse Cargo registry index JSON for `{crate_name}` at {}",
                entry_path.display()
            )
        })?;
        if entry.vers == version_num && entry.name.eq_ignore_ascii_case(crate_name) {
            return Ok(entry);
        }
    }

    Err(anyhow!(
        "Cargo registry index entry for `{crate_name}` version `{version_num}` was not found in {}",
        entry_path.display()
    ))
}

fn local_registry_dir() -> Result<PathBuf> {
    if let Ok(path) = env::var("CARGO_LOCAL_REGISTRY_DIR") {
        return Ok(PathBuf::from(path));
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
    use super::{collect_root_feature_names_from_dir, registry_entry_relative_path};
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

        let features =
            collect_root_feature_names_from_dir(&registry_root, "anyhow", "1.0.56").expect("features should load");

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

        let features =
            collect_root_feature_names_from_dir(&registry_root, "demo", "0.1.0").expect("features should load");

        assert_eq!(features, vec!["chrono", "codec", "default"]);
        fs::remove_dir_all(registry_root).expect("temp dir should be removed");
    }
}
