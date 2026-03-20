# Pip Dependency Crawler

This project is a Python-based tool that crawls pypi package dependencies from the PyPI and stores the metadata in a postgresql database. It concurrently fetches the dependency information for python package and parses their content files, like `wheel`, `zip`.

## Features

- Crawls python package content from the [PyPI](https://pypi.org/).
- decompress package content files for meta information such as dependencies and versions.
- Stores artifact metadata in postgresql for later retrieval and analysis.
- Utilizes concurrent goroutines to speed up the crawling process.

## Prerequisites

### 1. Dependency Installation and Local Package Mirror Setup

Ensure you have [Python3](https://www.python.org/downloads/) installed. Then install [Pip](https://pip.pypa.io/en/stable/installation/). You can verify your installation with the following command:
```bash
python3 --version
pip --version
```

Install project dependencies
```bash
pip install -r requirements.txt
```

Following the instruction [Bandersnatch](https://bandersnatch.readthedocs.io/en/latest/) to mirror all PyPI package content to your loacl disk.

### 2. Postgresql

You need a running instance of postgresql to store the module metadata. If you don't have postgresql installed, follow the [installation guide](https://www.postgresql.org/docs/current/tutorial-install.html).

## Setup Postgresql

1. Start your Postgresql instance:
   - If you have Postgresql installed locally, log in to the PostgreSQL shell using the following command:
     ```bash
     sudo -u postgres psql
     ```
2. Create a new user. You can using the following commands in the Postgresql shell:
    ```
    CREATE USER yourusername WITH PASSWORD 'yourpassword';
    ```

3. Create a new database called `PipMetadata`. You can create the database using the following commands in the Postgresql shell:

   ```bash
   CREATE DATABASE PipMetadata;
   ALTER DATABASE PipMetadata OWNER TO yourusername;
   ```

4. Update the Postgresql connection URI in the code if necessary. The default URI points to a local instance at `localhost:54321/PipMetadata`. If you're using a remote instance, modify the following line in the `mybatis.xml`:

   ```python
   database = PooledPostgresqlDatabase(
      'PipMetadata', 
      max_connections=8, 
      stale_timeout=300, 
      host='127.0.0.1', 
      port=54321, 
      user='YOUR-USERNAME', 
      password='YOUR-PASSWORD'
   )
   ```

   Replace `"jdbc:postgresql://localhost:5432/MavenEcoSystem"` with your remote Postgresql URI.

## Project Setup and Running

1. Set up Postgresql, as described in the "Setup Postgresql" section.

2. When the mirroring is complete, you can using `main.py` to extract dependenc information and store it to database.
   ```bash
   python main.py PATH/TO/YOUR/LOCAL/PACKAGE
   ```

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

Feel free to adjust the content based on the specifics of your project and deployment environment.