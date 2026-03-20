use anyhow::{Context, Result};
use postgres::{Client, NoTls, Row};
use std::collections::{HashMap, HashSet};
use std::sync::{Arc, Mutex};

use crate::batch::config::{BatchTables, VersionInfo, DEFAULT_DB_URL};

pub type SharedClient = Arc<Mutex<Client>>;

pub fn connect_default() -> SharedClient {
    Arc::new(Mutex::new(
        Client::connect(DEFAULT_DB_URL, NoTls).unwrap(),
    ))
}

pub fn prebuild_db_table(conn: SharedClient, tables: BatchTables) {
    create_dep_version_table(Arc::clone(&conn), tables);
    conn.lock()
        .unwrap()
        .query(
            &format!(
                r#"CREATE TABLE IF NOT EXISTS public.dep_errors{}
                (
                    ver integer,
                    is_panic boolean,
                    error text COLLATE pg_catalog."default",
                    CONSTRAINT dep_errors{}_ver_is_panic_error_key UNIQUE (ver, is_panic, error)
                )"#,
                tables.suffix, tables.suffix
            ),
            &[],
        )
        .unwrap_or_default();
    ensure_versions_with_name_view(Arc::clone(&conn));
    conn.lock()
        .unwrap()
        .query(
            &format!(
                r#"CREATE TABLE IF NOT EXISTS public.deps_process_status{}
                (
                    version_id INT,
                    status VARCHAR
                )"#,
                tables.suffix
            ),
            &[],
        )
        .unwrap();

    let has_rows = conn
        .lock()
        .unwrap()
        .query(
            &format!("SELECT * FROM deps_process_status{} LIMIT 1", tables.suffix),
            &[],
        )
        .unwrap()
        .first()
        .is_some();

    if !has_rows {
        conn.lock()
            .unwrap()
            .query(
                &format!(
                    "
                WITH ver_dep AS
                        (SELECT DISTINCT version_id as ver FROM dependencies WHERE kind != 2)
                INSERT INTO public.deps_process_status{} 
                    SELECT ver, 'undone' FROM ver_dep
                    WHERE ver NOT IN (SELECT id FROM versions WHERE yanked = true)
                    AND ver NOT IN (SELECT DISTINCT ver FROM dep_errors{})
                    AND ver NOT IN (SELECT DISTINCT version_from FROM dep_version{})",
                    tables.suffix, tables.suffix, tables.suffix
                ),
                &[],
            )
            .unwrap();
    } else {
        let query = format!(
            r#"UPDATE deps_process_status{} SET status='undone' WHERE version_id IN (
                SELECT version_id FROM deps_process_status{} WHERE status='processing'
            )"#,
            tables.suffix, tables.suffix
        );
        conn.lock().unwrap().query(&query, &[]).unwrap();
    }
}

pub fn fetch_versions_by_status(
    conn: SharedClient,
    tables: BatchTables,
    status: &str,
    limit: i64,
) -> Vec<VersionInfo> {
    ensure_versions_with_name_view(Arc::clone(&conn));
    let query = format!(
        r#"SELECT id,crate_id,name,num FROM versions_with_name WHERE id in (
                SELECT version_id FROM deps_process_status{} WHERE status='{}' ORDER BY version_id asc LIMIT {}
                )"#,
        tables.suffix, status, limit
    );
    rows_to_versions(conn.lock().unwrap().query(&query, &[]).unwrap())
}

pub fn mark_versions_processing(
    conn: SharedClient,
    tables: BatchTables,
    status: &str,
    limit: i64,
) {
    let query = format!(
        r#"UPDATE deps_process_status{} SET status='processing' WHERE version_id IN (
                    SELECT version_id FROM deps_process_status{} WHERE status='{}' ORDER BY version_id asc LIMIT {}
                )"#,
        tables.suffix, tables.suffix, status, limit
    );
    conn.lock().unwrap().query(&query, &[]).unwrap();
}

pub fn fetch_versions_with_offset(conn: SharedClient, offset: i64, limit: i64) -> Vec<VersionInfo> {
    ensure_versions_with_name_view(Arc::clone(&conn));
    let query = format!(
        r#"SELECT id,crate_id,name,num FROM versions_with_name OFFSET {} LIMIT {}"#,
        offset, limit
    );
    rows_to_versions(conn.lock().unwrap().query(&query, &[]).unwrap())
}

