# ==========================================
# AutoHeal DevOps - Test Microservice Dockerfile
# Python 3.12-slim, non-root user (UID 10001)
# Zero external dependencies (Python stdlib)
# ==========================================
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd -g 10001 autoheal && \
    useradd -u 10001 -g autoheal -s /bin/bash -m autoheal

COPY --chown=autoheal:autoheal server.py /app/server.py

USER autoheal

EXPOSE 8080 8081 8082

HEALTHCHECK --interval=10s --timeout=3s --start-period=3s --retries=3 \
  CMD python -c "import urllib.request, os; port = os.environ.get('SERVICE_PORT', '8080'); urllib.request.urlopen(f'http://127.0.0.1:{port}/health')" || exit 1

CMD ["python", "server.py"]
