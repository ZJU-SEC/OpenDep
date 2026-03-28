#!/bin/sh
set -eu

if [ "$#" -eq 0 ]; then
  exec python3 /workspace/pre-process/maven/build.py --help
fi

case "$1" in
  build|build.py)
    shift
    exec python3 /workspace/pre-process/maven/build.py "$@"
    ;;
  warm|index-all)
    exec python3 /workspace/pre-process/maven/build.py "$@"
    ;;
  python|python3|sh)
    exec "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
