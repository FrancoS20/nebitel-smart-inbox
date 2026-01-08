import os
import logging
import json
import requests
from fastapi import FastAPI, Request, HTTPException
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

#  IMPORTAMOS TU CEREBRO 
import cerebro  

# Configuración Inicial
load_dotenv()
app = FastAPI()

# Configuración de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Variables de Entorno
TOKEN = os.getenv("META_TOKEN")
VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN")
PHONE_NUMBER_ID = os.getenv("META_PHONE_ID")
DB_URL = os.getenv("DATABASE_URL")

# Configuración del Engine de Base de Datos (Neon Tech / PostgreSQL)
# Configuramos el pool para manejar desconexiones en serverless
try:
    engine = create_engine(
        DB_URL,
        pool_size=5,
        max_overflow=10,
        pool_recycle=1800
    )
    logger.info("✅ Engine de Base de Datos configurado correctamente")
except Exception as e:
    logger.critical(f"❌ Error fatal configurando DB: {e}")

#  FUNCIÓN AUXILIAR PARA ENVIAR WHATSAPP 
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
            logger.error(f"⚠️ Error enviando mensaje a Meta: {response.text}")
    except Exception as e:
        logger.error(f"❌ Falló la petición HTTP de envío: {e}")

# RUTA 1: VERIFICACIÓN (GET) 
@app.get("/webhook")
async def verify_webhook(request: Request):
    """Verificación de Meta"""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("META_VERIFY_TOKEN") 
    challenge = request.query_params.get("hub.challenge")

    # Nota: Meta suele enviar 'hub.verify_token', revisar si .env usa META_VERIFY_TOKEN
    verify_token_env = os.getenv("META_VERIFY_TOKEN")

    if mode and token:
        if mode == "subscribe" and token == verify_token_env:
            logger.info("✅ Webhook verificado.")
            return int(challenge)
        else:
            raise HTTPException(status_code=403, detail="Token de verificación incorrecto")
    return {"status": "error", "message": "Faltan parámetros"}

# RUTA 2: RECEPCIÓN DE MENSAJES (POST)
@app.post("/webhook")
async def receive_message(request: Request):
    """Recepción y Procesamiento de Mensajes"""
    try:
        body = await request.json()
        
        # Navegamos el JSON de WhatsApp
        entry = body.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if messages:
            msg = messages[0]
            
            # Datos del remitente
            wa_number = msg.get("from")
            name = value.get("contacts", [{}])[0].get("profile", {}).get("name", "Cliente")
            msg_type = msg.get("type")
            
            # Extraemos contenido
            text_body = ""
            if msg_type == "text":
                text_body = msg.get("text", {}).get("body", "")
            else:
                text_body = f"[{msg_type} recibido - Multimedia no soportado aún]"
            
            logger.info(f"📩 Mensaje de {name} ({wa_number}): {text_body}")

            # --- INICIO BLOQUE DE BASE DE DATOS ---
            try:
                with engine.connect() as conn:
                    
                    # 1. Upsert Contacto (Asegurar que existe el usuario)
                    sql_contact = text("""
                        INSERT INTO contacts (client_id, name, platform, last_activity) 
                        VALUES (:uid, :name, 'whatsapp', CURRENT_TIMESTAMP)
                        ON CONFLICT (client_id) DO UPDATE 
                        SET name = :name, last_activity = CURRENT_TIMESTAMP
                    """)
                    conn.execute(sql_contact, {"uid": wa_number, "name": name})
                    
                    # 2. LEER HISTORIAL (¡ANTES de guardar el nuevo!) ⏳
                    # Esto es clave para la MEMORIA TEMPORAL.
                    # Traemos 'created_at' para calcular tiempos.
                    sql_history = text("""
                        SELECT sender_type, message_text, created_at 
                        FROM messages 
                        WHERE contact_id = :uid 
                        ORDER BY id DESC 
                        LIMIT 6
                    """)
                    history_result = conn.execute(sql_history, {"uid": wa_number}).fetchall()
                    
                    # Formateamos historial para el Cerebro
                    historial_chat = []
                    for row in history_result:
                        role = "assistant" if row[0] == 'bot' else "user"
                        content = row[1]
                        fecha = row[2] # Timestamp real de la base de datos
                        
                        historial_chat.append({
                            "role": role, 
                            "content": content, 
                            "timestamp": fecha
                        })
                    
                    # Lo damos vuelta para que sea cronológico (Viejo -> Nuevo)
                    historial_chat = historial_chat[::-1] 
                    
                    # 3. AHORA SÍ: Guardar el Mensaje Nuevo (Inbound) 💾
                    sql_msg_in = text("""
                        INSERT INTO messages (contact_id, message_text, direction, sender_type, status)
                        VALUES (:uid, :body, 'inbound', 'user', 'received')
                    """)
                    conn.execute(sql_msg_in, {"uid": wa_number, "body": text_body})
                    
                    # Confirmamos la escritura en DB
                    conn.commit()
            
            except Exception as db_err:
                logger.error(f"❌ Error en Base de Datos: {db_err}")
                historial_chat = [] # Si falla la DB, seguimos sin memoria

            # --- FIN BLOQUE DB ---

            # --- CEREBRO TOMA EL CONTROL 🧠 ---
            # Le pasamos el texto nuevo Y el historial (que NO incluye el texto nuevo todavía en la lista)
            # Esto permite comparar tiempos correctamente.
            respuesta_bot = cerebro.procesar_mensaje(text_body, historial_chat)

            # PARCHE ARGENTINA 🇦🇷
            destinatario_final = wa_number
            if wa_number.startswith("549"):
                destinatario_final = wa_number.replace("549", "54", 1)

            # ENVIAR RESPUESTA A WHATSAPP
            await enviar_mensaje_whatsapp(destinatario_final, respuesta_bot)

            # GUARDAR RESPUESTA DEL BOT (Outbound)
            try:
                with engine.connect() as conn:
                    sql_msg_out = text("""
                        INSERT INTO messages (contact_id, message_text, direction, sender_type, status)
                        VALUES (:uid, :body, 'outbound', 'bot', 'sent')
                    """)
                    conn.execute(sql_msg_out, {"uid": wa_number, "body": respuesta_bot})
                    conn.commit()
            except Exception as e:
                logger.error(f"❌ Error guardando respuesta del bot: {e}")
            
        return {"status": "ok"}

    except Exception as e:
        logger.error(f"❌ Error procesando webhook general: {e}")
        return {"status": "ok"}