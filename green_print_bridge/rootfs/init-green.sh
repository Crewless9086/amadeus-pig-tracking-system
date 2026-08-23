#!/bin/sh
set -eu
umask 0077

fail_startup() {
  marker="green_startup_failed stage=$1 reason=$2"
  printf '%s\n' "${marker}" > /run/cups/green-startup-failure 2>/dev/null || true
  printf '%s\n' "${marker}" >&2
  exit 78
}
step() {
  step_stage=$1
  step_reason=$2
  shift 2
  "$@" 2>/dev/null || fail_startup "${step_stage}" "${step_reason}"
}
fail_initializer() {
  child_marker=""
  child_lines=""
  child_bytes=""
  if [ -s /run/cups/queue-initializer-error ]; then
    child_lines="$(/bin/busybox wc -l < /run/cups/queue-initializer-error 2>/dev/null)" || child_lines=""
    child_bytes="$(/bin/busybox wc -c < /run/cups/queue-initializer-error 2>/dev/null)" || child_bytes=""
    if [ "${child_lines}" = "1" ]; then
      child_marker="$(/bin/busybox head -n 1 /run/cups/queue-initializer-error 2>/dev/null)" || child_marker=""
      [ "${child_bytes}" = "$(( ${#child_marker} + 1 ))" ] || child_marker=""
    fi
  fi
  /bin/busybox rm -f /run/cups/queue-initializer-error 2>/dev/null || true
  case "${child_marker}" in
    "green_startup_failed stage=configuration reason=options_invalid"|\
    "green_startup_failed stage=configuration reason=queue_invalid"|\
    "green_startup_failed stage=configuration reason=printer_pin_invalid"|\
    "green_startup_failed stage=configuration reason=printer_hostname_invalid"|\
    "green_startup_failed stage=configuration reason=private_ipps_endpoint_invalid"|\
    "green_startup_failed stage=printer_tls reason=identity_or_connection_failed"|\
    "green_startup_failed stage=printer_binding reason=hosts_read_failed"|\
    "green_startup_failed stage=printer_binding reason=hosts_binding_invalid"|\
    "green_startup_failed stage=printer_binding reason=hosts_binding_conflict"|\
    "green_startup_failed stage=printer_binding reason=hosts_write_failed"|\
    "green_startup_failed stage=printer_binding reason=fixed_binding_unresolved"|\
    "green_startup_failed stage=printer_binding reason=fixed_binding_mismatch"|\
    "green_startup_failed stage=queue_configuration reason=queue_write_failed")
      printf '%s\n' "${child_marker}" > /run/cups/green-startup-failure 2>/dev/null || true
      printf '%s\n' "${child_marker}" >&2
      exit 78
      ;;
    *) fail_startup queue_initializer queue_initializer_failed ;;
  esac
}

# Bounded privileged initialization: ownership and two fixed processes only.
# Queue configuration is immutable in the image; no runtime queue mutation exists.
step mount_validation data_mount_invalid test -d /data
step mount_validation options_missing_or_empty test -s /data/options.json
step mount_validation options_unreadable test -r /data/options.json
step runtime_directory data_runtime_prepare_failed install -d -o greenprint -g greenprint -m 0700 /data/green-runtime
step runtime_directory spool_prepare_failed install -d -o greenprint -g greenprint -m 0700 /tmp/green-spool
step options_population runtime_options_install_failed install -o greenprint -g greenprint -m 0600 /data/options.json /data/green-runtime/options.json
step cups_directories cups_runtime_prepare_failed install -d -o cupsd -g cupsd -m 0750 /run/cups /var/log/cups /var/cache/cups
step cups_directories cups_spool_prepare_failed install -d -o cupsd -g cupsd -m 0700 /var/spool/cups
step bootstrap_interpreter interpreter_missing test -f /usr/bin/python3
step bootstrap_interpreter interpreter_missing test -x /usr/bin/python3
step printer_trust printer_identity_or_connection_failed env PYTHONPATH=/opt/green /usr/bin/python3 /opt/green/bootstrap_printer_trust.py /data/options.json /run/cups/printer-ca.crt
step ca_install ca_install_failed install -o root -g root -m 0644 /run/cups/printer-ca.crt /etc/cups/ssl/site.crt
/bin/busybox rm -f /run/cups/queue-initializer-error
queue="$(PYTHONPATH=/opt/green /usr/bin/python3 /opt/green/init_queue.py /data/options.json /run/cups/printers.conf 2>/run/cups/queue-initializer-error)" || fail_initializer
/bin/busybox rm -f /run/cups/queue-initializer-error
step queue_ownership queue_owner_failed chown cupsd:cupsd /run/cups/printers.conf
step queue_ownership queue_mode_failed chmod 0600 /run/cups/printers.conf
/usr/sbin/cupsd -f -c /etc/cups/cupsd.conf -s /etc/cups/cups-files.conf 2>/dev/null &
cupsd_pid=$!
if ! kill -0 "${cupsd_pid}" 2>/dev/null; then
  fail_startup cups_start cups_process_start_failed
fi
cups_ready=false
attempt=0
while [ "${attempt}" -lt 15 ]; do
  if ! kill -0 "${cupsd_pid}" 2>/dev/null; then
    wait "${cupsd_pid}" || true
    fail_startup cups_readiness cups_stopped_during_startup
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
  fail_startup cups_readiness cups_or_queue_not_ready
fi
step service_exec service_launcher_missing test -x /sbin/su-exec
step service_exec service_interpreter_missing test -x /usr/bin/python3
step service_exec service_script_unreadable test -r /opt/green/service.py
/sbin/su-exec greenprint:greenprint /usr/bin/python3 /opt/green/service.py 2>/dev/null || fail_startup service_exec service_process_failed
