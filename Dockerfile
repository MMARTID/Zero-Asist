FROM python:3.11-slim

# Evita logs raros y mejora rendimiento
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema mínimas (por si alguna lib las necesita)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copiar dependencias primero (cache eficiente)
COPY requirements.txt .

# Actualizar pip e instalar deps
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Cloud Run usa 8080
EXPOSE 8080

# Arranque robusto usando variable PORT (por si cambia)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]