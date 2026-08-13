FROM python:3.11-slim

WORKDIR /app
COPY server /app/server

ENV BILLING_HOST=0.0.0.0
ENV BILLING_PORT=8787
ENV BILLING_DATABASE=/data/billing.sqlite3

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data

USER appuser
EXPOSE 8787
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8787/health', timeout=3)"

CMD ["python", "/app/server/billing_service.py"]
