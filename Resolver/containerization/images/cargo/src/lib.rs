use std::collections::{HashSet, VecDeque};

use anyhow::Result;

pub mod batch;
pub mod graph;
pub mod model;
pub mod resolver;
pub mod util;

pub use graph::ResolvedGraph as Graph;
pub use model::{CargoEdge, CargoGraphResult, CargoJsonMap, CargoNode};

pub fn resolve_graph_of_version_once(name: &str, num: &str) -> Result<CargoGraphResult> {
    let resolve = resolver::resolve_with_all_features(name, num)?;
    let graph = Graph::build_deps(name, resolve);
    Ok(graph.to_result(name, Some(num)))
}

/// Resolve version's dependencies.
/// Is is recommended to be used for small mount of queries as it lacks of performance optimization.
pub fn resolve_deps_of_version_once(name: String, num: String) -> Result<String> {
    let resolve = resolver::resolve_with_all_features(&name, &num)?;

    let mut set = HashSet::new();
    let root = resolve.query(&name)?;
    let mut queue = VecDeque::new();
    let mut level = 1;
    queue.extend([Some(root), None]);

    while let Some(next) = queue.pop_front() {
        if let Some(pkg) = next {
            for (dep_pkg, _) in resolve.deps(pkg) {
                set.insert(((dep_pkg.name().to_string(), dep_pkg.version().to_string()), level));
                queue.push_back(Some(dep_pkg));
            }
        } else {
            level += 1;
            if !queue.is_empty() {
                queue.push_back(None);
            }
        }
    }

    let mut deps = String::new();
    for (version_to, level) in set {
        deps.push_str(&format!("{},{},{}\n", version_to.0, version_to.1, level));
    }

    Ok(deps)
}

/// Resolve version's dependencies. This time, we print raw dependency results with full info.
/// Is is recommended to be used for small mount of queries as it lacks of performance optimization.
pub fn resolve_deps_of_version_once_full(name: String, num: String) -> Result<String> {
    let result = resolve_graph_of_version_once(&name, &num)?;
    Ok(serde_json::to_string_pretty(&result)?)
}

pub fn format_virt_toml_file(name: &String, version_num: &String, features: &Vec<&str>) -> String {
    let owned_features: Vec<String> = features
        .iter()
        .map(|feature| (*feature).to_string())
        .collect();
    resolver::format_virt_toml_file(name, version_num, &owned_features)
}

pub fn test_registry(name: String, num: String) -> Result<String> {
    let resolve = resolver::resolve_with_all_features(&name, &num)?;
    let graph = Graph::build_deps(&name, resolve);
    Ok(graph.render_legacy())
}
