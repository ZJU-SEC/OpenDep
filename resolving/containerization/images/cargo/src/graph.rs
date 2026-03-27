use cargo::core::resolver::Resolve;
use cargo::core::summary::FeatureValue;
use serde_json::{json, Value};
use std::collections::{HashMap, HashSet, VecDeque};
use std::fmt;

use crate::{CargoEdge, CargoGraphResult, CargoNode};

#[derive(Debug, Clone, Hash, Eq, PartialEq)]
struct Version {
    name: String,
    num: String,
}

impl Version {
    fn new(name: impl Into<String>, num: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            num: num.into(),
        }
    }

    fn id(&self) -> String {
        format!("cargo:{}@{}", self.name, self.num)
    }

    fn to_node(&self, scope: &str) -> CargoNode {
        let mut node = CargoNode::new(self.name.clone(), Some(self.num.clone()));
        node.labels
            .insert("scope".to_string(), Value::String(scope.to_string()));
        node
    }
}

impl fmt::Display for Version {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{} v{}", self.name, self.num)
    }
}

#[derive(Debug, Clone)]
struct Deps {
    from: Version,
    to: Vec<Version>,
}

impl Deps {
    fn new(name: impl Into<String>, num: impl Into<String>) -> Self {
        Self {
            from: Version::new(name, num),
            to: Vec::new(),
        }
    }

    fn push_dep(&mut self, name: impl Into<String>, num: impl Into<String>) {
        self.to.push(Version::new(name, num));
    }
}

#[derive(Debug, Default)]
pub struct ResolvedGraph {
    versions_deps: HashMap<Version, Vec<Version>>,
}

impl ResolvedGraph {
    pub fn new() -> Self {
        Self {
            versions_deps: HashMap::new(),
        }
    }

    fn push(&mut self, deps: Deps) {
        self.versions_deps.insert(deps.from, deps.to);
    }

    pub fn build_deps(_requested_name: &str, resolve: Resolve) -> Self {
        let mut graph = Self::new();

        for pkg in resolve.sort() {
            let mut deps = Deps::new(pkg.name().to_string(), pkg.version().to_string());
            let enabled_features = resolve.features(pkg);
            let mut enabled_dep = Vec::new();
            let summary = resolve.summary(pkg);
            let mut suspect_deps = HashSet::new();

            for (feature, feature_deps) in summary.features() {
                if !enabled_features.contains(feature) {
                    continue;
                }
                for feature_dep in feature_deps {
                    if let FeatureValue::Dep { dep_name } = feature_dep {
                        enabled_dep.push(dep_name);
                    }
                }
            }

            for (_, feature_deps) in summary.features() {
                for feature_dep in feature_deps {
                    if let FeatureValue::DepFeature {
                        dep_name,
                        dep_feature: _,
                        weak,
                    } = feature_dep
                    {
                        if *weak
                            && !enabled_features.contains(dep_name)
                            && !enabled_dep.contains(&dep_name)
                        {
                            suspect_deps.insert(dep_name);
                        }
                    }
                }
            }

            for (dep_pkg, _) in resolve.deps(pkg) {
                if suspect_deps.contains(&dep_pkg.name()) {
                    continue;
                }
                deps.push_dep(dep_pkg.name().to_string(), dep_pkg.version().to_string());
            }
            graph.push(deps);
        }

        loop {
            let mut packages = HashSet::new();
            let mut reachable_packages = HashSet::new();
            reachable_packages.insert(Version::new("dep", "0.1.0"));

            for package in graph.versions_deps.keys() {
                packages.insert(package.clone());
            }
            for deps in graph.versions_deps.values() {
                for dep in deps {
                    reachable_packages.insert(dep.clone());
                }
            }

            if packages.len() == reachable_packages.len() {
                break;
            }

            for package in &packages {
                if !reachable_packages.contains(package) {
                    graph.versions_deps.remove(package);
                }
            }
        }

        graph
    }

