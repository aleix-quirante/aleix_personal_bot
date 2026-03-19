import os
import re
import logging
import asyncio
import json
import sqlite3
import subprocess
import urllib.parse
import requests
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from duckduckgo_search import DDGS

load_dotenv()

# --- CONFIGURACIÓN ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
USER_ID = int(os.getenv("USER_ID", "0"))
DB_PATH = "/Volumes/USB/jarvis_memory.db"  # Ruta directa al SSD

logging.basicConfig(level=logging.INFO, filename="bot.log")


# --- MEMORIA ---
def setup_database():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, role TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.commit()
    conn.close()


def save_message(role, content):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO messages (role, content) VALUES (?, ?)", (role, content))
    conn.commit()
    conn.close()


def get_context(limit=15):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT role, content FROM (SELECT * FROM messages ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
            (limit,),
        )
        rows = cursor.fetchall()
        conn.close()
        return [{"role": r, "content": c} for r, c in rows]
    except:
        return []


# --- HERRAMIENTAS ---
def search_mac_contact(search_name):
    # Dividimos el nombre en palabras sueltas
    words = search_name.strip().split()
    if not words:
        return None

    logging.info(f"Buscando en Contactos de macOS: {search_name}")
    print(f"🔍 [AGENTE] Intentando buscar en AppleScript: {search_name}")
    # Nota sobre permisos: Asegúrate de que la Terminal/VSCode/Python tengan permisos
    # en Ajustes del Sistema -> Privacidad y Seguridad -> Contactos

    # Construimos una condición flexible en AppleScript
    # Ej: name contains "antonio" and name contains "quirante"
    conditions = " and ".join([f'name contains "{p}"' for p in words])

    applescript = f"""
    tell application "Contacts"
        try
            -- Búsqueda elástica: Ignora si hay segundos nombres o apellidos entre medias
            set laPersona to first person whose {conditions}
            set elNumero to value of first phone of laPersona
            return elNumero
        on error
            try
                -- Fallback: Buscar solo por la primera palabra (nombre de pila)
                set laPersona to first person whose name contains "{words[0]}"
                set elNumero to value of first phone of laPersona
                return elNumero
            on error
                return "NO_ENCONTRADO"
            end try
        end try
    end tell
    """
    try:
        result = subprocess.run(
            ["osascript", "-e", applescript], capture_output=True, text=True
        )
        raw_number = result.stdout.strip()

        if raw_number == "NO_ENCONTRADO" or not raw_number:
            return None

        return re.sub(r"\D", "", raw_number)
    except Exception as e:
        logging.error(f"Error buscando contacto: {e}")
        return None


async def send_whatsapp(contact: str, message: str) -> str:
    """
    Usa esta herramienta EXCLUSIVAMENTE cuando el usuario te pida enviar un mensaje a alguien por WhatsApp o Telegram.
    Argumentos:
    - contact: El nombre de la persona EXACTO (ej. 'Iñaki', 'Noemi Arans'). Separa adecuadamente el nombre del resto de la frase u órdenes anexas.
    - message: El texto completo que quieres enviarle.
    """
    try:
        # 1. Buscar en Mac (usamos la función search_mac_contact que ya tienes definida)
        number = search_mac_contact(contact)
        if not number:
            return f"Error: No encontré a {contact} en la agenda."

        # 2. AppleScript y URL Deep Link
        url_text = urllib.parse.quote(message)
        url_whatsapp = f"whatsapp://send?phone={number}&text={url_text}"

        try:
            subprocess.run(["open", url_whatsapp], check=True)
        except Exception as e:
            return f"Error: No se pudo abrir la aplicación de WhatsApp. Verifica que está instalada."

        await asyncio.sleep(5)  # Esperar a que la app abra sin bloquear el bot

        print(f"DEBUG: Intentando enviar mensaje a {number}...")

        # Nuevo AppleScript mejorado para 2026
        script_send = """
        tell application "WhatsApp" to activate
        delay 2
        tell application "System Events"
            tell process "WhatsApp"
                set frontmost to true
                -- Intento 1: Pulsar Enter de forma nativa
                keystroke return
                delay 1
                -- Intento 2: Buscar el botón "Enviar" y hacer click físico
                try
                    click (first button whose description is "Enviar")
                end try
                try
                    click (first button whose description is "Send")
                end try
            end tell
        end tell
        """
        await asyncio.to_thread(
            subprocess.run, ["osascript", "-e", script_send], check=True
        )
        return f"Éxito: Mensaje enviado a {contact}."
    except Exception as e:
        return f"Error al enviar: {str(e)}"


