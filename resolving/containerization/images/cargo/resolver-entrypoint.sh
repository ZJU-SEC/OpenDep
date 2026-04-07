#!/bin/sh
set -eu

metadata_mode="${CARGO_METADATA_MODE:-${CARGO_REGISTRY_MODE:-indexed}}"
case "$(printf '%s' "$metadata_mode" | tr '[:upper:]' '[:lower:]')" in
  indexed|local-registry)
    normalized_mode="indexed"
    ;;
  online|crates.io)
    normalized_mode="online"
    ;;
  *)
    echo "unsupported CARGO metadata mode: $metadata_mode" >&2
    exit 2
    ;;
esac

runtime_root="${CARGO_RUNTIME_ROOT:-/opt/opendep/cargo-runtime}"
config_dir="$runtime_root/.cargo"
template_path="$config_dir/config.$normalized_mode.toml"
active_path="$config_dir/config.toml"
shared_root="${CARGO_SHARED_DATA_ROOT:-${CARGO_PREPROCESS_DATA_ROOT:-/cargo-data}}"
cargo_home="${CARGO_HOME:-$shared_root/cargo-home}"

if [ ! -f "$template_path" ]; then
  echo "missing Cargo runtime config template: $template_path" >&2
  exit 2
fi

mkdir -p "$config_dir"
mkdir -p "$cargo_home"
cp "$template_path" "$active_path"

export CARGO_METADATA_MODE="$normalized_mode"
export CARGO_SHARED_DATA_ROOT="$shared_root"
export CARGO_HOME="$cargo_home"
export CARGO_LOCAL_REGISTRY_DIR="${CARGO_LOCAL_REGISTRY_DIR:-$shared_root/local-registry}"

exec /usr/local/bin/cargo-resolver "$@"
