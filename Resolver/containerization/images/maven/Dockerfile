FROM cnspary/maven-resolver-base:latest

WORKDIR /app

RUN apt-get update && \
    apt-get install -y maven python3 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY . .

RUN set -eu; \
    if [ -f /app/pom.xml ] && [ -f /app/run.sh ]; then source_dir=/app; \
    elif [ -f /app/Resolver/containerization/images/maven/pom.xml ] && [ -f /app/Resolver/containerization/images/maven/run.sh ]; then source_dir=/app/Resolver/containerization/images/maven; \
    else echo "maven source directory not found" >&2; exit 1; fi; \
    mkdir -p /root/.m2; \
    mvn -q -DskipTests -f "$source_dir/pom.xml" clean package; \
    install -m 755 "$source_dir/run.sh" /usr/local/bin/maven-resolver; \
    install -m 644 "$source_dir/target/maven-resolver.jar" /usr/local/lib/maven-resolver.jar

ENTRYPOINT ["/usr/local/bin/maven-resolver"]
