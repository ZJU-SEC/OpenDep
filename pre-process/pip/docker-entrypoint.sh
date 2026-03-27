#!/bin/sh
set -eu

if [ "$#" -eq 0 ]; then
  set -- build
fi

case "$1" in
  build|build.py)
    shift
    exec python3 /workspace/pre-process/pip/build.py "$@"
    ;;
  load|load.py)
    shift
    exec python3 /workspace/pre-process/pip/load.py "$@"
    ;;
  extract|extract.py)
    shift
    exec python3 /workspace/pre-process/pip/extract.py "$@"
    ;;
  python|python3|bash|sh)
    exec "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
