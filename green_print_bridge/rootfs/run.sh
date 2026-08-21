#!/usr/bin/with-contenv bashio
set -euo pipefail
umask 077

mkdir -p /data /run/cups /tmp/cups /tmp/green-spool
chmod 0700 /data /tmp/cups /tmp/green-spool

exec python3 /opt/green/service.py
