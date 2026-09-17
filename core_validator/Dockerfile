FROM python:3.12-slim@sha256:dd29372629eeba2dd003fd9e9d35a5b8236c44727875a0364254b5127af88e65

ARG SOURCE_COMMIT

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && git config --system --add safe.directory /source \
    && python -m pip install --no-cache-dir pytest==8.4.1 python-dotenv==1.0.1

LABEL org.opencontainers.image.source="https://github.com/Crewless9086/amadeus-pig-tracking-system" \
      org.opencontainers.image.revision="${SOURCE_COMMIT}" \
      org.opencontainers.image.version="v1-${SOURCE_COMMIT}" \
      org.opencontainers.image.title="Amadeus CORE isolated validator"

USER 65532:65532
WORKDIR /source
CMD ["python3"]
