use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

pub type CargoJsonMap = Map<String, Value>;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CargoGraphResult {
    pub root: CargoNode,
    #[serde(default)]
    pub nodes: Vec<CargoNode>,
    #[serde(default)]
    pub edges: Vec<CargoEdge>,
    #[serde(default)]
    pub semantics: CargoJsonMap,
    #[serde(default)]
    pub metrics: CargoJsonMap,
}

impl CargoGraphResult {
    pub fn new(root: CargoNode) -> Self {
        Self {
            root,
            nodes: Vec::new(),
            edges: Vec::new(),
            semantics: CargoJsonMap::new(),
            metrics: CargoJsonMap::new(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CargoNode {
    pub id: String,
    pub ecosystem: String,
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub version: Option<String>,
    #[serde(default)]
    pub labels: CargoJsonMap,
    #[serde(default)]
    pub attributes: CargoJsonMap,
}

impl CargoNode {
    pub fn new(name: impl Into<String>, version: Option<String>) -> Self {
        let name = name.into();
        let id = match &version {
            Some(version) => format!("cargo:{}@{}", name, version),
            None => format!("cargo:{}", name),
        };
        Self {
            id,
            ecosystem: "cargo".to_string(),
            name,
            version,
            labels: CargoJsonMap::new(),
            attributes: CargoJsonMap::new(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CargoEdge {
    pub from: String,
    pub to: String,
    #[serde(rename = "type")]
    pub edge_type: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub constraint: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub depth: Option<u32>,
    #[serde(default)]
    pub attributes: CargoJsonMap,
}

impl CargoEdge {
    pub fn new(from: impl Into<String>, to: impl Into<String>, edge_type: impl Into<String>) -> Self {
        Self {
            from: from.into(),
            to: to.into(),
            edge_type: edge_type.into(),
            constraint: None,
            depth: None,
            attributes: CargoJsonMap::new(),
        }
    }
}
