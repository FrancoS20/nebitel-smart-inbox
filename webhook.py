import os
import logging
import json
import requests
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
import cerebro
from datetime import datetime

# CONFIGURACIÓN 
load_dotenv()
VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN")
META_TOKEN = os.getenv("META_TOKEN")
PHONE_NUMBER_ID = os.getenv("META_PHONE_ID")
DB_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("webhook")
app = FastAPI()

if not DB_URL: logger.error("❌ Falta DATABASE_URL"); exit()
engine = create_engine(DB_URL)

# --- FUNCIÓN 1: ENVIAR A WHATSAPP ---
def enviar_mensaje_whatsapp_sync(numero, texto):
    """Versión síncrona para correr en background"""
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {META_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": numero, "type": "text", "text": {"body": texto}}
    try:
        requests.post(url, headers=headers, json=data)
    except Exception as e:
        logger.error(f"⚠️ Error enviando a Meta: {e}")

# --- FUNCIÓN 2: LÓGICA PESADA (BASE DE DATOS + IA) ---
def procesar_notificacion_fondo(data):
    """
    Esta función corre DESPUÉS de responderle a Meta.
    Acá nos tomamos todo el tiempo del mundo.
    """
    try:
        value = data.get('entry', [])[0].get('changes', [])[0].get('value', {})
        messages = value.get('messages', [])
        
        if not messages: return

        msg = messages[0]
        wa_number = msg['from']
        
        # Filtrar mensajes de estado (leído, entregado, etc) que no tienen texto
        if 'text' not in msg:
            logger.info(f"Ignorando actualización de estado de {wa_number}")
            return

        text_body = msg['text']['body']
        contact_name = value.get('contacts', [])[0].get("profile", {}).get("name", "Cliente")

        logger.info(f"📩 Procesando fondo: {wa_number} dice: {text_body}")

        # 1. GUARDAR ENTRADA
        try:
            with engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO contacts (client_id, name, created_at, bot_mode) 
                    VALUES (:uid, :name, CURRENT_TIMESTAMP, TRUE)
                    ON CONFLICT (client_id) DO UPDATE SET name = :name
                """), {"uid": wa_number, "name": contact_name})
                
                # Chequeamos duplicados de mensaje para estar seguros (Opcional, pero buena práctica)
                # Por ahora guardamos directo
                conn.execute(text("""
                    INSERT INTO messages (contact_id, message_text, direction, sender_type, status, created_at)
                    VALUES (:uid, :body, 'inbound', 'user', 'received', CURRENT_TIMESTAMP)
                """), {"uid": wa_number, "body": text_body})
                conn.commit()
        except Exception as e:
            logger.error(f"❌ Error DB Inbound: {e}")
            return

        # 2. CHEQUEO BOT MODE
        is_bot_active = True
        try:
            with engine.connect() as conn:
                res = conn.execute(text("SELECT bot_mode FROM contacts WHERE client_id=:uid"), {"uid": wa_number}).fetchone()
                if res is not None: is_bot_active = res[0]
        except: pass

        if not is_bot_active:
            logger.info(f"🛑 Bot apagado para {wa_number}. Fin.")
            return

        logger.info(f"🟢 Bot activo. Llamando a Gemini...")

        # 3. CEREBRO (IA)
        historial = []
        try:
            with engine.connect() as conn:
                rows = conn.execute(text("SELECT sender_type, message_text FROM messages WHERE contact_id=:uid ORDER BY id DESC LIMIT 6"), {"uid": wa_number}).fetchall()
                for r in reversed(rows):
                    historial.append({"role": "user" if r[0]=='user' else "model", "content": r[1]})
        except: pass

        # LLAMADA A GEMINI (Aquí es donde antes se trababa y Meta reenviaba)
        resultado = cerebro.procesar_mensaje(text_body, historial)
        rta = resultado.get("respuesta", "Error")

        # 4. RESPONDER
        dest = wa_number.replace("549", "54", 1) if wa_number.startswith("549") else wa_number
        enviar_mensaje_whatsapp_sync(dest, rta)

        # 5. GUARDAR SALIDA
        try:
            with engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO messages (contact_id, message_text, direction, sender_type, status, priority_score, intent, conversation_status, created_at)
                    VALUES (:uid, :body, 'outbound', 'bot', 'sent', :prio, :intent, :est, CURRENT_TIMESTAMP)
                """), {"uid": wa_number, "body": rta, "prio": resultado.get("prioridad",5), "intent": resultado.get("intencion","Gral"), "est": resultado.get("status","open")})
                conn.commit()
        except Exception as e:
            logger.error(f"❌ Error DB Outbound: {e}")

    except Exception as e:
        logger.error(f"🔥 Error en background: {e}")

# --- RUTAS ---

@app.get("/webhook")
async def verify_webhook(request: Request):
    if request.query_params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(request.query_params.get("hub.challenge"))
    raise HTTPException(status_code=403, detail="Token inválido")

@app.post("/webhook")
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    """
    ENDPOINT RÁPIDO: Solo recibe, devuelve 200 OK y manda a trabajar al fondo.
    """
    try:
        data = await request.json()
        # ¡MAGIA! Agregamos la tarea a la cola y respondemos YA.
        background_tasks.add_task(procesar_notificacion_fondo, data)
        return {"status": "received"} # Meta recibe esto en milisegundos y se queda feliz.
    except Exception as e:
        logger.error(f"Error recibiendo: {e}")
        return {"status": "error"}