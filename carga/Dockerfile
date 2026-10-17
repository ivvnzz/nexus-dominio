FROM python:3.12-slim
WORKDIR /app
COPY carga/requirements.txt /app/carga/requirements.txt
RUN pip install --no-cache-dir -r /app/carga/requirements.txt
COPY carga/ /app/carga/
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "carga.cargar"]
