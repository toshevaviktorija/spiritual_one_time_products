FROM python:3.12-slim-bookworm AS builder
ENV PIP_NO_CACHE_DIR=1
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential pkg-config libcairo2-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip wheel --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core libfreetype6 libjpeg62-turbo zlib1g libcairo2 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels -r requirements.txt && rm -rf /wheels
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app
COPY --chown=app:app . .
RUN mkdir -p /app/private_reports /app/staticfiles && chown -R app:app /app/private_reports /app/staticfiles
USER app
EXPOSE 8000
ENTRYPOINT ["sh", "/app/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "150", "--access-logfile", "-", "--error-logfile", "-"]
