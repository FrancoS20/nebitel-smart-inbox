import os
import logging
import json
import requests
from fastapi import FastAPI, Request, HTTPException
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Importamos nuestro cerebro inteligente (ahora devuelve JSON)
import cerebro 

# --- CONFIGURACIÓN ---
load_dotenv()

# Credenciales y Tokens
VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN")
META_TOKEN = os.getenv("META_TOKEN")
PHONE_NUMBER_ID = os.getenv("META_PHONE_ID")
DB_URL = os.getenv("DATABASE_URL")

# Configuración de Logs (Para ver colores en la terminal)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("webhook")

app = FastAPI()

# Conexión a Base de Datos
if not DB_URL:
    logger.error("❌ Falta DATABASE_URL en el archivo .env")
    exit()
engine = create_engine(DB_URL)

# --- FUNCIÓN: ENVIAR MENSAJE A META ---
async def enviar_mensaje_whatsapp(numero, texto):
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {META_TOKEN}",
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
        response.raise_for_status()
        logger.info(f"📤 Mensaje enviado a {numero}")
    except requests.exceptions.RequestException as e:
        logger.error(f"⚠️ Error enviando mensaje a Meta: {e}")
        if response is not None:
             logger.error(f"Detalle Meta: {response.text}")

# --- RUTAS DEL SERVIDOR ---

@app.get("/")
async def root():
    return {"status": "Nebitel Bot Activo 🦅", "mode": "JSON Architecture"}

@app.get("/webhook")
async def verify_webhook(request: Request):
    """Verificación inicial de Meta"""
    hub_mode = request.query_params.get("hub.mode")
    hub_verify_token = request.query_params.get("hub.verify_token")
    hub_challenge = request.query_params.get("hub.challenge")

    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        logger.info("✅ Webhook verificado correctamente.")
        return int(hub_challenge)
    
    raise HTTPException(status_code=403, detail="Token inválido")

@app.post("/webhook")
async def receive_message(request: Request):
    """
    Núcleo del sistema: Recibe -> Guarda -> Piensa -> Clasifica -> Responde -> Guarda
    """
    try:
        data = await request.json()
        
        # Estructura típica de mensaje de WhatsApp
        entry = data.get('entry', [])[0]
        changes = entry.get('changes', [])[0]
        value = changes.get('value', {})
        messages = value.get('messages', [])

        if messages:
            msg = messages[0]
            wa_number = msg['from']     # Número del cliente
            text_body = msg['text']['body'] # Texto que escribió
            
            logger.info(f"📩 Mensaje de {wa_number}: {text_body}")

            # 1. GUARDAR MENSAJE ENTRANTE (INBOUND)
            try:
                with engine.connect() as conn:
                    # Nos aseguramos que el contacto exista (Upsert simple)
                    conn.execute(text("""
                        INSERT INTO contacts (client_id, name, created_at) 
                        VALUES (:uid, 'Cliente Nuevo', CURRENT_TIMESTAMP)
                        ON CONFLICT (client_id) DO NOTHING
                    """), {"uid": wa_number})
                    
                    # Guardamos el mensaje del usuario
                    conn.execute(text("""
                        INSERT INTO messages (contact_id, message_text, direction, sender_type, status, created_at)
                        VALUES (:uid, :body, 'inbound', 'user', 'received', CURRENT_TIMESTAMP)
                    """), {"uid": wa_number, "body": text_body})
                    conn.commit()
            except Exception as e:
                logger.error(f"❌ Error DB (Entrante): {e}")

            # 2. RECUPERAR HISTORIAL (MEMORIA)
            historial_chat = []
            try:
                with engine.connect() as conn:
                    result = conn.execute(text("""
                        SELECT sender_type, message_text, created_at 
                        FROM messages 
                        WHERE contact_id = :uid 
                        ORDER BY id DESC LIMIT 6
                    """), {"uid": wa_number})
                    
                    # Convertimos a formato para la IA (orden cronológico)
                    msgs_db = result.fetchall()
                    for fila in reversed(msgs_db):
                        role = "user" if fila[0] == 'user' else "model"
                        historial_chat.append({
                            "role": role, 
                            "content": fila[1],
                            "timestamp": fila[2] # Guardamos la fecha para el cálculo de tiempo
                        })
            except Exception as e:
                logger.error(f"⚠️ Error leyendo historial: {e}")

            # 3. CEREBRO TOMA EL CONTROL 🧠 (Ahora devuelve JSON)
            resultado_ia = cerebro.procesar_mensaje(text_body, historial_chat)
            
            # 4. DESEMPAQUETAR DATOS
            # Usamos .get() para evitar errores si algo falta
            respuesta_texto = resultado_ia.get("respuesta", "Disculpá, tuve un error interno.")
            intencion = resultado_ia.get("intencion", "General")
            prioridad = resultado_ia.get("prioridad", 5)
            estado_charla = resultado_ia.get("status", "open")

            logger.info(f"🤖 IA Responde: {respuesta_texto[:30]}... | Intención: {intencion} | Prio: {prioridad}")

            # 5. PARCHE ARGENTINA (Para enviar)
            destinatario = wa_number
            if wa_number.startswith("549"):
                destinatario = wa_number.replace("549", "54", 1)

            # 6. ENVIAR SOLO TEXTO A WHATSAPP
            await enviar_mensaje_whatsapp(destinatario, respuesta_texto)

            # 7. GUARDAR RESPUESTA Y METADATOS EN DB (OUTBOUND)
            try:
                with engine.connect() as conn:
                    # Aquí guardamos los datos nuevos: intent, priority_score, conversation_status
                    sql_out = text("""
                        INSERT INTO messages 
                        (contact_id, message_text, direction, sender_type, status, priority_score, intent, conversation_status, created_at)
                        VALUES (:uid, :body, 'outbound', 'bot', 'sent', :prio, :intent, :estado, CURRENT_TIMESTAMP)
                    """)
                    conn.execute(sql_out, {
                        "uid": wa_number, 
                        "body": respuesta_texto,
                        "prio": prioridad,
                        "intent": intencion,
                        "estado": estado_charla
                    })
                    conn.commit()
            except Exception as e:
                logger.error(f"❌ Error guardando respuesta IA: {e}")

        return {"status": "received"}

    except Exception as e:
        logger.error(f"🔥 Error crítico en Webhook: {e}")
        return {"status": "error", "detail": str(e)}