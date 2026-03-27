use std::collections::{HashMap, HashSet};
use std::fs::File;
use std::io::Write;
use std::path::Path;

pub use crate::batch::config::{RERESOLVE_DATA_SIZE, THREAD_DATA_SIZE, VersionInfo};
pub use crate::batch::db::get_ver_name_table;

pub fn write_dependency_file_sorted(
    path_string: String,
    dependencies: &HashMap<String, HashSet<String>>,
) {
    let mut content: Vec<String> = Vec::new();
    let path = Path::new(path_string.as_str());
    let display = path.display();
    let mut file = match File::create(path) {
        Err(why) => panic!("couldn't create {}: {}", display, why),
        Ok(file) => file,
    };

    for (crate_name, versions) in dependencies {
        for version in versions {
            content.push(format!("{},{}\n", crate_name, version));
        }
    }

    content.sort();
    for line in content {
        if let Err(why) = file.write_all(line.as_bytes()) {
            panic!("couldn't write to {}: {}", display, why);
        }
    }
}
