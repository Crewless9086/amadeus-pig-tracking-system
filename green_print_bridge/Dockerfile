FROM --platform=linux/arm64 ghcr.io/home-assistant/aarch64-base:3.22@sha256:0f19d1a4b031b3d141945a906e7c0d09fc98c796c18e2ea9072bce8e0b67578a

ARG BUILD_ARCH=aarch64
ARG BUILD_VERSION=0.3.7
ARG SOURCE_COMMIT
RUN test -n "${SOURCE_COMMIT}" \
    && test "${#SOURCE_COMMIT}" -eq 40 \
    && ! printf '%s' "${SOURCE_COMMIT}" | grep -Eq '[^0-9a-f]'
LABEL io.hass.type="app" \
      io.hass.arch="${BUILD_ARCH}" \
      io.hass.version="${BUILD_VERSION}" \
      org.opencontainers.image.title="Amadeus Green Print Bridge" \
      org.opencontainers.image.description="Fail-closed outbound CUPS adapter for the bounded weekly-sheet pilot" \
      org.opencontainers.image.source="https://github.com/Crewless9086/amadeus-pig-tracking-system" \
      org.opencontainers.image.revision="${SOURCE_COMMIT}" \
      org.opencontainers.image.version="${BUILD_VERSION}"

RUN apk add --no-cache cups cups-client cups-filters ca-certificates python3 su-exec \
    && addgroup -S greenprint && adduser -S -D -H -s /sbin/nologin -G greenprint greenprint \
    && addgroup -S cupsd && adduser -S -D -H -s /sbin/nologin -G cupsd cupsd \
    && chown root:cupsd /etc/cups/cups-files.conf && chmod 0640 /etc/cups/cups-files.conf \
    && sed -i -E '/^[[:space:]]*(User|Group|CreateSelfSignedCerts|Printcap|ErrorLog|ServerRoot)[[:space:]]+/d' /etc/cups/cups-files.conf \
    && printf '\nUser cupsd\nGroup cupsd\nCreateSelfSignedCerts no\nPrintcap /run/cups/printcap\nErrorLog stderr\nServerRoot /run/cups\n' >> /etc/cups/cups-files.conf \
    && mkdir -p /opt/green /data /run/cups /tmp/green-spool /var/spool/cups /var/log/cups /var/cache/cups /etc/cups/ssl \
    && chmod 0755 /etc/cups/ssl \
    && chown greenprint:greenprint /data /tmp/green-spool \
    && chown cupsd:cupsd /run/cups /var/spool/cups /var/log/cups /var/cache/cups \
    && chmod 0700 /data /tmp/green-spool /var/spool/cups

COPY rootfs /
COPY app /opt/green/
RUN chmod 0755 /run.sh /init-green.sh /healthcheck.py \
    && chmod 0644 /etc/cups/cupsd.conf \
    && grep -Fqx 'User cupsd' /etc/cups/cups-files.conf \
    && grep -Fqx 'Group cupsd' /etc/cups/cups-files.conf \
    && grep -Fqx 'CreateSelfSignedCerts no' /etc/cups/cups-files.conf \
    && grep -Fqx 'Printcap /run/cups/printcap' /etc/cups/cups-files.conf \
    && grep -Fqx 'ErrorLog stderr' /etc/cups/cups-files.conf \
    && grep -Fqx 'ServerRoot /run/cups' /etc/cups/cups-files.conf \
    && test "$(grep -Ec '^[[:space:]]*User[[:space:]]+' /etc/cups/cups-files.conf)" -eq 1 \
    && test "$(grep -Ec '^[[:space:]]*Group[[:space:]]+' /etc/cups/cups-files.conf)" -eq 1 \
    && test "$(grep -Ec '^[[:space:]]*CreateSelfSignedCerts[[:space:]]+' /etc/cups/cups-files.conf)" -eq 1 \
    && test "$(grep -Ec '^[[:space:]]*Printcap[[:space:]]+' /etc/cups/cups-files.conf)" -eq 1 \
    && test "$(grep -Ec '^[[:space:]]*ErrorLog[[:space:]]+' /etc/cups/cups-files.conf)" -eq 1 \
    && test "$(grep -Ec '^[[:space:]]*ServerRoot[[:space:]]+' /etc/cups/cups-files.conf)" -eq 1 \
    && rm -f /etc/cups/printers.conf \
    && /usr/sbin/cupsd -t -c /etc/cups/cupsd.conf -s /etc/cups/cups-files.conf

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD ["/healthcheck.py"]
CMD ["/bin/sh", "-c", "mkdir -p /run/cups 2>/dev/null || { echo 'green_startup_failed stage=s6_exec reason=failure_boundary_unavailable' >&2; exit 78; }; rm -f /run/cups/green-startup-failure 2>/dev/null || true; test -f /run.sh && test -r /run.sh || { echo 'green_startup_failed stage=s6_exec reason=run_script_unreadable' >&2; exit 78; }; /bin/sh /run.sh 2>/dev/null; status=$?; test \"${status}\" -eq 0 && exit 0; if test \"${status}\" -eq 78 && test -s /run/cups/green-startup-failure; then marker=\"$(/bin/busybox head -n 1 /run/cups/green-startup-failure)\"; if printf '%s\\n' \"${marker}\" | /bin/busybox grep -Eq '^green_startup_failed stage=[a-z_]+ reason=[a-z_]+$'; then printf '%s\\n' \"${marker}\" >&2; exit 78; fi; fi; echo 'green_startup_failed stage=s6_exec reason=run_script_failed' >&2; exit 78"]
