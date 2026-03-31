#!/bin/sh
set -eu

if [ "$#" -eq 0 ]; then
  set -- build
fi

case "$1" in
  build|build.py)
    shift
    exec python3 /workspace/pre-process/npm/build.py "$@"
    ;;
  sync|sync.py)
    shift
    exec python3 /workspace/pre-process/npm/sync.py "$@"
    ;;
  python|python3|bash|sh)
    exec "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
