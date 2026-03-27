use rust_deps::batch::config::{init_file_logger, DEFAULT_LOG_FILE};
use rust_deps::batch::runner::run_deps;

fn main() {
    init_file_logger(DEFAULT_LOG_FILE).unwrap();
    run_deps(20, "undone");
}
