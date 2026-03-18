#!/bin/bash

# Cargar variables de entorno
set -a
source /Users/v2estudio/aleix_jarvis/.env
set +a

# Actualizar el modelo de Ollama
/usr/local/bin/ollama pull llama3

# Enviar mensaje por Telegram
curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage" \
    -d chat_id="${USER_ID}" \
    -d text="🔧 Mantenimiento nocturno: Modelo actualizado y optimizado en el Mac Mini M4." \
    > /dev/null
