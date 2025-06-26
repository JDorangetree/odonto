#!/bin/bash

echo "Running custom startup script..."

# Instalar ffmpeg y ffprobe
# Para sistemas basados en Debian/Ubuntu (usado por Azure App Services Linux)
apt-get update -y
apt-get install -y ffmpeg

# Verificar que ffmpeg se instaló correctamente
if ! command -v ffmpeg &> /dev/null
then
    echo "ffmpeg could not be found, attempting alternative installation."
    # Si la anterior falla, intenta con otra forma (menos común en App Services)
    # Esto es un fallback, la línea de arriba suele funcionar
    # wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
    # tar -xf ffmpeg-release-amd64-static.tar.xz
    # mv ffmpeg-*-amd64-static/ffmpeg /usr/local/bin/
    # mv ffmpeg-*-amd64-static/ffprobe /usr/local/bin/
    # rm -rf ffmpeg-*-amd64-static*
fi

echo "ffmpeg/ffprobe installation complete or verified."

# Comando para iniciar tu aplicación FastAPI
# Reemplaza 'main:app' si tu archivo y objeto FastAPI tienen otros nombres
# Usamos gunicorn como servidor de producción, con uvicorn workers
exec gunicorn -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 main:app

echo "Application started."