#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(CDPATH='' cd -- "$SCRIPT_DIR/../.." && pwd)"
SNAPSHOT_DIR="$REPO_ROOT/resolving/containerization/images/cargo/crates.io-index"
STAGING_DIR="$REPO_ROOT/resolving/containerization/images/cargo/.crates.io-index.staging"
INDEX_URL="${CARGO_INDEX_URL:-https://github.com/rust-lang/crates.io-index.git}"

echo "Refreshing Cargo snapshot into: $SNAPSHOT_DIR"
echo "Source index: $INDEX_URL"

rm -rf "$STAGING_DIR"
mkdir -p "$(dirname "$STAGING_DIR")"

git clone --depth 1 "$INDEX_URL" "$STAGING_DIR"
rm -rf "$STAGING_DIR/.git"

rm -rf "$SNAPSHOT_DIR"
mv "$STAGING_DIR" "$SNAPSHOT_DIR"

echo "Cargo snapshot refresh complete."
