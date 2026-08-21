#!/usr/bin/with-contenv bashio
set -euo pipefail
umask 077

# Bounded privileged initialization: ownership and two fixed processes only.
# Queue configuration is immutable in the image; no runtime queue mutation exists.
install -d -o greenprint -g greenprint -m 0700 /data /tmp/green-spool
install -d -o cupsd -g cupsd -m 0750 /run/cups /var/log/cups
install -d -o cupsd -g cupsd -m 0700 /var/spool/cups
/usr/bin/python3 /opt/green/init_queue.py /data/options.json /run/cups/printers.conf
chown cupsd:cupsd /run/cups/printers.conf
chmod 0600 /run/cups/printers.conf
su-exec cupsd:cupsd /usr/sbin/cupsd -f &
exec su-exec greenprint:greenprint /usr/bin/python3 /opt/green/service.py
