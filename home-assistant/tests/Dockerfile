# Test runner for the dashboard's end-to-end tests: pytest + Playwright (Chromium), pinned.
# The playwright pip package must match the image's browsers (same version).
FROM mcr.microsoft.com/playwright/python:v1.62.0-noble

RUN pip install --no-cache-dir --break-system-packages \
      playwright==1.62.0 \
      pytest==8.4.2 \
      pytest-playwright==0.7.1 \
      requests==2.32.5 \
      websocket-client==1.8.0 \
      docker==7.1.0

ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /e2e
