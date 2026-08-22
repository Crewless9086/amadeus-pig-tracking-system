#!/bin/sh
set -eu
umask 0077

stage=bootstrap_entry
reason=unexpected_bootstrap_exit
startup_failed() {
  rc=$?
  if [ "${rc}" -ne 0 ]; then
    echo "green_startup_failed stage=${stage} reason=${reason}" >&2
  fi
  exit "${rc}"
}
trap startup_failed EXIT

# Bounded privileged initialization: ownership and two fixed processes only.
# Queue configuration is immutable in the image; no runtime queue mutation exists.
stage=mount_validation
reason=data_mount_invalid
test -d /data
test -r /data/options.json
test -s /data/options.json
reason=ca_missing_or_empty
test -r /config/private-ca.crt
test -s /config/private-ca.crt
stage=runtime_directory
reason=data_runtime_prepare_failed
install -d -o greenprint -g greenprint -m 0700 /data/green-runtime
reason=spool_prepare_failed
install -d -o greenprint -g greenprint -m 0700 /tmp/green-spool
stage=options_population
reason=runtime_options_install_failed
install -o greenprint -g greenprint -m 0600 /data/options.json /data/green-runtime/options.json
stage=cups_directories
reason=cups_runtime_prepare_failed
install -d -o cupsd -g cupsd -m 0750 /run/cups /var/log/cups /var/cache/cups
reason=cups_spool_prepare_failed
install -d -o cupsd -g cupsd -m 0700 /var/spool/cups
stage=ca_install
reason=ca_install_failed
install -o root -g root -m 0644 /config/private-ca.crt /etc/cups/ssl/site.crt
stage=queue_initializer
reason=queue_initializer_failed
queue="$(PYTHONPATH=/opt/green /usr/bin/python3 /opt/green/init_queue.py /data/options.json /run/cups/printers.conf)"
stage=queue_ownership
reason=queue_owner_failed
chown cupsd:cupsd /run/cups/printers.conf
reason=queue_mode_failed
chmod 0600 /run/cups/printers.conf
stage=cups_start
reason=cups_process_start_failed
/usr/sbin/cupsd -f -c /etc/cups/cupsd.conf -s /etc/cups/cups-files.conf &
cupsd_pid=$!
cups_ready=false
attempt=0
while [ "${attempt}" -lt 15 ]; do
  if ! kill -0 "${cupsd_pid}" 2>/dev/null; then
    wait "${cupsd_pid}" || true
    stage=cups_readiness
    reason=cups_stopped_during_startup
    exit 1
  fi
  scheduler="$(/usr/bin/lpstat -r 2>/dev/null || true)"
  if [ "${scheduler}" = "scheduler is running" ] && /usr/bin/lpstat -v "${queue}" >/dev/null 2>&1; then
    cups_ready=true
    break
  fi
  attempt=$((attempt + 1))
  /bin/busybox sleep 1
done
if [ "${cups_ready}" != true ]; then
  stage=cups_readiness
  reason=cups_or_queue_not_ready
  exit 1
fi
stage=service_exec
reason=service_exec_failed
exec /sbin/su-exec greenprint:greenprint /usr/bin/python3 /opt/green/service.py
