# Maven Dependency Crawler

This project is a Java-based tool that crawls maven artifacts dependencies from the maven central repoistory and stores the metadata in a postgresql database. It concurrently fetches the dependency information for maven artifacts and parses their `pom.xml` files.

## Features

- Crawls maven artifact dependencies from the [Maven repository](https://repo1.maven.org/maven2/).
- Parses `pom.xml` files for artifact information such as dependencies and versions.
- Stores artifact metadata in postgresql for later retrieval and analysis.
- Utilizes concurrent goroutines to speed up the crawling process.

## Prerequisites

### 1. Java Installation

Ensure you have [Java](https://www.java.com/en/) installed (version 11 or later). You can verify your installation with the following command:

```bash
java --version
```

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

3. Create a new database called `MavenEcoSystem`. You can create the database using the following commands in the Postgresql shell:

   ```bash
   CREATE DATABASE MavenEcoSystem;
   ALTER DATABASE MavenEcoSystem OWNER TO yourusername;
   ```

4. Update the Postgresql connection URI in the code if necessary. The default URI points to a local instance at `jdbc:postgresql://localhost:5432/MavenEcoSystem`. If you're using a remote instance, modify the following line in the `mybatis.xml`:

   ```xml
    <environments default="prod">
        <environment id="prod">
            <transactionManager type="JDBC"/>
            <dataSource type="POOLED">
                <property name="driver" value="org.postgresql.Driver"/>
                <property name="url" value="jdbc:postgresql://localhost:5432/MavenEcoSystem"/>
                <property name="username" value="USERNAME"/>
                <property name="password" value="PASSWORD"/>
                <property name="poolMaximumActiveConnections" value="60"/>
            </dataSource>
        </environment>
    </environments>
   ```

   Replace `"jdbc:postgresql://localhost:5432/MavenEcoSystem"` with your remote Postgresql URI.

## Project Setup

1. Set up Postgresql, as described in the "Setup Postgresql" section.

2. Build project:

   ```bash
   bash build.sh
   ```

## Running the Project

1. Run the java program:

   ```bash
   java -jar build/MavenEcoSystem.jar --indexer
   java -jar build/MavenEcoSystem.jar --crawl
   ```

   The crawler will fetch artifact data and store the results in postgresql.

2. You can monitor the results in artifact data by querying the `ArtifactMeta` table.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

Feel free to adjust the content based on the specifics of your project and deployment environment.