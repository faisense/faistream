# Multi-arch (linux/amd64, linux/arm64) image for the faistream service.
#   docker build -t faistream .
#   docker run --rm -v ./faistream.yaml:/config/config.yaml -p 7300-7310:7300-7310 faistream
# With `network: true` in the config, programs elsewhere receive frames on 7301 and up.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

RUN useradd --create-home --uid 1000 faistream

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[all]"

# Consumers reading shared memory must run as the same user (segments are 0600).
USER faistream
EXPOSE 7300
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s CMD ["faistream", "ls"]
ENTRYPOINT ["faistream"]
CMD ["serve", "/config/config.yaml"]
