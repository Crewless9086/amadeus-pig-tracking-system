#!/bin/sh
set -eu
umask 0077

fail_bootstrap() {
  marker="green_startup_failed stage=bootstrap_exec reason=$1"
  printf '%s\n' "${marker}" > /run/cups/green-startup-failure 2>/dev/null || true
  printf '%s\n' "${marker}" >&2
  exit 78
}

if [ ! -f /init-green.sh ] || [ ! -r /init-green.sh ]; then
  fail_bootstrap init_script_unreadable
fi
if /bin/sh /init-green.sh; then
  exit 0
else
  status=$?
fi
if [ "${status}" -eq 78 ] && [ -s /run/cups/green-startup-failure ]; then
  exit 78
fi
fail_bootstrap init_script_failed
