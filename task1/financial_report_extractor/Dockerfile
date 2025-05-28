# Usa una imagen base oficial de Python
FROM python:3.9-slim

# Establece el directorio de trabajo en /app
WORKDIR /app

# Copia el archivo de requerimientos al contenedor
COPY requirements.txt .

# Instala las dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto del código de la aplicación al directorio de trabajo
COPY ./app /app

# Expone el puerto en el que corre la aplicación FastAPI (debe coincidir con Uvicorn)
EXPOSE 8000

# Comando para correr la aplicación usando Uvicorn
# El host 0.0.0.0 permite que la aplicación sea accesible desde fuera del contenedor
# --reload es útil para desarrollo, para producción se quitaría
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
