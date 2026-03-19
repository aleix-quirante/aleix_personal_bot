import os
import re
import logging
import asyncio
import json
import sqlite3
import subprocess
import urllib.parse
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
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, role TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)"
    )
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
def buscar_contacto_mac(nombre_buscar):
    # Dividimos el nombre en palabras sueltas
    palabras = nombre_buscar.strip().split()
    if not palabras:
        return None

    # Construimos una condición flexible en AppleScript
    # Ej: name contains "antonio" and name contains "quirante"
    condiciones = " and ".join([f'name contains "{p}"' for p in palabras])

    applescript = f"""
    tell application "Contacts"
        try
            -- Búsqueda elástica: Ignora si hay segundos nombres o apellidos entre medias
            set laPersona to first person whose {condiciones}
            set elNumero to value of first phone of laPersona
            return elNumero
        on error
            return "NO_ENCONTRADO"
        end try
    end tell
    """
    try:
        resultado = subprocess.run(
            ["osascript", "-e", applescript], capture_output=True, text=True
        )
        numero_bruto = resultado.stdout.strip()

        if numero_bruto == "NO_ENCONTRADO" or not numero_bruto:
            return None

        return re.sub(r"\D", "", numero_bruto)
    except Exception as e:
        logging.error(f"Error buscando contacto: {e}")
        return None


def herramienta_whatsapp(contacto: str, mensaje: str) -> str:
    """
    Usa esta herramienta EXCLUSIVAMENTE cuando el usuario te pida enviar un mensaje a alguien por WhatsApp o Telegram.
    Argumentos:
    - contacto: El nombre de la persona (ej. 'Iñaki', 'Noemi Arans').
    - mensaje: El texto que quieres enviarle.
    """
    try:
        # 1. Buscar en Mac (usamos la función buscar_contacto_mac que ya tienes definida)
        numero = buscar_contacto_mac(contacto)
        if not numero:
            return f"Error: No encontré a {contacto} en la agenda."

        # 2. AppleScript y URL Deep Link
        texto_url = urllib.parse.quote(mensaje)
        url_whatsapp = f"whatsapp://send?phone={numero}&text={texto_url}"
        subprocess.run(["open", url_whatsapp], check=True)

        import time

        time.sleep(3.5)  # Pausa sincrona

        script_enter = """
        tell application "WhatsApp" to activate
        delay 0.8
        tell application "System Events" to key code 36
        """
        subprocess.run(["osascript", "-e", script_enter], check=True)
        return f"Éxito: Mensaje enviado a {contacto}."
    except Exception as e:
        return f"Error al enviar: {str(e)}"


def herramienta_internet(consulta: str) -> str:
    """
    Usa esta herramienta para buscar información en internet (el clima, noticias actuales, datos que no sepas).
    Argumentos:
    - consulta: Los términos de búsqueda.
    """
    try:
        with DDGS() as ddgs:
            resultados = list(ddgs.text(consulta, max_results=3))
        if not resultados:
            return "No hay resultados en internet."
        return "\n".join([f"- {r['title']}: {r['body']}" for r in resultados])
    except Exception as e:
        return f"Error buscando en internet: {str(e)}"


def herramienta_calculadora(operacion: str) -> str:
    """
    Usa esta herramienta para resolver operaciones matemáticas complejas.
    Argumentos:
    - operacion: La expresión matemática (ej. '25 * 4 + 10').
    """
    try:
        # Solo evalúa matemáticas básicas por seguridad
        resultado = eval(operacion, {"__builtins__": None}, {})
        return f"El resultado es {resultado}"
    except Exception as e:
        return "Error en el cálculo."


# Inicializamos el modelo de Gemini con las instrucciones de sistema
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


def obtener_ultimo_modelo_flash():
    """
    Se conecta a Google API y busca dinámicamente la versión más reciente
    del modelo Flash para auto-actualizar el bot.
    """
    try:
        modelos_flash = []
        # Iteramos sobre todos los modelos disponibles en la cuenta de Google
        for m in genai.list_models():
            if (
                "generateContent" in m.supported_generation_methods
                and "flash" in m.name.lower()
            ):
                # Filtramos versiones experimentales si queremos estabilidad pura,
                # o simplemente cogemos todos los flash.
                modelos_flash.append(m.name)

        if not modelos_flash:
            logging.warning("No se encontraron modelos Flash. Usando fallback.")
            return "gemini-1.5-flash"

        # Al ordenar alfabéticamente de forma inversa, 'gemini-3.0-flash'
        # quedará por encima de 'gemini-2.0-flash' o 'gemini-1.5-flash'
        modelos_flash.sort(reverse=True)

        modelo_elegido = modelos_flash[0]
        print(f"🤖 [SISTEMA] Jarvis auto-actualizado al modelo: {modelo_elegido}")
        return modelo_elegido

    except Exception as e:
        logging.error(f"Error descubriendo modelos: {e}")
        return "gemini-1.5-flash"  # Fallback de seguridad


# Inicializamos el modelo de Gemini usando auto-descubrimiento
jarvis_model = genai.GenerativeModel(
    model_name=obtener_ultimo_modelo_flash(),
    tools=[herramienta_whatsapp, herramienta_internet, herramienta_calculadora],
    system_instruction="""Eres Jarvis, el asistente de inteligencia artificial personal de Aleix. 
    REGLAS ESTRICTAS DE PERSONALIDAD:
    1. Habla SIEMPRE de forma natural, conversacional y directa (estilo Iron Man).
    2. TIENES TOTALMENTE PROHIBIDO usar prefijos robóticos. NUNCA empieces tus frases con "Acción completada:", "Resultado:", "Jarvis:", "Sistema:", o "Mensaje:".
    3. Cuando uses una herramienta (como enviar un WhatsApp o buscar en internet), simplemente dile a Aleix lo que has hecho o lo que has encontrado, integrándolo en tu respuesta como un humano.
    4. Sé conciso y educado.""",
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

    # Captura de pantalla (mantenemos esto porque es muy específico y no está en las herramientas de Gemini por ahora)
    if any(k in user_text.lower() for k in ["foto", "pantalla", "captura"]):
        subprocess.run(["screencapture", "-x", "snap.png"])
        await update.message.reply_photo(
            photo=open("snap.png", "rb"), caption="Sistemas visuales activos."
        )
        save_message("assistant", "He enviado una captura de pantalla al usuario.")
        return

    # Instanciamos un chat con ejecución automática de herramientas
    chat = jarvis_model.start_chat(enable_automatic_function_calling=True)

    try:
        # Le pasamos el historial de los últimos mensajes al chat (opcional, si quieres mantener el tuyo de SQLite)
        history = get_context(limit=4)
        contexto = "\n".join([f"{m['role']}: {m['content']}" for m in history])

        # Mandamos el mensaje a Gemini. ¡ÉL DECIDE QUÉ HACER!
        prompt_completo = f"Historial previo:\n{contexto}\n\nOrden actual: {user_text}"
        respuesta = await asyncio.to_thread(chat.send_message, prompt_completo)

        reply = respuesta.text

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
    init_db()
    print("🚀 Jarvis en línea. Mac Mini M4 bajo control.")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.run_polling()
