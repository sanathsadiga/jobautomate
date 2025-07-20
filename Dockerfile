# ---------------- Stage 1: Builder (install Python deps incl. any wheels build) ----------------
FROM python:3.11-slim@sha256:139020233cc412efe4c8135b0efe1c7569dc8b28ddd88bddb109b764f8977e30 AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System packages ONLY needed to build Python deps (remove heavy stuff after build)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev \
    # (If pdfplumber / pillow compiled extras) 
    libjpeg62-turbo-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency file(s) first for better layer caching
COPY requirements.txt ./
# Install dependencies into the image (global site-packages)
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# ---------------- Stage 2: Runtime ----------------
FROM python:3.11-slim@sha256:139020233cc412efe4c8135b0efe1c7569dc8b28ddd88bddb109b764f8977e30

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install ONLY runtime system libraries (Postgres client, Chromium, chromedriver, minimal GUI libs for headless)
# Using Debian/Ubuntu repo chromium + chromium-driver keeps versions matched automatically
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    chromium chromium-driver \
    # Common headless chrome runtime deps (some may already be pulled as transitive)
    libnss3 libgdk-pixbuf-2.0-0 libgtk-3-0 libx11-6 libxkbcommon0 libxi6 libgconf-2-4 libasound2 \
    libdrm2 libgbm1 libxcomposite1 libxdamage1 libxrandr2 libxtst6 \
    libjpeg62-turbo zlib1g \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# (Optional) set environment vars Selenium code can rely on
ENV CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/lib/chromium/chromedriver

# Copy Python site-packages & binaries from builder
COPY --from=builder /usr/local /usr/local

WORKDIR /app

# Copy application source
COPY . .

# Create non-root user and adjust ownership
RUN addgroup --system app && adduser --system --ingroup app app \
    && chown -R app:app /app

USER app

EXPOSE 8000

# (Optional) set PYTHONPATH if you rely on implicit imports
# ENV PYTHONPATH=/app

# Default command - gunicorn (recommended) OR uvicorn. You used uvicorn; keeping it.
# For improved prod robustness, consider gunicorn+uvicorn workers:
# CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
