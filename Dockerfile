# Imagen base liviana con Python 3.13
FROM python:3.13-slim

WORKDIR /app

# Instalar dependencias primero (Docker cachea esta capa si requirements.txt no cambia)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código del backend y los archivos estáticos de la PWA
COPY app/ ./app/
COPY static/ ./static/

# Fly enruta el tráfico al puerto interno 8080
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
