FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
# Los navegadores de Playwright se instalan en una ruta compartida para que el usuario 'app' los lea
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app

COPY requirements.txt .
# Chromium + sus dependencias de sistema (apt) para resolver el desafío de AWS WAF.
# --with-deps corre apt-get (requiere root; el build de Docker lo es hasta 'USER app').
RUN pip install --no-cache-dir -r requirements.txt \
 && playwright install --with-deps chromium \
 && chmod -R a+rx /ms-playwright

COPY api_liquidacion.py .

# Usuario sin privilegios
RUN useradd --create-home --uid 10001 app
USER app

EXPOSE 8000
CMD ["python", "api_liquidacion.py"]
