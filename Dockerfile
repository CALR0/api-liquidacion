# Imagen oficial de Playwright: ya trae Chromium + todas sus dependencias de sistema,
# y la versión coincide con playwright==1.49.0 de requirements.txt. Evita el --with-deps
# que fallaba en Debian trixie por paquetes de fuentes inexistentes.
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# venv para evitar el bloqueo "externally managed environment" de Ubuntu al usar pip
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api_liquidacion.py .

# La imagen trae el usuario sin privilegios 'pwuser'; los navegadores en /ms-playwright son suyos
USER pwuser

EXPOSE 8000
CMD ["python", "api_liquidacion.py"]