def web_search(query: str) -> str:
    """
    Usa esta herramienta para buscar información en internet (el clima, noticias actuales, datos que no sepas).
    Argumentos:
    - query: Los términos de búsqueda.
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
        if not results:
            return "No hay resultados en internet."
        return "\n".join([f"- {r['title']}: {r['body']}" for r in results])
    except Exception as e:
        return f"Error buscando en internet: {str(e)}"


def calculator(operation: str) -> str:
    """
    Usa esta herramienta para resolver operaciones matemáticas complejas.
    Argumentos:
    - operation: La expresión matemática (ej. '25 * 4 + 10').
    """
    try:
        # Solo evalúa matemáticas básicas por seguridad
        result = eval(operation, {"__builtins__": None}, {})
        return f"El resultado es {result}"
    except Exception as e:
        return "Error en el cálculo."


def get_weather(city: str) -> str:
    """
    Usa esta herramienta EXCLUSIVAMENTE para saber el tiempo meteorológico, temperatura o pronóstico de una ciudad.
    Argumentos:
    - city: El nombre de la ciudad (ej. 'Sabadell', 'Madrid').
    """
    try:
        # wttr.in devuelve el tiempo en formato texto plano rápido y gratis
        url = f"https://wttr.in/{city}?format=4&M"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return f"El tiempo actual en {city} es: {response.text}"
        return "No pude obtener los datos meteorológicos del servidor."
    except Exception as e:
        return f"Error de conexión al buscar el clima: {str(e)}"


# --- PREVENCIÓN DE REPOSO ---
def prevent_system_sleep():
    """
    Usa el comando nativo de macOS 'caffeinate' para evitar que el Mac Mini M4
    entre en reposo mientras el bot esté en ejecución, asegurando operatividad 24/7.
    -i: evita reposo del sistema.
    -m: evita reposo del monitor.
    -s: evita reposo del equipo al estar conectado a corriente.
    """
    try:
        subprocess.Popen(["caffeinate", "-ims"])
        logging.info("Sistema caffeinate activado. Reposo prevenido.")
    except Exception as e:
        logging.error(f"No se pudo activar caffeinate: {e}")


# Inicializamos el modelo de Gemini con las instrucciones de sistema
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


def get_latest_flash_model():
    """
    Se conecta a Google API y busca dinámicamente la versión más reciente
    del modelo Flash para auto-actualizar el bot.
    """
    try:
        flash_models = []
        # Iteramos sobre todos los modelos disponibles en la cuenta de Google
        for m in genai.list_models():
            if (
                "generateContent" in m.supported_generation_methods
                and "flash" in m.name.lower()
            ):
                # Filtramos versiones experimentales si queremos estabilidad pura,
                # o simplemente cogemos todos los flash.
                flash_models.append(m.name)

        if not flash_models:
            logging.warning("No se encontraron modelos Flash. Usando fallback.")
            return "gemini-1.5-flash"

        # Al ordenar alfabéticamente de forma inversa, 'gemini-3.0-flash'
        # quedará por encima de 'gemini-2.0-flash' o 'gemini-1.5-flash'
        flash_models.sort(reverse=True)

        chosen_model = flash_models[0]
        print(f"🤖 [SISTEMA] Jarvis auto-actualizado al modelo: {chosen_model}")
        return chosen_model

    except Exception as e:
        logging.error(f"Error descubriendo modelos: {e}")
        return "gemini-1.5-flash"  # Fallback de seguridad


# Inicializamos el modelo de Gemini usando auto-descubrimiento
jarvis_model = genai.GenerativeModel(
    model_name=get_latest_flash_model(),
    tools=[
        send_whatsapp,
        web_search,
        calculator,
        get_weather,
    ],
    system_instruction="""Eres Jarvis, el asistente de inteligencia artificial personal de Aleix. 
    REGLAS ESTRICTAS DE PERSONALIDAD:
    1. Habla SIEMPRE de forma natural, conversacional y directa (estilo Iron Man).
    2. TIENES TOTALMENTE PROHIBIDO usar prefijos robóticos. NUNCA empieces tus frases con "Acción completada:", "Resultado:", "Jarvis:", "Sistema:", o "Mensaje:".
    3. Cuando uses una herramienta (como enviar un WhatsApp o buscar en internet), simplemente dile a Aleix lo que has hecho o lo que has encontrado, integrándolo en tu respuesta como un humano.
    4. Sé conciso y educado.
    5. NUNCA intentes usar web_search para buscar números de teléfono de personas. Los números de teléfono solo pueden obtenerse a través de la agenda local del Mac.""",
)


# --- PROCESAMIENTO ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != USER_ID:
        logging.warning(
            f"Intento de acceso no autorizado del ID: {update.effective_user.id}"
        )
        return

    user_text = update.message.text
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )

    # 1. Interceptor Visual: Captura de pantalla directa
    if any(
        k in user_text.lower() for k in ["foto", "pantalla", "captura", "screenshot"]
    ):
        try:
            import subprocess

            logging.info(
                "Intentando capturar pantalla (puede salir negra si el Mac está en reposo)."
            )
            # -x hace la captura en silencio (sin el sonido del disparador del Mac)
            subprocess.run(["screencapture", "-x", "snap.png"], check=True)
            await update.message.reply_photo(
                photo=open("snap.png", "rb"),
                caption="📸 Sistemas visuales en línea. Aquí tiene la captura de la pantalla principal.",
            )
            return  # Salimos para que Gemini no intente responder también con texto
        except Exception as e:
            logging.error(f"Error al tomar captura: {e}")
            await update.message.reply_text("❌ Error en los sistemas ópticos del Mac.")
            return

    # Instanciamos un chat con ejecución automática de herramientas
    chat = jarvis_model.start_chat(enable_automatic_function_calling=True)

    try:
        # Le pasamos el historial de los últimos mensajes al chat (opcional, si quieres mantener el tuyo de SQLite)
        history = get_context(limit=4)
        chat_context = "\n".join([f"{m['role']}: {m['content']}" for m in history])

        # Mandamos el mensaje a Gemini. ¡ÉL DECIDE QUÉ HACER!
        full_prompt = f"Historial previo:\n{chat_context}\n\nOrden actual: {user_text}"
        gemini_response = await asyncio.to_thread(chat.send_message, full_prompt)

        reply = gemini_response.text

        # Guardamos y respondemos
        save_message("user", user_text)
        save_message("assistant", reply)
        await update.message.reply_text(reply)

    except Exception as e:
        logging.error(f"Error crítico en el Agente: {e}")
        await update.message.reply_text(
            "❌ Mis sistemas principales han colapsado temporalmente."
        )


if __name__ == "__main__":
    setup_database()
    print("🚀 Jarvis en línea. Mac Mini M4 bajo control.")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    prevent_system_sleep()
    app.run_polling()
