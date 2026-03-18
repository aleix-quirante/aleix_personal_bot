import os
import re
import logging
import asyncio
import json
import sqlite3
import subprocess
from datetime import datetime
from dotenv import load_dotenv
import ollama
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from duckduckgo_search import DDGS

load_dotenv()

# --- CONFIGURACIÓN ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
USER_ID = int(os.getenv("USER_ID", "0"))
DB_PATH = "/Volumes/USB/jarvis_memory.db" # Ruta directa al SSD
MODEL_NAME = "llama3"

logging.basicConfig(level=logging.INFO, filename='bot.log')

SYSTEM_PROMPT = {
    'role': 'system', 
    'content': 'Eres Jarvis, el asistente de Aleix. Eres culto y eficiente. Sabes que corres en un Mac Mini M4. IMPORTANTE: Tu nombre es Jarvis, si Aleix te pide enviar un mensaje a alguien, el destinatario NUNCA eres tú.'
}

# --- MEMORIA ---
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, role TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
    conn.close()

def save_message(role, content):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('INSERT INTO messages (role, content) VALUES (?, ?)', (role, content))
    conn.commit()
    conn.close()

def get_context(limit=15):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT role, content FROM (SELECT * FROM messages ORDER BY id DESC LIMIT ?) ORDER BY id ASC', (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [{'role': r, 'content': c} for r, c in rows]
    except: return []

# --- AUTOMATIZACIÓN WHATSAPP (EL CORAZÓN) ---
async def enviar_whatsapp(contacto, mensaje, update):
    await update.message.reply_text(f"Jarvis: Localizando a {contacto}...")
    
    # Limpiamos el nombre por si la IA se ha liado
    contacto_limpio = contacto.replace("Jarvis", "").replace("al ", "").replace("a ", "").strip()

    script_whatsapp = f"""
    tell application "WhatsApp" to activate
    delay 1
    tell application "System Events"
        tell process "WhatsApp"
            set frontmost to true
            key code 53 -- Esc para asegurar que no hay nada abierto
            delay 0.5
            keystroke "f" using command down -- Abrir buscador
            delay 0.5
            keystroke "a" using command down -- Seleccionar todo
            key code 51 -- Borrar
            delay 0.5
            keystroke "{contacto_limpio}"
            delay 3.0 -- TIEMPO PARA QUE WHATSAPP BUSQUE REALMENTE
            
            key code 125 -- FLECHA ABAJO: Crucial para salir del cuadro de texto
            delay 0.5
            key code 36 -- ENTER: Entrar al chat
            delay 1.5
            
            keystroke "{mensaje}"
            delay 0.5
            key code 36 -- ENTER: Enviar mensaje
        end tell
    end tell
    """
    try:
        # Usamos el binario con permisos (el que funcionó con la 'X')
        subprocess.run(["osascript", "-e", script_whatsapp], check=True)
        await update.message.reply_text(f"✅ Mensaje enviado a {contacto_limpio}, señor.")
        return True
    except:
        await update.message.reply_text("❌ Error en la interfaz de WhatsApp.")
        return False

# --- PROCESAMIENTO ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != USER_ID: return
    
    user_text = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    # 1. ¿Es WhatsApp?
    intent_prompt = f"Analiza: '{user_text}'. ¿Quiere enviar un mensaje a alguien? Responde solo SI o NO."
    intent_res = await asyncio.to_thread(ollama.chat, model=MODEL_NAME, messages=[{'role': 'user', 'content': intent_prompt}])
    
    if "SI" in intent_res['message']['content'].upper():
        extract_prompt = f"Extrae el nombre y el mensaje de: '{user_text}'. NUNCA uses 'Jarvis' como nombre. Responde solo JSON: {{\"c\": \"nombre\", \"m\": \"texto\"}}"
        extract_res = await asyncio.to_thread(ollama.chat, model=MODEL_NAME, messages=[{'role': 'user', 'content': extract_prompt}])
        
        try:
            # Limpieza de JSON ultra-robusta
            res_text = extract_res['message']['content']
            match = re.search(r'\{.*\}', res_text, re.DOTALL)
            if match:
                data = json.loads(match.group())
                await enviar_whatsapp(data['c'], data['m'], update)
                return
        except: pass

    # 2. Captura de pantalla
    if any(k in user_text.lower() for k in ["foto", "pantalla", "captura"]):
        subprocess.run(["screencapture", "-x", "snap.png"])
        await update.message.reply_photo(photo=open("snap.png", 'rb'), caption="Sistemas visuales activos.")
        return

    # 3. Charla normal
    save_message('user', user_text)
    history = get_context()
    response = await asyncio.to_thread(ollama.chat, model=MODEL_NAME, messages=[SYSTEM_PROMPT] + history)
    reply = response['message']['content']
    save_message('assistant', reply)
    await update.message.reply_text(reply)

if __name__ == '__main__':
    init_db()
    print("🚀 Jarvis en línea. Mac Mini M4 bajo control.")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.run_polling()