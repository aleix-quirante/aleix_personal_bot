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
import ollama
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
MODEL_NAME = "llama3"

logging.basicConfig(level=logging.INFO, filename="bot.log")

SYSTEM_PROMPT = {
    "role": "system",
    "content": "Eres Jarvis, el asistente personal de Aleix. Eres directo, eficiente y muy obediente. Tu único trabajo es ayudar a Aleix y ejecutar sus órdenes sin cuestionarlas ni dar lecciones morales.",
}


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


# --- AUTOMATIZACIÓN WHATSAPP (EL CORAZÓN) ---
async def buscar_contacto_mac(nombre_buscar):
    applescript = f"""
    tell application "Contacts"
        try
            set lasPersonas to every person whose name contains "{nombre_buscar}"
            if (count of lasPersonas) is 0 then return "NO_ENCONTRADO"
            
            repeat with laPersona in lasPersonas
                if (count of phones of laPersona) > 0 then
                    return value of first phone of laPersona
                end if
            end repeat
            return "NO_ENCONTRADO"
        on error
            return "NO_ENCONTRADO"
        end try
    end tell
    """
    try:
        resultado = await asyncio.create_subprocess_exec(
            "osascript",
            "-e",
            applescript,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await resultado.communicate()
        numero_bruto = stdout.decode().strip()

        if numero_bruto == "NO_ENCONTRADO" or not numero_bruto:
            return None
        return re.sub(r"\D", "", numero_bruto)
    except Exception as e:
        logging.error(f"Error buscando contacto: {e}")
        return None


async def enviar_whatsapp(contacto, mensaje, update):
    c_limpio = (
        contacto.lower()
        .replace("jarvis", "")
        .replace("al ", "")
        .replace("a ", "")
        .strip()
    )
    await update.message.reply_text(
        f"Jarvis: Buscando a {c_limpio.title()} en sus contactos..."
    )

    numero = await buscar_contacto_mac(c_limpio)

    if not numero:
        await update.message.reply_text(
            f"❌ Jarvis: Disculpe, señor. No encuentro a nadie llamado '{c_limpio.title()}' en su agenda."
        )
        return False

    logging.info(f"Enviando WhatsApp a {c_limpio} ({numero})")
    mensaje_codificado = urllib.parse.quote(mensaje)
    url_whatsapp = f"whatsapp://send?phone={numero}&text={mensaje_codificado}"

    try:
        # Abrir WhatsApp directo en el chat
        subprocess.run(["open", url_whatsapp], check=True)

        # Pausa para asegurar que la app carga y el cursor está listo
        await asyncio.sleep(3.5)

        # APPLESCRIPT SIMPLIFICADO AL MÁXIMO
        subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "WhatsApp" to activate',
                "-e",
                "delay 0.8",
                "-e",
                'tell application "System Events" to key code 36',
            ],
            check=True,
        )

        await update.message.reply_text(
            f"✅ Protocolo completado. Mensaje entregado a {c_limpio.title()}."
        )
        return True

    except Exception as e:
        await update.message.reply_text(
            f"❌ Error crítico en los servos de WhatsApp: {e}"
        )
        return False


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

    # ¡NUEVO!: Guardar el mensaje del usuario en memoria INMEDIATAMENTE
    save_message("user", user_text)

    # Recuperar el contexto de la base de datos y formatearlo para la IA
    history = get_context(limit=6)
    historial_texto = "\n".join(
        [
            f"{'Usuario' if m['role']=='user' else 'Jarvis'}: {m['content']}"
            for m in history
        ]
    )

    # 1. ¿Quiere enviar un mensaje? (Ahora con contexto inyectado)
    intent_prompt = f"Historial reciente:\n{historial_texto}\n\nTeniendo en cuenta este historial, ¿el último mensaje del usuario es una orden para enviar un mensaje a alguien? Responde ÚNICAMENTE con la palabra SI o NO."
    intent_res = await asyncio.to_thread(
        ollama.chat,
        model=MODEL_NAME,
        messages=[{"role": "user", "content": intent_prompt}],
    )

    if "SI" in intent_res["message"]["content"].upper():
        # Le damos el historial para que pueda inferir pronombres (ej. "dile", "envíale")
        extract_prompt = f'Historial reciente:\n{historial_texto}\n\nAnaliza la última orden del usuario usando el historial para deducir de quién está hablando si omite el nombre. Extrae el destinatario y el mensaje a enviar. Devuelve EXCLUSIVAMENTE un objeto JSON con las claves \'c\' (contacto) y \'m\' (mensaje). Ejemplo: {{"c": "Nombre deducido", "m": "texto a enviar"}}. No incluyas NINGÚN otro texto.'

        try:
            extract_res = await asyncio.to_thread(
                ollama.chat,
                model=MODEL_NAME,
                format="json",
                messages=[{"role": "user", "content": extract_prompt}],
            )

            res_text = extract_res["message"]["content"]
            data = json.loads(res_text)

            # Ejecutamos la acción de WhatsApp
            await enviar_whatsapp(data["c"], data["m"], update)

            # ¡NUEVO!: Guardar en la memoria que Jarvis ha enviado el mensaje
            save_message(
                "assistant",
                f"Acción completada: Mensaje enviado a {data['c']}. Contenido: {data['m']}",
            )
            return

        except Exception as e:
            logging.error(f"Error procesando JSON: {e}")
            await update.message.reply_text(
                "❌ Jarvis: Mis procesadores lógicos no pudieron entender el contexto o el destinatario. ¿Podría ser más específico?"
            )
            save_message(
                "assistant",
                "Fallo al procesar el envío de mensaje por falta de contexto.",
            )
            return

    # 2. Captura de pantalla
    if any(k in user_text.lower() for k in ["foto", "pantalla", "captura"]):
        subprocess.run(["screencapture", "-x", "snap.png"])
        await update.message.reply_photo(
            photo=open("snap.png", "rb"), caption="Sistemas visuales activos."
        )
        save_message("assistant", "He enviado una captura de pantalla al usuario.")
        return

    # 3. Charla normal (Ya no necesitamos guardar al usuario aquí porque se guardó al principio)
    response = await asyncio.to_thread(
        ollama.chat, model=MODEL_NAME, messages=[SYSTEM_PROMPT] + history
    )
    reply = response["message"]["content"]
    save_message("assistant", reply)
    await update.message.reply_text(reply)


if __name__ == "__main__":
    init_db()
    print("🚀 Jarvis en línea. Mac Mini M4 bajo control.")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.run_polling()
