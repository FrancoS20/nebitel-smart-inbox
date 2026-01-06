import os
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from mensajeria import enviar_mensaje_whatsapp

# --- CONFIGURACIÓN ---
load_dotenv()
TOKEN_VERIFICACION = os.getenv("META_VERIFY_TOKEN")
DB_URL = os.getenv("DATABASE_URL")

# Configurar Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Conectar a la Base de Datos
engine = create_engine(DB_URL)
app = FastAPI()

# --- RUTAS ---
@app.get("/")
async def home():
    return {"status": "Nebitel Smart Inbox V2 Activo 🚀"}

# 1. VERIFICACIÓN DE META
@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == TOKEN_VERIFICACION:
        logger.info("✅ Meta golpeó la puerta y la clave es correcta.")
        challenge = params.get("hub.challenge")
        return PlainTextResponse(content=challenge, status_code=200)
    
    logger.error("❌ Clave incorrecta o intento de acceso no autorizado")
    raise HTTPException(status_code=403, detail="Token inválido")

# 2. RECEPCIÓN DE MENSAJES
@app.post("/webhook")
async def receive_message(request: Request):
    data = await request.json()
    
    try:
        entry = data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        
        if "messages" in value:
            message_data = value["messages"][0]
            contact_data = value["contacts"][0]
            
            # Datos del remitente
            client_id = contact_data["wa_id"]           
            name = contact_data["profile"]["name"]      
            platform = "whatsapp"
            sender_type = 'user'
            
            # Datos del mensaje
            msg_type = message_data.get("type")
            text_body = ""
            
            if msg_type == "text":
                text_body = message_data["text"]["body"]
            else:
                text_body = f"[{msg_type.upper()}] Archivo recibido"

            logger.info(f"📩 Mensaje de {name} ({client_id}): {text_body}")

            # --- GUARDAR EN BASE DE DATOS ---
            with engine.connect() as connection:
                # A. Guardar Contacto
                sql_contact = text("""
                    INSERT INTO contacts (client_id, name, platform, last_activity)
                    VALUES (:id, :name, :plat, NOW())
                    ON CONFLICT (client_id) 
                    DO UPDATE SET name = :name, last_activity = NOW()
                """)
                connection.execute(sql_contact, {"id": client_id, "name": name, "plat": platform})
                
                # B. Guardar Mensaje Entrante
                sql_msg = text("""
                    INSERT INTO messages (contact_id, message_text, media_type, direction, sender_type, status)
                    VALUES (:id, :body, :type, 'inbound', 'user', 'received')
                """)
                connection.execute(sql_msg, {"id": client_id, "body": text_body, "type": msg_type})
                connection.commit()
                logger.info("💾 Guardado correctamente en DB Nueva.")
                
                # --- 🤖 RESPUESTA AUTOMÁTICA ---
                if sender_type == 'user': 
                    logger.info("🗣️ Nebitel intentando responder...")
                    respuesta = f"🤖 Recibí tu mensaje: '{text_body}'. (Guardado en DB)"
                
                    # === PARCHE ARGENTINA (AQUÍ ESTÁ LA MAGIA) ===
                    # Si el número empieza con 549, le sacamos el 9 para engañar a Meta
                    destinatario_final = client_id
                    if client_id.startswith("549"):
                        destinatario_final = client_id.replace("549", "54", 1)
                        logger.info(f"🇦🇷 Parche activado: Cambiando {client_id} por {destinatario_final}")
                    # ============================================

                    # Enviamos al destinatario corregido
                    await enviar_mensaje_whatsapp(destinatario_final, respuesta)
                    
                    # Guardamos la respuesta
                    sql_outbound = text("""
                        INSERT INTO messages (contact_id, message_text, direction, sender_type, status)
                        VALUES (:id, :body, 'outbound', 'bot', 'sent')
                    """)
                    connection.execute(sql_outbound, {"id": client_id, "body": respuesta})
                    connection.commit()
                    logger.info("💾 Respuesta del Bot guardada en DB.")

    except Exception as e:
        logger.exception(f"⚠️ Error procesando mensaje: {e}")
        return {"status": "error_handled"}

    return {"status": "received"}