pub fn update_process_status(
    conn: SharedClient,
    tables: BatchTables,
    version_id: i32,
    status: &str,
) {
    conn.lock()
        .unwrap()
        .query(
            &format!(
                "UPDATE deps_process_status{} SET status = '{}' WHERE version_id = '{}';",
                tables.suffix, status, version_id
            ),
            &[],
        )
        .expect("Update process status fails");
}

pub fn get_ver_name_table(conn: SharedClient) -> HashMap<(String, String), i32> {
    ensure_versions_with_name_view(Arc::clone(&conn));
    let rows = conn
        .lock()
        .unwrap()
        .query(r#"SELECT id, crate_id, num ,name FROM versions_with_name"#, &[])
        .unwrap();
    let mut ver_name_table: HashMap<(String, String), i32> = HashMap::new();
    for ver in rows {
        let name: String = ver.get(3);
        let num: String = ver.get(2);
        let version_id: i32 = ver.get(0);
        ver_name_table.entry((name, num)).or_insert(version_id);
    }
    ver_name_table
}

pub fn lookup_version_id(
    table: &HashMap<(String, String), i32>,
    name: &str,
    version: &str,
) -> Result<i32> {
    table
        .get(&(name.to_string(), version.to_string()))
        .copied()
        .with_context(|| format!("Can't get version_id for {} {}", name, version))
}

pub fn store_resolve_error(
    conn: SharedClient,
    tables: BatchTables,
    version: i32,
    is_panic: bool,
    message: String,
) {
    let message = message.replace('"', "\"").replace('\'', "''");
    let query = format!(
        "INSERT INTO dep_errors{}(ver, is_panic, error) VALUES ({}, {:?}, '{}');",
        tables.suffix, version, is_panic, message
    );
    conn.lock().unwrap().query(&query, &[]).unwrap_or_default();
    update_process_status(Arc::clone(&conn), tables, version, "fail");
}

pub fn insert_flat_dependencies(
    conn: SharedClient,
    tables: BatchTables,
    version_from: i32,
    deps: &HashSet<(i32, usize)>,
) {
    if deps.is_empty() {
        return;
    }

    let mut query = format!("INSERT INTO dep_version{} VALUES", tables.suffix);
    for (version_to, level) in deps {
        query.push_str(&format!("({}, {}, {}),", version_from, version_to, level));
    }
    query.pop();
    query.push(';');
    conn.lock().unwrap().query(&query, &[]).unwrap_or_default();
}

pub fn insert_complete_dependencies(
    conn: SharedClient,
    tables: BatchTables,
    version_from: i32,
    deps: &HashSet<(i32, i32, usize)>,
) {
    if deps.is_empty() {
        return;
    }

    let mut query = format!("INSERT INTO dep_version{} VALUES", tables.suffix);
    for (version_to, version_parent, level) in deps {
        query.push_str(&format!(
            "({}, {}, {}, {}),",
            version_from, version_to, version_parent, level
        ));
    }
    query.pop();
    query.push(';');
    conn.lock().unwrap().query(&query, &[]).unwrap_or_default();
}

fn create_dep_version_table(conn: SharedClient, tables: BatchTables) {
    let query = if tables.include_parent_column {
        format!(
            r#"CREATE TABLE IF NOT EXISTS dep_version{}(
                    version_from INT,
                    version_to INT,
                    version_parent INT,
                    dep_level INT
                    )"#,
            tables.suffix
        )
    } else {
        format!(
            r#"CREATE TABLE IF NOT EXISTS dep_version{}(
                    version_from INT,
                    version_to INT,
                    dep_level INT,
                    UNIQUE(version_from, version_to, dep_level))"#,
            tables.suffix
        )
    };

    conn.lock().unwrap().query(&query, &[]).unwrap_or_default();
}

fn ensure_versions_with_name_view(conn: SharedClient) {
    conn.lock()
        .unwrap()
        .query(
            r#"CREATE VIEW versions_with_name as (
        SELECT versions.*, crates.name FROM versions INNER JOIN crates ON versions.crate_id = crates.id
        )"#,
            &[],
        )
        .unwrap_or_default();
}

fn rows_to_versions(rows: Vec<Row>) -> Vec<VersionInfo> {
    rows.iter()
        .map(|row| VersionInfo {
            version_id: row.get(0),
            crate_id: row.get(1),
            name: row.get(2),
            num: row.get(3),
        })
        .collect()
}
