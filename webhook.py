import os
import logging
import json
import requests
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# --- IMPORTAMOS TU NUEVO MÓDULO ---
import cerebro  # <--- Acá está la magia de la separación

# 1. Configuración Inicial
load_dotenv()
app = FastAPI()

# Configuración de Logs (Para ver colores en la terminal)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 2. Variables de Entorno (Desde el .env)
TOKEN = os.getenv("META_TOKEN")
VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN")
PHONE_NUMBER_ID = os.getenv("META_PHONE_ID")
DB_URL = os.getenv("DATABASE_URL")

# 3. Conexión a Base de Datos (Neon Postgres)
try:
    engine = create_engine(DB_URL)
    connection = engine.connect()
    logger.info("✅ Conexión a Base de Datos EXITOSA")
except Exception as e:
    logger.error(f"❌ Error conectando a la DB: {e}")

# --- FUNCIÓN AUXILIAR PARA ENVIAR WHATSAPP ---
async def enviar_mensaje_whatsapp(numero, texto):
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {"body": texto}
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            logger.info(f"📤 Mensaje enviado a {numero}")
        else:
            logger.error(f"⚠️ Error enviando mensaje: {response.text}")
    except Exception as e:
        logger.error(f"❌ Falló el envío: {e}")

# --- RUTA 1: VERIFICACIÓN (GET) ---
@app.get("/webhook")
async def verify_webhook(request: Request):
    """Meta usa esto para verificar que el servidor es tuyo"""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("META_VERIFY_TOKEN")
    challenge = request.query_params.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            logger.info("✅ Webhook verificado correctamente.")
            return int(challenge)
        else:
            raise HTTPException(status_code=403, detail="Token incorrecto")

# --- RUTA 2: RECEPCIÓN DE MENSAJES (POST) ---
@app.post("/webhook")
async def receive_message(request: Request):
    """Acá llegan los mensajes de los clientes"""
    try:
        body = await request.json()
        
        # Navegamos el JSON complejo de WhatsApp
        entry = body.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if messages:
            msg = messages[0]
            
            # Datos del remitente
            wa_number = msg.get("from")  # El número (ej: 549343...)
            name = value.get("contacts", [{}])[0].get("profile", {}).get("name", "Desconocido")
            msg_type = msg.get("type")
            
            # Extraemos el contenido
            text_body = ""
            if msg_type == "text":
                text_body = msg.get("text", {}).get("body", "")
            elif msg_type == "image":
                text_body = "Imagen recibida (Multimedia)"
            
            logger.info(f"📩 Mensaje de {name} ({wa_number}): {text_body}")

            # --- 1. GUARDAMOS EN BASE DE DATOS (ENTRADA) ---
            
            # A. Guardar/Actualizar Contacto
            # CORRECCIÓN: Usamos 'client_id' y agregamos 'platform' = 'whatsapp'
            sql_contact = text("""
                INSERT INTO contacts (client_id, name, platform, last_activity) 
                VALUES (:uid, :name, 'whatsapp', CURRENT_TIMESTAMP)
                ON CONFLICT (client_id) DO UPDATE 
                SET name = :name, last_activity = CURRENT_TIMESTAMP
            """)
            connection.execute(sql_contact, {"uid": wa_number, "name": name})
            
            # B. Guardar Mensaje Entrante
            # CORRECCIÓN: 'contact_id' debe coincidir con el 'client_id' de arriba
            sql_msg_in = text("""
                INSERT INTO messages (contact_id, message_text, direction, sender_type, status, priority_score)
                VALUES (:uid, :body, 'inbound', 'user', 'received', 0)
            """)
            connection.execute(sql_msg_in, {"uid": wa_number, "body": text_body})
            connection.commit()

            # --- 2. CEREBRO TOMA EL CONTROL 🧠 ---
            # Llamamos al archivo externo
            respuesta_bot = cerebro.procesar_mensaje(text_body)

            # --- 3. PARCHE ARGENTINA 🇦🇷 ---
            destinatario_final = wa_number
            if wa_number.startswith("549"):
                destinatario_final = wa_number.replace("549", "54", 1)

            # --- 4. ENVIAR RESPUESTA ---
            await enviar_mensaje_whatsapp(destinatario_final, respuesta_bot)

            # --- 5. GUARDAMOS EN BASE DE DATOS (SALIDA) ---
            sql_msg_out = text("""
                INSERT INTO messages (contact_id, message_text, direction, sender_type, status, priority_score)
                VALUES (:uid, :body, 'outbound', 'bot', 'sent', 0)
            """)
            connection.execute(sql_msg_out, {"uid": wa_number, "body": respuesta_bot})
            connection.commit()
            
        return {"status": "ok"}

    except Exception as e:
        logger.error(f"❌ Error procesando webhook: {e}")
        # Importante: Devolver 'ok' a Meta aunque falle nuestra DB para que no reintenten infinitamente
        return {"status": "ok"}