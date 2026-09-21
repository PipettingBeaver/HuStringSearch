FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HUSTRING_GRAPH=/data/graph \
    HUSTRING_CACHE=/data/cache \
    HUSTRING_WEB_DIR=/app/web \
    HUSTRING_AUTO_BUILD=1 \
    PORT=8000

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY web ./web
RUN pip install ".[web]"

COPY docker/entrypoint.sh /usr/local/bin/hustring-entrypoint
RUN chmod +x /usr/local/bin/hustring-entrypoint

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request,sys; p=os.environ.get('PORT','8000'); sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+p+'/api/health').status == 200 else 1)"

ENTRYPOINT ["hustring-entrypoint"]
