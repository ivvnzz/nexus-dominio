# Microservicio de dominio de Nexus Retail (FastAPI + PostgreSQL), puerto 3000 de la red interna.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY dominio/requirements.txt .
RUN pip install -r requirements.txt

COPY dominio/app ./app

RUN useradd --system --no-create-home dominio
USER dominio

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3000/health', timeout=2)"]

# Un proceso por contenedor: la escala se hace con réplicas en el compose, no con workers.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000", "--no-access-log"]
