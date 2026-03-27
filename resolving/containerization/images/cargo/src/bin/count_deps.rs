use anyhow::Result;
use crossbeam::channel;
use log::{error, info, warn};
use std::panic::{self, catch_unwind};
use std::sync::{Arc, Mutex};
use std::thread;

use rust_deps::batch::config::{init_file_logger, COUNT_DEPS_LOG_FILE, THREAD_DATA_SIZE, VersionInfo};
use rust_deps::batch::db::{connect_default, fetch_versions_with_offset};
use rust_deps::resolver::resolve_with_all_features;

fn main() {
    init_file_logger(COUNT_DEPS_LOG_FILE).unwrap();
    count_all_deps(20, "undone");
}

/// Count all versions and dependencies.
/// Run dependency resolving in `workers` threads.
pub fn count_all_deps(workers: usize, _status: &str) {
    let conn = connect_default();
    let (tx, rx) = channel::bounded::<Vec<VersionInfo>>(workers);

    let mut handles = vec![];
    for worker_id in 0..workers {
        let rx = rx.clone();

        handles.push(thread::spawn(move || {
            let version_count = Arc::new(Mutex::new(0usize));
            let deps_count = Arc::new(Mutex::new(0usize));
            while let Ok(versions) = rx.recv() {
                for version in versions {
                    let panic_version = version.clone();
                    let old_hook = panic::take_hook();
                    panic::set_hook(Box::new(move |info| {
                        let err_message = format!("{:?}", info);
                        error!(
                            "Thread {}: Panic occurs, version - {}, info:{}",
                            worker_id, panic_version.version_id, err_message
                        );
                    }));

                    if catch_unwind({
                        let version = version.clone();
                        let version_count = Arc::clone(&version_count);
                        let deps_count = Arc::clone(&deps_count);
                        move || match get_dep_count(&version) {
                            Err(error) => {
                                warn!(
                                    "Resolve version {} fails, due to error: {}",
                                    version.version_id, error
                                );
                            }
                            Ok(count) => {
                                *deps_count.lock().unwrap() += count;
                                *version_count.lock().unwrap() += 1;
                                info!(
                                    "Thread {}: Version_count {}, Deps count {}",
                                    worker_id,
                                    version_count.lock().unwrap(),
                                    deps_count.lock().unwrap()
                                );
                            }
                        }
                    })
                    .is_err()
                    {
                        error!("Thread {}: Panic occurs, version - {}", worker_id, version.version_id);
                    }
                    panic::set_hook(old_hook);
                }
            }
        }));
    }

    let mut offset = 592000;
    loop {
        let versions = fetch_versions_with_offset(Arc::clone(&conn), offset, THREAD_DATA_SIZE);
        if versions.is_empty() {
            break;
        }
        offset += THREAD_DATA_SIZE;
        tx.send(versions).unwrap();
    }

    std::mem::drop(tx);
    for handle in handles {
        if handle.join().is_err() {
            error!("!!!Thread Crash!!!");
        }
    }

    info!(r#"\\\ !Resolving Done! ///"#);
}

fn get_dep_count(version_info: &VersionInfo) -> Result<usize> {
    let resolve = resolve_with_all_features(&version_info.name, &version_info.num)?;
    Ok(resolve.iter().map(|pkg| resolve.deps(pkg).count()).sum::<usize>() - 1)
}
