# Maven resolving Image

This directory contains the Java backend image for Maven dependency resolution.
The image build packages the Maven resolver jar and installs a small launcher script as the image entrypoint.
Inside the jar, the active Java entrypoint now lives under `cn.edu.zju.nirvana.maven.adapter`.

## Directory structure

Key files and directories:

- `resolving/containerization/images/maven/Dockerfile` — image definition
- `resolving/containerization/images/maven/pom.xml` — Maven project definition
- `resolving/containerization/images/maven/run.sh` — image entry launcher
- `resolving/containerization/images/maven/src/main/` — main Java source tree
- `resolving/containerization/images/maven/src/test/` — test source tree
- `resolving/containerization/images/maven/.dockerignore` — Docker build context exclusions
- `resolving/containerization/images/maven/.gitignore` — local build artifact exclusions

Current Java package layout:

- `cn.edu.zju.nirvana.maven.adapter`
  - `MavenResolverAdapterMain` — jar main class for direct image execution
  - `MavenSingleResolver` — Aether-backed graph resolver that emits backend JSON
- `cn.edu.zju.nirvana.maven.bootstrap`
  - `Booter` — local repository and remote repository session setup
  - `ManualRepositorySystemFactory` — Aether service locator wiring

## Build the image

Run from the repository root:

```bash
docker build -f resolving/containerization/images/maven/Dockerfile -t maven-resolver:latest .
```

## Run the image

There are two Docker-only ways to run the Maven backend from this subtree:

- Direct image run
  - entrypoint: `/usr/local/bin/maven-resolver`
  - input: one coordinate argument in `groupId:artifactId:version` form
  - output: backend graph JSON only
- Compose-backed service run
  - service: `resolver-maven`
  - default service entrypoint: `python3 resolving/containerization/runtime/maven_adapter.py`
  - if you want the raw Maven backend CLI from this submodule, override the entrypoint to `/usr/local/bin/maven-resolver`

The shared Maven cache is typically mounted to `/root/.m2`.

Example direct image run:

```bash
docker run --rm -v resolver-maven-m2-cache:/root/.m2 maven-resolver:latest org.apache.logging.log4j:log4j-core:2.23.1
```

Example compose-backed run against the same image and mounts:

```bash
docker compose -f resolving/containerization/docker-compose.yml run --rm \
  --entrypoint /usr/local/bin/maven-resolver \
  resolver-maven \
  org.apache.logging.log4j:log4j-core:2.23.1
```

## Notes

- The launcher expects one Maven coordinate in the form `groupId:artifactId:version`.
- The named volume `resolver-maven-m2-cache` is recommended for repeated runs.
- The built jar is installed at `/usr/local/lib/maven-resolver.jar`.
- The jar manifest main class is `cn.edu.zju.nirvana.maven.adapter.MavenResolverAdapterMain`.
- The Compose service `resolver-maven` defaults to the Python adapter layer; use `--entrypoint /usr/local/bin/maven-resolver` when you want the raw single-coordinate Maven backend CLI.
