FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api_liquidacion.py .

# Usuario sin privilegios
RUN useradd --create-home --uid 10001 app
USER app

EXPOSE 8000
CMD ["python", "api_liquidacion.py"]
