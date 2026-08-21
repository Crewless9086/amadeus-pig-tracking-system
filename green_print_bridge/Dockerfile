FROM ghcr.io/home-assistant/aarch64-base:3.22

ARG BUILD_ARCH=aarch64
ARG BUILD_VERSION=0.1.0
LABEL io.hass.type="app" \
      io.hass.arch="${BUILD_ARCH}" \
      io.hass.version="${BUILD_VERSION}" \
      org.opencontainers.image.title="Amadeus Green Print Bridge" \
      org.opencontainers.image.description="Private CUPS adapter for the bounded weekly-sheet pilot" \
      org.opencontainers.image.source="https://github.com/Crewless9086/amadeus-pig-tracking-system"

RUN apk add --no-cache cups cups-client cups-filters ca-certificates python3 \
    && mkdir -p /opt/green /data /run/cups /tmp/green-spool \
    && chmod 0700 /data /tmp/green-spool

COPY rootfs /
COPY app /opt/green/
RUN chmod 0755 /run.sh /healthcheck.py \
    && chmod 0644 /etc/cups/cupsd.conf

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD ["/healthcheck.py"]
CMD ["/run.sh"]
