#!/bin/sh
set -eu

if [ "$#" -eq 0 ]; then
  set -- apply
fi

case "$1" in
  apply|list|rollback|reapply|mark|unmark|develop|new)
    exec yoyo "$@"
    ;;
  python|python3|bash|sh)
    exec "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
