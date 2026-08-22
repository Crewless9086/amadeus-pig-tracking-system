#!/bin/sh
set -eu
umask 0077

if /init-green.sh; then
  exit 0
else
  rc=$?
fi
if [ "${rc}" -eq 126 ] || [ "${rc}" -eq 127 ]; then
  echo "green_startup_failed stage=s6_exec reason=bootstrap_exec_failed" >&2
fi
exit "${rc}"
