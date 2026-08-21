FROM ghcr.io/home-assistant/aarch64-base:3.22

ARG BUILD_ARCH=aarch64
ARG BUILD_VERSION=0.2.0
ARG SOURCE_COMMIT=unknown
LABEL io.hass.type="app" \
      io.hass.arch="${BUILD_ARCH}" \
      io.hass.version="${BUILD_VERSION}" \
      org.opencontainers.image.title="Amadeus Green Print Bridge" \
      org.opencontainers.image.description="Private CUPS adapter for the bounded weekly-sheet pilot" \
      org.opencontainers.image.source="https://github.com/Crewless9086/amadeus-pig-tracking-system" \
      org.opencontainers.image.revision="${SOURCE_COMMIT}"

RUN apk add --no-cache cups cups-client cups-filters ca-certificates python3 su-exec \
    && addgroup -S greenprint && adduser -S -D -H -s /sbin/nologin -G greenprint greenprint \
    && addgroup -S cupsd && adduser -S -D -H -s /sbin/nologin -G cupsd cupsd \
    && mkdir -p /opt/green /data /run/cups /tmp/green-spool /var/spool/cups /var/log/cups \
    && chown greenprint:greenprint /data /tmp/green-spool \
    && chown cupsd:cupsd /run/cups /var/spool/cups /var/log/cups \
    && chmod 0700 /data /tmp/green-spool /var/spool/cups

COPY rootfs /
COPY app /opt/green/
RUN chmod 0755 /run.sh /init-green.sh /healthcheck.py \
    && chmod 0644 /etc/cups/cupsd.conf \
    && rm -f /etc/cups/printers.conf \
    && ln -s /run/cups/printers.conf /etc/cups/printers.conf

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD ["/healthcheck.py"]
CMD ["/run.sh"]
