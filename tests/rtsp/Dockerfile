FROM python:3.12-slim
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_ROOT_USER_ACTION=ignore
WORKDIR /src
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[all]" pytest
COPY tests ./tests
CMD ["pytest", "-v", "-p", "no:cacheprovider", "tests/rtsp/test_rtsp.py"]
