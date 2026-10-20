# Base liviana fijada a Debian bookworm (python:3.13-slim pasó a trixie, no soportado por
# Playwright 1.49). Se instalan a mano las librerías de sistema de Chromium y solo se descarga
# el navegador con 'playwright install chromium', sin --with-deps (que fallaba por fuentes).
# Mucho más liviana que la imagen oficial de Playwright, que no cabía en el disco de build de Render.
FROM python:3.13-slim-bookworm

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
# Los navegadores se instalan en una ruta compartida para que el usuario 'app' los lea
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app

# Dependencias de sistema que Chromium headless necesita (lista estable de Debian bookworm)
RUN apt-get update && apt-get install -y --no-install-recommends \
      libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
      libdbus-1-3 libatspi2.0-0 libx11-6 libxcomposite1 libxdamage1 libxext6 \
      libxfixes3 libxrandr2 libgbm1 libxcb1 libxkbcommon0 libpango-1.0-0 \
      libcairo2 libasound2 libglib2.0-0 libxshmfence1 \
      fonts-liberation libfontconfig1 ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && playwright install chromium \
 && chmod -R a+rx /ms-playwright

COPY api_liquidacion.py .

# Usuario sin privilegios
RUN useradd --create-home --uid 10001 app
USER app

EXPOSE 8000
CMD ["python", "api_liquidacion.py"]
