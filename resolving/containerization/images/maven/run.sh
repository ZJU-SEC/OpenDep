#!/bin/bash

set -e

JAR_PATH="${MAVEN_RESOLVER_JAR:-/usr/local/lib/maven-resolver.jar}"
MAIN_CLASS="${MAVEN_RESOLVER_MAIN_CLASS:-cn.edu.zju.nirvana.adapter.MavenResolverAdapterMain}"

if [ ! -f "$JAR_PATH" ] && [ -f "target/maven-resolver.jar" ]; then
    JAR_PATH="target/maven-resolver.jar"
fi

export JAVA_OPTS="${JAVA_OPTS:--Xmx2g -Xms1g -XX:+UseG1GC}"

if [ ! -f "$JAR_PATH" ]; then
    echo "Missing built jar: $JAR_PATH" >&2
    exit 1
fi

if [ $# -ne 1 ]; then
    echo "Usage: $0 <groupId:artifactId:version>" >&2
    echo "Example: $0 org.apache.logging.log4j:log4j-core:2.23.1" >&2
    exit 1
fi

exec java $JAVA_OPTS -cp "$JAR_PATH" "$MAIN_CLASS" "$1"