    pub fn render_legacy(&self) -> String {
        let mut lines = vec![String::from("graph: Graph {")];

        let mut entries: Vec<_> = self.versions_deps.iter().collect();
        entries.sort_by(|(left, _), (right, _)| left.to_string().cmp(&right.to_string()));
        for (from, to) in entries {
            lines.push(format!("  - {}", from));
            let mut deps = to.clone();
            deps.sort_by(|left, right| left.to_string().cmp(&right.to_string()));
            for dep in deps {
                lines.push(format!("    - {}", dep));
            }
        }

        lines.push(String::from("}"));
        lines.join("\n")
    }

    pub fn to_result(
        &self,
        requested_name: &str,
        requested_version: Option<&str>,
    ) -> CargoGraphResult {
        let virtual_root = Version::new("dep", "0.1.0");
        let root_version = self
            .versions_deps
            .get(&virtual_root)
            .and_then(|deps| {
                deps.iter()
                    .find(|dep| dep.name == requested_name)
                    .cloned()
                    .or_else(|| deps.first().cloned())
            })
            .unwrap_or_else(|| {
                Version::new(
                    requested_name.to_string(),
                    requested_version.unwrap_or_default().to_string(),
                )
            });

        let mut nodes = Vec::new();
        let mut edges = Vec::new();
        let mut seen = HashSet::new();
        let mut adjacency: HashMap<String, Vec<String>> = HashMap::new();
        let mut versions: Vec<_> = self.versions_deps.keys().cloned().collect();
        versions.sort_by(|left, right| left.to_string().cmp(&right.to_string()));

        for version in versions {
            if version == virtual_root {
                continue;
            }
            let id = version.id();
            if seen.insert(id) {
                let scope = if version == root_version { "root" } else { "runtime" };
                nodes.push(version.to_node(scope));
            }
        }

        let mut edge_keys = HashSet::new();
        for (from, tos) in &self.versions_deps {
            if *from == virtual_root {
                continue;
            }
            let from_id = from.id();
            for to in tos {
                if *to == virtual_root {
                    continue;
                }
                let to_id = to.id();
                adjacency
                    .entry(from_id.clone())
                    .or_default()
                    .push(to_id.clone());
                if edge_keys.insert((from_id.clone(), to_id.clone())) {
                    let edge_type = if *from == root_version {
                        "direct"
                    } else {
                        "transitive"
                    };
                    edges.push(CargoEdge::new(from_id.clone(), to_id, edge_type));
                }
            }
        }

        let root_id = root_version.id();
        let mut depths: HashMap<String, u32> = HashMap::new();
        depths.insert(root_id.clone(), 0);
        let mut queue = VecDeque::from([root_id]);
        while let Some(current) = queue.pop_front() {
            let current_depth = depths.get(&current).copied().unwrap_or(0);
            if let Some(children) = adjacency.get(&current) {
                for child in children {
                    if depths.contains_key(child) {
                        continue;
                    }
                    depths.insert(child.clone(), current_depth + 1);
                    queue.push_back(child.clone());
                }
            }
        }

        for edge in &mut edges {
            if let Some(depth) = depths.get(&edge.to) {
                edge.depth = Some(*depth);
            }
        }

        nodes.sort_by(|left, right| left.id.cmp(&right.id));
        edges.sort_by(|left, right| {
            (left.from.as_str(), left.to.as_str()).cmp(&(right.from.as_str(), right.to.as_str()))
        });

        let root = root_version.to_node("root");
        let mut result = CargoGraphResult::new(root);
        result.nodes = nodes;
        result.edges = edges;
        result
            .metrics
            .insert("node_count".to_string(), json!(result.nodes.len()));
        result
            .metrics
            .insert("edge_count".to_string(), json!(result.edges.len()));
        result
            .semantics
            .insert("requested_name".to_string(), json!(requested_name));
        if let Some(version) = requested_version {
            result
                .semantics
                .insert("requested_version".to_string(), json!(version));
        }
        result
            .semantics
            .insert("virtual_root".to_string(), json!(virtual_root.to_string()));
        result
    }
}
