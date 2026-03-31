FROM cnspary/cargo-resolver-base:latest

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 \
        git \
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
    if [ -f /app/Cargo.toml ] && [ -f /app/src/bin/cargo_resolver.rs ]; then source_dir=/app; \
    elif [ -f /app/resolving/containerization/images/cargo/Cargo.toml ] && [ -f /app/resolving/containerization/images/cargo/src/bin/cargo_resolver.rs ]; then source_dir=/app/resolving/containerization/images/cargo; \
    else echo "cargo source directory not found" >&2; exit 1; fi; \
    if [ -d /app/resolving/containerization/images/cargo/crates.io-index ]; then index_source=/app/resolving/containerization/images/cargo/crates.io-index; \
    elif [ -d /app/crates.io-index ]; then index_source=/app/crates.io-index; \
    else echo "crates.io-index snapshot not found in build context" >&2; exit 1; fi; \
    config_source="$source_dir/.cargo/config.toml"; \
    if [ ! -f "$config_source" ]; then echo "cargo config not found: $config_source" >&2; exit 1; fi; \
    build_config_backup="$config_source.runtime"; \
    mv "$config_source" "$build_config_backup"; \
    rm -rf "$CARGO_RUNTIME_ROOT/local-registry" "$CARGO_RUNTIME_ROOT/image-local-registry"; \
    mkdir -p "$CARGO_RUNTIME_ROOT/image-local-registry"; \
    cp -R "$index_source" "$CARGO_RUNTIME_ROOT/image-local-registry/index"; \
    rm -rf "$CARGO_RUNTIME_ROOT/image-local-registry/index/.git"; \
    ln -s "$CARGO_RUNTIME_ROOT/image-local-registry" "$CARGO_RUNTIME_ROOT/local-registry"; \
    cd "$source_dir"; \
    cargo build --release --bin cargo_resolver; \
    cp "$build_config_backup" "$CARGO_RUNTIME_ROOT/.cargo/config.toml"; \
    mv "$build_config_backup" "$config_source"; \
    install -m 755 target/release/cargo_resolver /usr/local/bin/cargo-resolver

ENTRYPOINT ["/usr/local/bin/cargo-resolver"]
