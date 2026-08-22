#!/bin/sh
set -eu
umask 0077

# Bounded privileged initialization: ownership and two fixed processes only.
# Queue configuration is immutable in the image; no runtime queue mutation exists.
install -d -o greenprint -g greenprint -m 0700 /data /tmp/green-spool
install -d -o cupsd -g cupsd -m 0750 /run/cups /var/log/cups /var/cache/cups
install -d -o cupsd -g cupsd -m 0700 /var/spool/cups
test -s /config/private-ca.crt
install -o root -g root -m 0644 /config/private-ca.crt /etc/cups/ssl/site.crt
PYTHONPATH=/opt/green /usr/bin/python3 /opt/green/init_queue.py /data/options.json /run/cups/printers.conf
chown cupsd:cupsd /run/cups/printers.conf
chmod 0600 /run/cups/printers.conf
/usr/sbin/cupsd -f &
exec /sbin/su-exec greenprint:greenprint /usr/bin/python3 /opt/green/service.py
