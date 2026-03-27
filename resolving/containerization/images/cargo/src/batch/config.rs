use log::SetLoggerError;
use simplelog::{ColorChoice, CombinedLogger, Config, LevelFilter, TermLogger, TerminalMode, WriteLogger};
use std::fs::OpenOptions;

#[derive(Debug, Clone)]
pub struct VersionInfo {
    pub version_id: i32,
    pub crate_id: i32,
    pub name: String,
    pub num: String,
}

pub const DEFAULT_DB_URL: &str = "host=localhost dbname=crates user=postgres password=postgres";
pub const THREAD_DATA_SIZE: i64 = 50;
pub const RERESOLVE_DATA_SIZE: i64 = 20;

pub const DEFAULT_LOG_FILE: &str = "./rust_deps.log";
pub const COUNT_DEPS_LOG_FILE: &str = "./count_deps.log";
pub const COMPLETE_DEPS_LOG_FILE: &str = "./complete_deps.log";

#[derive(Debug, Clone, Copy)]
pub struct BatchTables {
    pub suffix: &'static str,
    pub include_parent_column: bool,
}

pub const DEFAULT_TABLES: BatchTables = BatchTables {
    suffix: "",
    include_parent_column: false,
};

pub const COMPLETE_DEPTH_TABLES: BatchTables = BatchTables {
    suffix: "_CompleteDepth",
    include_parent_column: true,
};

pub fn init_file_logger(path: &str) -> Result<(), SetLoggerError> {
    CombinedLogger::init(vec![
        TermLogger::new(
            LevelFilter::Warn,
            Config::default(),
            TerminalMode::Mixed,
            ColorChoice::Auto,
        ),
        WriteLogger::new(
            LevelFilter::Info,
            Config::default(),
            OpenOptions::new()
                .read(true)
                .write(true)
                .create(true)
                .append(true)
                .open(path)
                .unwrap(),
        ),
    ])
}
