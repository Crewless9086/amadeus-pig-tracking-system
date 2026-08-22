FROM --platform=linux/arm64 ghcr.io/home-assistant/aarch64-base:3.22@sha256:0f19d1a4b031b3d141945a906e7c0d09fc98c796c18e2ea9072bce8e0b67578a

ARG BUILD_ARCH=aarch64
ARG BUILD_VERSION=0.3.2
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
