use anyhow::Result;
use crossbeam::channel;
use log::{error, info, warn};
use std::collections::{HashMap, HashSet, VecDeque};
use std::panic::{self, catch_unwind};
use std::sync::Arc;
use std::thread;

use crate::batch::config::{BatchTables, VersionInfo, DEFAULT_TABLES, THREAD_DATA_SIZE};
use crate::batch::db::{
    connect_default, fetch_versions_by_status, get_ver_name_table, insert_flat_dependencies,
    lookup_version_id, mark_versions_processing, prebuild_db_table, store_resolve_error,
    update_process_status, SharedClient,
};
use crate::resolver::resolve_with_all_features;

pub fn run_deps(workers: usize, status: &str) {
    validate_status(status);

    let tables = DEFAULT_TABLES;
    let conn = connect_default();
    prebuild_db_table(Arc::clone(&conn), tables);
    let ver_name_table = Arc::new(get_ver_name_table(Arc::clone(&conn)));

    let (tx, rx) = channel::bounded::<Vec<VersionInfo>>(workers);
    let mut handles = vec![];
    for worker_id in 0..workers {
        let conn = Arc::clone(&conn);
        let rx = rx.clone();
        let ver_name_table = Arc::clone(&ver_name_table);

        handles.push(thread::spawn(move || {
            while let Ok(versions) = rx.recv() {
                for version in versions {
                    let panic_version = version.clone();
                    let old_hook = panic::take_hook();
                    panic::set_hook({
                        let conn_copy = Arc::clone(&conn);
                        Box::new(move |info| {
                            let err_message = format!("{:?}", info);
                            error!(
                                "Thread {}: Panic occurs, version - {}, info:{}",
                                worker_id, panic_version.version_id, err_message
                            );
                            store_resolve_error(
                                Arc::clone(&conn_copy),
                                tables,
                                panic_version.version_id,
                                true,
                                err_message,
                            );
                        })
                    });

                    if catch_unwind({
                        let conn = Arc::clone(&conn);
                        let ver_name_table = Arc::clone(&ver_name_table);
                        let version = version.clone();
                        move || {
                            if let Err(error) = resolve(worker_id as u32, Arc::clone(&conn), &version, Arc::clone(&ver_name_table), tables) {
                                warn!(
                                    "Resolve version {} fails, due to error: {}",
                                    version.version_id, error
                                );
                                store_resolve_error(
                                    Arc::clone(&conn),
                                    tables,
                                    version.version_id,
                                    false,
                                    format!("{:?}", error),
                                );
                            } else {
                                info!("Thread {}: Done version - {}", worker_id, version.version_id);
                            }
                        }
                    })
                    .is_err()
                    {
                        error!("Thread {}: Panic occurs, version - {}", worker_id, version.version_id);
                        store_resolve_error(
                            Arc::clone(&conn),
                            tables,
                            version.version_id,
                            true,
                            String::new(),
                        );
                    }
                    panic::set_hook(old_hook);
                }
            }
        }));
    }

    loop {
        let versions = fetch_versions_by_status(Arc::clone(&conn), tables, status, THREAD_DATA_SIZE);
        if versions.is_empty() {
            break;
        }
        mark_versions_processing(Arc::clone(&conn), tables, status, THREAD_DATA_SIZE);
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

fn validate_status(status: &str) {
    if status == "processing" {
        panic!(
            "If you specify undone, it will automatically process crates whose status is 'processing'"
        )
    }
    if status != "undone" && status != "fail" {
        panic!("The status can only be undone/fail")
    }
}

fn resolve(
    thread_id: u32,
    conn: SharedClient,
    version_info: &VersionInfo,
    ver_name_table: Arc<HashMap<(String, String), i32>>,
    tables: BatchTables,
) -> Result<()> {
    let version_id = version_info.version_id;
    let result = resolve_store_deps_of_version(thread_id, Arc::clone(&conn), version_info, ver_name_table, tables);
    let status = if result.is_ok() { "done" } else { "fail" };
    update_process_status(Arc::clone(&conn), tables, version_id, status);
    result
}

fn resolve_store_deps_of_version(
    _thread_id: u32,
    conn: SharedClient,
    version_info: &VersionInfo,
    ver_name_table: Arc<HashMap<(String, String), i32>>,
    tables: BatchTables,
) -> Result<()> {
    let resolve = resolve_with_all_features(&version_info.name, &version_info.num)?;

    let mut map = HashMap::new();
    let mut set = HashSet::new();
    for pkg in resolve.iter() {
        map.insert(
            (pkg.name().to_string(), pkg.version().to_string()),
            lookup_version_id(ver_name_table.as_ref(), &pkg.name().to_string(), &pkg.version().to_string())?,
        );
    }

    let root = resolve
        .query(&version_info.name)
        .or_else(|_| resolve.query(&format!("{}:{}", version_info.name, version_info.num)))?;
    let mut queue = VecDeque::new();
    let mut level = 1usize;
    queue.extend([Some(root), None]);

    while let Some(next) = queue.pop_front() {
        if let Some(pkg) = next {
            for (dep_pkg, _) in resolve.deps(pkg) {
                set.insert((
                    map[&(dep_pkg.name().to_string(), dep_pkg.version().to_string())],
                    level,
                ));
                queue.push_back(Some(dep_pkg));
            }
        } else {
            level += 1;
            if !queue.is_empty() {
                queue.push_back(None)
            }
        }
    }

    insert_flat_dependencies(conn, tables, version_info.version_id, &set);
    Ok(())
}
