# Jarvis - Asistente Personal de Telegram (Local AI)

Este proyecto es un bot de Telegram diseñado para actuar como **Jarvis**, el asistente de IA personal de Aleix. Se ejecuta de forma local en un Mac Mini M4 y utiliza [Ollama](https://ollama.ai/) para procesar lenguaje natural utilizando el modelo `llama3`.

El bot tiene una personalidad predefinida: responde siempre en español, con un tono profesional, eficiente y con un toque de ingenio británico, imitando al Jarvis de Iron Man.

## ✨ Características Principales

*   **Inteligencia Artificial Local**: Utiliza Ollama con el modelo `llama3` ejecutándose completamente en local, lo que garantiza la privacidad de los datos.
*   **Enlace con WhatsApp (AppleScript)**: Jarvis es capaz de entender cuándo quieres enviar un mensaje a alguien y utilizar la UI de macOS para enviar mensajes de WhatsApp de forma totalmente autónoma.
*   **Búsqueda Web Integrada**: Conexión a internet mediante DuckDuckGo Search para obtener información actualizada en tiempo real a través del comando `/buscar`.
*   **Seguridad Estricta**: El bot está restringido para responder **únicamente** a un usuario específico (definido por su ID de Telegram). Ignorará cualquier intento de acceso de otros usuarios.
*   **Memoria Persistente (SSD)**: Jarvis mantiene un historial de los mensajes utilizando una base de datos SQLite configurada para almacenarse en un disco SSD externo. Esto proporciona contexto a largo plazo y sobrevive a reinicios del bot.
*   **Capturas del Sistema**: Si mencionas palabras como "foto", "pantalla" o "captura", tomará una captura de pantalla remota del Mac Mini y te la enviará por Telegram.
*   **Mantenimiento Automático**: Un script nocturno configurado vía `cron` se encarga de mantener actualizado el modelo de IA y envía reportes de mantenimiento por Telegram.
*   **Procesamiento Asíncrono**: Las llamadas al modelo de IA y la automatización de UI se realizan de forma asíncrona para no bloquear la recepción de nuevos mensajes en Telegram.

## 📋 Requisitos Previos

Para ejecutar este bot, necesitarás:

1.  **Python 3.8+** instalado (o un entorno virtual `venv`).
2.  **Ollama** instalado y ejecutándose en tu máquina.
3.  El modelo `llama3` descargado en Ollama. Puedes descargarlo ejecutando en tu terminal:
    ```bash
    ollama run llama3
    ```
4.  Permisos de **Accesibilidad** en macOS concedidos a la Terminal/Python para que el AppleScript pueda controlar WhatsApp.
5.  Un **Token de Bot de Telegram** (obtenido a través de [@BotFather](https://t.me/botfather)).
6.  Tu **ID de Usuario de Telegram** (puedes obtenerlo hablando con bots como [@userinfobot](https://t.me/userinfobot)).
7.  Un **SSD o unidad de almacenamiento externo** donde alojar la memoria (opcional pero recomendado, configurado en `.env`).

## 🚀 Instalación y Configuración

1.  **Clona o descarga** este repositorio.

2.  **Crea un entorno virtual e instala las dependencias** necesarias usando pip:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install python-telegram-bot python-dotenv ollama duckduckgo-search
    ```

3.  **Configura las variables de entorno**:
    Crea un archivo llamado `.env` en la raíz del proyecto y añade tus credenciales y rutas:
    ```env
    TELEGRAM_TOKEN="tu_token_de_telegram_aqui"
    USER_ID=tu_id_de_usuario_aqui
    DB_PATH="/Volumes/USB/jarvis_memory.db"
    ```

4.  **Configura el Mantenimiento Nocturno**:
    Haz ejecutable el script de actualización:
    ```bash
    chmod +x update_jarvis.sh
    ```
    Luego, añádelo a tu crontab para que se ejecute diariamente (por ejemplo, a las 04:00 AM):
    ```bash
    crontab -e
    # Añadir: 0 4 * * * /ruta/absoluta/a/tu/proyecto/update_jarvis.sh
    ```

## ⚙️ Uso

Para iniciar el servidor de Jarvis, usa el intérprete de tu entorno virtual en segundo plano con `nohup`:

```bash
nohup ./venv/bin/python bot.py > bot_output.log 2>&1 &
```

A partir de este momento, puedes ir a Telegram, buscar tu bot y enviarle el comando `/start`. Jarvis se presentará, inicializará su memoria SSD y estará listo para asistirte.

### Capacidades y Comandos

* `/start` - Inicializa a Jarvis y comprueba el estado del sistema.
* `/buscar [consulta]` - Jarvis conectará a la red global usando DuckDuckGo para buscar información actualizada y responderte basándose en los resultados.
* **Manejo Natural**: Escribe normalmente con Jarvis. Él recordará el contexto gracias a su memoria persistente en SQLite.
* **Enviar WhatsApp**: Dile de forma natural algo como "Jarvis, envíale un mensaje a Laura diciendo que llegaré en 10 minutos". Él detectará la intención, extraerá los datos en JSON y usará AppleScript para enviarlo por ti.
* **Capturas de Pantalla**: Menciona en cualquier frase "foto", "pantalla" o "captura" y obtendrás instantáneamente una imagen del estado de tu Mac Mini M4.

## 📝 Estructura del Código

*   `bot.py`: Contiene toda la lógica principal, integración con Telegram, base de datos SQLite, NLP Router para WhatsApp (AppleScript) y llamadas a Ollama/DuckDuckGo.
*   `update_jarvis.sh`: Script en Bash independiente para mantener actualizado el modelo `llama3` y notificar al usuario.
*   `.env`: Archivo (no incluido en el repositorio por seguridad) que almacena de forma segura el token, ID de usuario y la ruta del SSD.
*   `bot.log` / `bot_output.log`: Archivos generados automáticamente donde se registran eventos y posibles errores del sistema.

## 🔒 Privacidad y Seguridad

Al ejecutar el modelo de lenguaje de forma local mediante Ollama, ninguna parte de tus conversaciones se envía a servidores de terceros (como OpenAI o Google). Toda la inferencia ocurre en tu propia máquina (Mac Mini M4). Tu historial de conversación permanece completamente privado dentro de tu archivo SQLite en tu unidad local. Además, el filtro por `USER_ID` evita que otras personas interactúen con tu instancia de Jarvis o usen los comandos de sistema.