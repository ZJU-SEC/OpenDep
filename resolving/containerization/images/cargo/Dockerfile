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

ENV CARGO_SHARED_DATA_ROOT=/cargo-data
ENV CARGO_HOME=/cargo-data/cargo-home
ENV CARGO_RUNTIME_ROOT=/opt/opendep/cargo-runtime
RUN mkdir -p "$CARGO_HOME" "$CARGO_RUNTIME_ROOT/.cargo"

COPY . .

RUN set -eu; \
    source_dir=/app/resolving/containerization/images/cargo; \
    if [ ! -f "$source_dir/Cargo.toml" ] || [ ! -f "$source_dir/src/bin/cargo_resolver.rs" ]; then \
        echo "cargo source directory not found at $source_dir" >&2; \
        exit 1; \
    fi; \
    runtime_config_dir="$source_dir/runtime-config"; \
    if [ ! -f "$runtime_config_dir/config.indexed.toml" ] || [ ! -f "$runtime_config_dir/config.online.toml" ]; then \
        echo "cargo runtime config templates not found at $runtime_config_dir" >&2; \
        exit 1; \
    fi; \
    entrypoint_source="$source_dir/resolver-entrypoint.sh"; \
    if [ ! -f "$entrypoint_source" ]; then echo "cargo runtime entrypoint not found: $entrypoint_source" >&2; exit 1; fi; \
    mkdir -p "$CARGO_RUNTIME_ROOT/local-registry"; \
    cd "$source_dir"; \
    cargo build --release --bin cargo_resolver; \
    install -m 644 "$runtime_config_dir/config.indexed.toml" "$CARGO_RUNTIME_ROOT/.cargo/config.indexed.toml"; \
    install -m 644 "$runtime_config_dir/config.online.toml" "$CARGO_RUNTIME_ROOT/.cargo/config.online.toml"; \
    install -m 755 "$entrypoint_source" /usr/local/bin/cargo-resolver-runtime; \
    install -m 755 target/release/cargo_resolver /usr/local/bin/cargo-resolver

WORKDIR /opt/opendep/cargo-runtime

ENTRYPOINT ["/usr/local/bin/cargo-resolver-runtime"]
