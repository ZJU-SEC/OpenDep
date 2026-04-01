#!/bin/sh
set -eu

if [ "$#" -eq 0 ]; then
  set -- --help
fi

case "$1" in
  build|build.py)
    shift
    exec python3 /workspace/pre-process/cargo/build.py "$@"
    ;;
  clone|update|prepare-local-registry|-h|--help)
    exec python3 /workspace/pre-process/cargo/build.py "$@"
    ;;
  python|python3|bash|sh)
    exec "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
