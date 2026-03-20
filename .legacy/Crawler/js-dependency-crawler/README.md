# NPM Dependency Crawler

This project is a C++-based tool that crawls JavaScript package dependencies from the NPM registry and stores the metadata in a CouchDB database. It concurrently fetches the dependency information for JS package and parses their `package.json` files.

## Features

- Crawls JS package dependencies from the [NPM registry](https://www.npmjs.com/).
- Parses `package.json` files for module information such as dependencies and versions.
- Stores module metadata in CounchDB for later retrieval and analysis.
- Utilizes concurrent goroutines to speed up the crawling process.

## Prerequisites

### 1.CouchDB Installation

You need a running instance of CouchDB to store the package metadata. If you don't have CouchDB installed, follow the [installation guide](https://docs.couchdb.org/en/stable/install/index.html).

### 2.Setup CouchDB

1. Start your CouchDB instance:
   - Open the configuration file for editing, `/opt/couchdb/etc/local.ini`:
    ```bash
    [admins]
    admin = yourpassword
    ```
   This creates an admin user with the username admin and your specified password.

2. To bind CouchDB to all network interfaces (optional):
    ```bash
    [chttpd]
    bind_address = 0.0.0.0
    ```

2. Starting CouchDB

   ```bash
   sudo systemctl start couchdb
   ```

4. Accessing CouchDB
   CouchDB runs on port 5984 by default. You can access the CouchDB Web interface (Fauxton) by opening a browser and navigating to:
    ```
    http://127.0.0.1:5984/_utils/
    ```
   Log in with the admin credentials you set during configuration. You should see a response similar to:
    ```
    {
    "couchdb": "Welcome",
    "version": "3.2.1",
    "features": [],
    "vendor": {
        "name": "The Apache Software Foundation"
    }
    }

    ```

## Project Setup

1. Build the crawler
   ```bash
   bash docker.build.sh
   ```

2. Run the crawler
   ```bash
   bash docker_sync_official.sh
   ```

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
