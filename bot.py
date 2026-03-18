import os
import re
import logging
import asyncio
import json
import sqlite3
import subprocess
from dotenv import load_dotenv
import ollama
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from duckduckgo_search import DDGS

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
USER_ID = int(os.getenv("USER_ID", "0"))
DB_PATH = os.getenv("DB_PATH", "/Volumes/USB/jarvis_memory.db")
MODEL_NAME = "llama3"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot.log'
)

SYSTEM_PROMPT = {
    'role': 'system', 
    'content': 'Eres Jarvis, el asistente personal de Aleix. Responde SIEMPRE en español. Tu tono es profesional, eficiente, muy culto y con el ingenio británico de Paul Bettany en Iron Man. Sabes que corres localmente en un Mac Mini M4.'
}

def init_db():
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir, exist_ok=True)
        except Exception as e:
            logging.error(f"No se pudo crear el directorio de la BD: {e}")
            
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY,
                role TEXT,
                content TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Error inicializando BD: {e}")

def save_message(role, content):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO messages (role, content) VALUES (?, ?)', (role, content))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Error al guardar mensaje en BD: {e}")

def get_context(limit=15):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT role, content FROM (
                SELECT role, content, id FROM messages ORDER BY id DESC LIMIT ?
            ) ORDER BY id ASC
        ''', (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [{'role': row[0], 'content': row[1]} for row in rows]
    except Exception as e:
        logging.error(f"Error al recuperar contexto de BD: {e}")
        return []

async def enviar_whatsapp(contacto, mensaje, update):
    logging.info(f"Iniciando envío de WhatsApp a {contacto}: {mensaje}")
    await update.message.reply_text(f"Jarvis: Localizando a {contacto} en el sistema...")
    
    script_locate = f"""
    tell application "WhatsApp" to activate
    delay 1
    tell application "System Events"
        tell process "WhatsApp"
            set frontmost to true
            key code 53 -- Escape
            delay 0.1
            key code 53
            delay 0.1
            key code 53
            delay 0.5
            keystroke "f" using command down
            delay 1
            keystroke "a" using command down
            key code 51 -- Borrar
            keystroke "{contacto}"
            delay 2
            key code 125 -- Flecha Abajo
            delay 0.5
            keystroke return
        end tell
    end tell
    """
    try:
        await asyncio.to_thread(subprocess.run, ["osascript", "-e", script_locate], check=True, capture_output=True, text=True)
        
        await update.message.reply_text("Jarvis: Escribiendo mensaje...")
        
        script_send = f"""
        tell application "System Events"
            tell process "WhatsApp"
                set frontmost to true
                keystroke "{mensaje}"
                delay 0.5
                keystroke return
            end tell
        end tell
        """
        await asyncio.to_thread(subprocess.run, ["osascript", "-e", script_send], check=True, capture_output=True, text=True)
        
        await update.message.reply_text("Jarvis: Protocolo finalizado.")
        return True
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        logging.error(f"Error al enviar WhatsApp mediante UI: {error_msg}")
        await update.message.reply_text(f"Jarvis: Error de sistema detectado. Detalle técnico: {error_msg}")
        return False

async def check_user(update: Update) -> bool:
    user_id = update.effective_user.id
    if user_id != USER_ID:
        logging.warning(f"Intento de acceso de ID no autorizado: {user_id}")
        return False
    return True

def web_search(query):
    try:
        results = DDGS().text(query, max_results=3)
        context = ""
        for i, res in enumerate(results, 1):
            context += f"[{i}] {res['title']}: {res['body']} (Fuente: {res['href']})\n\n"
        return context if context else "No se encontraron resultados relevantes."
    except Exception as e:
        logging.error(f"Error en búsqueda web: {e}")
        return f"Ocurrió un error al buscar en la red: {e}"

async def buscar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_user(update): return
    
    if not context.args:
        await update.message.reply_text("Por favor, señor, indíqueme qué desea que busque. Ejemplo: /buscar clima en Madrid")
        return
        
    query = " ".join(context.args)
    temp_message = await update.message.reply_text(f"🔍 Conectando a la red global para buscar: {query}...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    try:
        search_results = await asyncio.to_thread(web_search, query)
        
        prompt = f"Aquí tienes información actualizada de internet sobre '{query}':\n\n{search_results}\n\nBasándote estrictamente en esta información, responde de forma concisa al usuario."
        messages = [
            SYSTEM_PROMPT,
            {'role': 'user', 'content': prompt}
        ]
        
        response = await asyncio.to_thread(
            ollama.chat,
            model=MODEL_NAME,
            messages=messages
        )
        
        bot_response = response['message']['content']
        
        save_message('user', f"/buscar {query}")
        save_message('assistant', bot_response)
        
        await temp_message.edit_text(bot_response)
        
    except Exception as e:
        logging.error(f"Error en comando buscar: {e}")
        await temp_message.edit_text("Mis disculpas, señor. Ha fallado mi enlace con la red global o mi procesamiento de los datos.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_user(update): return
    await update.message.reply_text("A sus órdenes, Aleix. Mis sistemas están operativos. Memoria inicializada en el Mac Mini M4. ¿En qué le puedo asistir?")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_user(update): return
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    user_message = update.message.text
    save_message('user', user_message)
    
    msg_lower = user_message.lower()
    if any(keyword in msg_lower for keyword in ["foto", "pantalla", "captura"]):
        await update.message.reply_text("Iniciando captura de pantalla de los sistemas principales, señor...")
        filepath = "snap.png"
        try:
            subprocess.run(["screencapture", "-x", filepath], check=True)
            with open(filepath, 'rb') as photo:
                await update.message.reply_photo(photo=photo, caption="Captura del sistema completada con éxito.")
            if os.path.exists(filepath):
                os.remove(filepath)
            return
        except Exception as e:
            logging.error(f"Error al tomar captura: {e}")
            await update.message.reply_text(f"Mis disculpas, señor. Ha ocurrido un error al intentar capturar la pantalla: {e}")
            return

    # NLP Router: Comprobar intención de enviar WhatsApp
    try:
        intent_prompt = f"Analiza: '{user_message}'. ¿El usuario está pidiendo enviar un mensaje, decir algo o comunicar algo a una persona? Si el usuario menciona a una persona y algo que quiere decirle, responde SI siempre. Responde solo SI o NO."
        intent_response = await asyncio.to_thread(
            ollama.chat,
            model=MODEL_NAME,
            messages=[{'role': 'user', 'content': intent_prompt}]
        )
        
        is_whatsapp = intent_response['message']['content'].strip().upper()
        
        if "SI" in is_whatsapp:
            extract_prompt = f"Extrae el destinatario y el mensaje de: '{user_message}'. \nREGLA DE ORO: 'Jarvis' es el nombre del ASISTENTE. NUNCA extraigas 'Jarvis' como contacto a menos que el usuario diga explícitamente 'envía un mensaje a mi contacto llamado Jarvis'. \nResponde solo JSON: {{\"c\": \"nombre_real\", \"m\": \"texto\"}}."
            extract_response = await asyncio.to_thread(
                ollama.chat,
                model=MODEL_NAME,
                messages=[{'role': 'user', 'content': extract_prompt}]
            )
            
            try:
                json_text = extract_response['message']['content']
                # Clean string in Python to find first '{' and last '}'
                start_idx = json_text.find('{')
                end_idx = json_text.rfind('}')
                if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
                    json_str = json_text[start_idx:end_idx+1]
                    data = json.loads(json_str)
                    contacto = data.get("c", "Desconocido")
                    mensaje = data.get("m", "")
                    
                    # Limpieza de Nombre
                    for palabra in ["Jarvis", "a la", "al", "a"]:
                        if contacto.lower().startswith(palabra.lower() + " "):
                            contacto = contacto[len(palabra)+1:].strip()
                            
                    if contacto.lower() == 'jarvis':
                        contacto = "Desconocido"
                    
                    # Ejecutar automatización UI con logs
                    success = await enviar_whatsapp(contacto, mensaje, update)
                        
                    if success:
                        save_message('assistant', f"Mensaje enviado a {contacto}: {mensaje}")
                    return
                else:
                    raise ValueError("No JSON object found in response")
            except Exception as e:
                logging.error(f"Error al decodificar JSON de WhatsApp: {e}")
                # Fallback al chat normal si falla el JSON
    except Exception as e:
        logging.error(f"Error en NLP Router de WhatsApp: {e}")
        # Continuar con el chat normal si hay error en el router
        
    history = get_context(limit=15)
    
    try:
        # Construir mensajes con el prompt del sistema + historial
        messages = [SYSTEM_PROMPT] + history
        
        response = await asyncio.to_thread(
            ollama.chat,
            model=MODEL_NAME,
            messages=messages
        )
        
        bot_response = response['message']['content']
        
        save_message('assistant', bot_response)
        
        await update.message.reply_text(bot_response)
    except Exception as e:
        logging.error(f"Error en Ollama: {e}")
        await update.message.reply_text("Mis disculpas, señor. Parece que mi motor cognitivo principal ha sufrido un breve fallo.")

if __name__ == '__main__':
    init_db()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("buscar", buscar_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🚀 Servidor Jarvis arrancando con memoria conectada a /Volumes/USB/jarvis_memory.db...")
    app.run_polling()
