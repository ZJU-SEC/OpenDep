FROM cnspary/cargo-resolver-base:latest

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 \
        pkg-config \
        libssl-dev \
        ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENV CARGO_HOME=/cargo-home
ENV CARGO_RUNTIME_ROOT=/opt/opendep/cargo-runtime
RUN mkdir -p /cargo-home "$CARGO_RUNTIME_ROOT/.cargo"

COPY . .

RUN set -eu; \
    source_dir=/app/resolving/containerization/images/cargo; \
    if [ ! -f "$source_dir/Cargo.toml" ] || [ ! -f "$source_dir/src/bin/cargo_resolver.rs" ]; then \
        echo "cargo source directory not found at $source_dir" >&2; \
        exit 1; \
    fi; \
    config_source="$source_dir/.cargo/config.toml"; \
    if [ ! -f "$config_source" ]; then echo "cargo config not found: $config_source" >&2; exit 1; fi; \
    build_config_backup="$config_source.runtime"; \
    mv "$config_source" "$build_config_backup"; \
    mkdir -p "$CARGO_RUNTIME_ROOT/local-registry"; \
    cd "$source_dir"; \
    cargo build --release --bin cargo_resolver; \
    cp "$build_config_backup" "$CARGO_RUNTIME_ROOT/.cargo/config.toml"; \
    mv "$build_config_backup" "$config_source"; \
    install -m 755 target/release/cargo_resolver /usr/local/bin/cargo-resolver

WORKDIR /opt/opendep/cargo-runtime

ENTRYPOINT ["/usr/local/bin/cargo-resolver"]
