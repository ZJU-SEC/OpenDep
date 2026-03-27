# Maven resolving Image

This directory contains the Java backend image for Maven dependency resolution.
The image build packages the Maven resolver jar and installs a small launcher script as the image entrypoint.

## Directory structure

Key files and directories:

- `resolving/containerization/images/maven/Dockerfile` — image definition
- `resolving/containerization/images/maven/pom.xml` — Maven project definition
- `resolving/containerization/images/maven/run.sh` — image entry launcher
- `resolving/containerization/images/maven/src/main/` — main Java source tree
- `resolving/containerization/images/maven/src/test/` — test source tree
- `resolving/containerization/images/maven/.dockerignore` — Docker build context exclusions
- `resolving/containerization/images/maven/.gitignore` — local build artifact exclusions

## Build the image

Run from the repository root:

```bash
docker build -f resolving/containerization/images/maven/Dockerfile -t maven-resolver:latest .
```

## Run the image

The image entrypoint is `/usr/local/bin/maven-resolver`.
The shared Maven cache is typically mounted to `/root/.m2`.

Example native run:

```bash
docker run --rm -v resolver-maven-m2-cache:/root/.m2 maven-resolver:latest org.apache.logging.log4j:log4j-core:2.23.1
```

## Notes

- The launcher expects one Maven coordinate in the form `groupId:artifactId:version`.
- The named volume `resolver-maven-m2-cache` is recommended for repeated runs.
- The built jar is installed at `/usr/local/lib/maven-resolver.jar`.
