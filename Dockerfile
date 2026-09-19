FROM python:3.12-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY app ./app
RUN pip wheel --no-cache-dir --wheel-dir /wheels .
RUN git clone https://github.com/NickWaterton/samsung-tv-ws-api.git /samsung-source && \
    git -C /samsung-source checkout fe95ef1d784cd32f49bf9a07ec479576574eea07 && \
    git -C /samsung-source archive --format=tar.gz --output=/samsungtvws-source.tar.gz HEAD

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 FRAME_DATA_DIR=/data
RUN useradd --uid 10001 --create-home frame && mkdir /data && chown frame:frame /data
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir --no-deps /wheels/* && rm -rf /wheels
WORKDIR /opt/frame
COPY scripts ./scripts
COPY LICENSE THIRD_PARTY_NOTICES.md ./
COPY --from=build /samsungtvws-source.tar.gz /usr/share/adaptive-frame-matte/samsungtvws-source.tar.gz
USER 10001:10001
VOLUME ["/data"]
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/healthz', timeout=3)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8787", "--no-access-log"]
