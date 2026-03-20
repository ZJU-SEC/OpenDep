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
RUN mkdir -p /cargo-home /app/.cargo

COPY . .

RUN set -eu; \
    if [ -f /app/Cargo.toml ] && [ -f /app/src/bin/cargo_resolver.rs ]; then source_dir=/app; \
    elif [ -f /app/Resolver/containerization/images/cargo/Cargo.toml ] && [ -f /app/Resolver/containerization/images/cargo/src/bin/cargo_resolver.rs ]; then source_dir=/app/Resolver/containerization/images/cargo; \
    else echo "cargo source directory not found" >&2; exit 1; fi; \
    config_source="$source_dir/.cargo/config.toml"; \
    if [ ! -f "$config_source" ]; then echo "cargo config not found: $config_source" >&2; exit 1; fi; \
    if [ "$config_source" != "/app/.cargo/config.toml" ]; then cp "$config_source" /app/.cargo/config.toml; fi; \
    rm -rf /app/crates.io-index; \
    git clone https://github.com/rust-lang/crates.io-index.git /app/crates.io-index; \
    cd "$source_dir"; \
    cargo build --release --bin cargo_resolver; \
    install -m 755 target/release/cargo_resolver /usr/local/bin/cargo-resolver

ENTRYPOINT ["/usr/local/bin/cargo-resolver"]
