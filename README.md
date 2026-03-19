# Jarvis - Asistente Personal de Telegram (Agent AI)

Este proyecto es un bot de Telegram diseñado para actuar como **Jarvis**, el asistente de IA personal de Aleix. Se ejecuta de forma local en un Mac Mini M4 y utiliza la API de **Gemini** (Google Generative AI) con **Function Calling nativo** (Arquitectura de Agentes) para procesar lenguaje natural, buscar información, realizar cálculos y automatizar el sistema.

El bot tiene una personalidad predefinida: responde con un tono inteligente, conversacional y directo, imitando al Jarvis de Iron Man.

## ✨ Características Principales

*   **Arquitectura de Agentes (Function Calling)**: Utiliza un sistema de auto-descubrimiento para usar siempre el modelo `gemini-flash` más reciente. El Agente decide de forma autónoma cuándo chatear, cuándo buscar en internet, cuándo calcular o cuándo ejecutar automatizaciones en el Mac, sin depender de prompts frágiles de "intent parsing".
*   **Future-Proofing (Auto-Actualización)**: Al arrancar, consulta la API de Google, filtra los modelos "flash", los ordena por versión y selecciona dinámicamente el más avanzado disponible (ej. saltará de 1.5 a 2.0 o 3.0 automáticamente).
*   **Enlace con WhatsApp (AppleScript)**: Jarvis puede buscar contactos en la agenda de macOS y enviar mensajes de WhatsApp de forma totalmente autónoma utilizando AppleScript y Deep Links.
*   **Búsqueda Web Integrada**: El Agente utiliza la herramienta de DuckDuckGo Search para buscar información en internet de manera transparente cuando se le hacen preguntas de actualidad.
*   **Calculadora Integrada**: El Agente cuenta con una herramienta para resolver operaciones matemáticas de forma precisa.
*   **Seguridad Estricta**: El bot está restringido para responder **únicamente** a un usuario específico (definido por su ID de Telegram). Ignorará cualquier intento de acceso de otros usuarios.
*   **Memoria Persistente (SSD)**: Jarvis mantiene un historial de los mensajes utilizando una base de datos SQLite configurada para almacenarse en un disco SSD externo.
*   **Capturas del Sistema**: Si mencionas palabras como "foto", "pantalla" o "captura", tomará una captura de pantalla remota del Mac Mini y te la enviará por Telegram.

## 📋 Requisitos Previos

Para ejecutar este bot, necesitarás:

1.  **Python 3.8+** instalado.
2.  Una **API Key de Google Gemini** obtenida desde Google AI Studio.
3.  Permisos de **Accesibilidad** y **Automatización** en macOS concedidos a la Terminal/Python para que el AppleScript pueda controlar WhatsApp y Contactos.
4.  Un **Token de Bot de Telegram** (obtenido a través de [@BotFather](https://t.me/botfather)).
5.  Tu **ID de Usuario de Telegram** (puedes obtenerlo hablando con bots como [@userinfobot](https://t.me/userinfobot)).
6.  Un **SSD o unidad de almacenamiento externo** donde alojar la memoria SQLite.

## 🚀 Instalación y Configuración

1.  **Clona o descarga** este repositorio.

2.  **Crea un entorno virtual e instala las dependencias** necesarias usando pip:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install python-telegram-bot python-dotenv google-generativeai duckduckgo-search
    ```

3.  **Configura las variables de entorno**:
    Crea un archivo llamado `.env` en la raíz del proyecto y añade tus credenciales:
    ```env
    TELEGRAM_TOKEN="tu_token_de_telegram_aqui"
    USER_ID=tu_id_de_usuario_aqui
    GEMINI_API_KEY="tu_api_key_de_gemini_aqui"
    ```
    Asegúrate también de actualizar la ruta `DB_PATH` dentro de `bot.py` según tu sistema de archivos.

## ⚙️ Uso

Para iniciar a Jarvis:

```bash
source .venv/bin/activate
python bot.py
```

A partir de este momento, puedes ir a Telegram, buscar tu bot y hablarle de forma natural. 

### Capacidades del Agente

* **Charla Natural**: Escribe normalmente con Jarvis. Él recordará el contexto de la conversación (hasta 4 mensajes de historial).
* **Enviar WhatsApp**: Dile de forma natural algo como "Jarvis, envíale un mensaje a Laura diciendo que llegaré en 10 minutos". El Agente deducirá automáticamente que debe usar la herramienta `herramienta_whatsapp`, buscará el contacto y enviará el mensaje.
* **Búsqueda en Internet**: Pregunta cosas como "¿Qué tiempo hace hoy en Madrid?" o "¿Quién ganó el partido de ayer?". El Agente usará la herramienta `herramienta_internet` para responderte con datos reales.
* **Cálculos Matemáticos**: Pídele que resuelva operaciones complejas y utilizará la `herramienta_calculadora`.
* **Capturas de Pantalla**: Menciona en cualquier frase "foto", "pantalla" o "captura" y obtendrás instantáneamente una imagen del estado de tu Mac.

## 📝 Estructura del Código

*   `bot.py`: Contiene toda la lógica principal, la definición de las Herramientas (WhatsApp, Internet, Calculadora), la configuración de `GenerativeModel` de Gemini con Function Calling, el historial SQLite y la integración con Telegram.
*   `.env`: Archivo (no incluido en el repositorio) que almacena las variables de entorno.
*   `bot.log`: Archivo generado automáticamente donde se registran eventos y errores.
