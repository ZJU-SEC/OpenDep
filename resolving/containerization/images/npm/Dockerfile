FROM cnspary/npm-resolver-base:latest

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        cmake \
        libcurl4-openssl-dev \
        python3 \
        python3-psycopg2 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

RUN set -eu; \
    if [ -f /app/CMakeLists.txt ]; then source_dir=/app; \
    elif [ -f /app/resolving/containerization/images/npm/CMakeLists.txt ]; then source_dir=/app/resolving/containerization/images/npm; \
    else echo "npm CMakeLists.txt not found" >&2; exit 1; fi; \
    cmake -S "$source_dir" -B "$source_dir/build/release" -D CMAKE_BUILD_TYPE=Release; \
    cmake --build "$source_dir/build/release" -j"$(nproc)"; \
    install -m 755 "$source_dir/bin/npm-resolver" /usr/local/bin/npm-resolver; \
    find "$source_dir/build/release" \( -type f -o -type l \) -name '*.so*' -exec cp -a {} /usr/local/lib/ \;; \
    ldconfig

ENTRYPOINT ["/usr/local/bin/npm-resolver"]
