# Maven Resolver Image

`resolving/containerization/images/maven/` packages the Java backend used by `resolver-maven`.

## What It Does

The Maven resolver image:

- packages the Maven resolver jar and its launcher script
- resolves one Maven coordinate at a time
- uses the shared `.m2` cache mounted at `/root/.m2`
- serves normalized `resolve`, `health`, and `capabilities` responses through the adapter-backed service

## Use Through the Resolver CLI

If you want the shared `.m2` cache warmed ahead of time, do that through [`pre-process/maven/README.md`](../../../../pre-process/maven/README.md).

Examples:

```bash
docker compose -f resolving/containerization/docker-compose.yml build resolver-maven
python3 main.py health --ecosystem maven
python3 main.py capabilities --ecosystem maven

python3 main.py resolve --ecosystem maven --name org.apache.logging.log4j:log4j-core --version 2.23.1 --format graph
```