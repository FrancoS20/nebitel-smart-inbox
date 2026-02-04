import os
import logging
import requests
from typing import Dict, Any
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import orjson
from dotenv import load_dotenv

# Tus módulos
import cerebro
from sqlalchemy import create_engine, text

# --- 1. CONFIGURACIÓN ---
load_dotenv()

# Configuración de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("webhook-turbo")

app = FastAPI()

# Variables de entorno
DB_URL = os.getenv("DATABASE_URL")
META_TOKEN = os.getenv("META_TOKEN")
META_PHONE_ID = os.getenv("META_PHONE_ID")
META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "nebitel_token_secreto")

# Conexión a DB (Pool Optimizado para alto tráfico)
engine = create_engine(
    DB_URL, 
    pool_pre_ping=True, 
    pool_size=5, 
    max_overflow=10,
    pool_recycle=1800
)

# --- 2. FUNCIÓN PARA ENVIAR A META (SALIDA) ---
def enviar_a_whatsapp_api(telefono, texto):
    """Envía el mensaje final a la API de Meta"""
    if not META_TOKEN or not META_PHONE_ID:
        logger.error("❌ Faltan credenciales de Meta en .env")
        return

    url = f"https://graph.facebook.com/v21.0/{META_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {META_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": telefono,
        "type": "text",
        "text": {"body": texto}
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        if response.status_code == 200:
            logger.info(f"✅ Mensaje enviado a {telefono}")
        else:
            logger.error(f"❌ Error Meta: {response.text}")
    except Exception as e:
        logger.error(f"❌ Excepción enviando a Meta: {e}")

# --- 3. TAREA DE FONDO (LÓGICA CRÍTICA) ---
def procesar_mensaje_fondo(payload: Dict[Any, Any]):
    """
    Esta función corre en paralelo. 
    Incluye: Guardado, Chequeo de Estado (ON/OFF), IA y Respuesta.
    """
    try:
        # A. Extraer datos (Parsing seguro)
        entry = payload.get('entry', [])
        if not entry: return
        changes = entry[0].get('changes', [])
        if not changes: return
        value = changes[0].get('value', {})
        messages = value.get('messages', [])
        
        if not messages: return # Es una actualización de estado, no un mensaje nuevo.

        msg = messages[0]
        
        # --- DEFINICIÓN DE TELÉFONOS ---
        # 1. telefono_para_meta: El ID original (con 549 generalmente).
        telefono_para_meta = msg.get('from', '') 
        
        # 2. telefono_db: Limpio para la base de datos (sin +).
        telefono_db = str(telefono_para_meta).replace('+', '').strip()
        
        texto = msg.get('text', {}).get('body', '')
        
        # Nombre del perfil
        contacts_meta = value.get('contacts', [])
        nombre = contacts_meta[0].get('profile', {}).get('name', 'Desconocido') if contacts_meta else 'Desconocido'
        
        logger.info(f"📨 Procesando: {nombre} ({telefono_db}) - '{texto}'")

        with engine.connect() as conn:
            # B. Guardar en Base de Datos
            # 1. Asegurar contacto
            conn.execute(text("""
                INSERT INTO contacts (client_id, name, platform) 
                VALUES (:cid, :nom, 'whatsapp') 
                ON CONFLICT (client_id) DO UPDATE SET last_activity = NOW()
            """), {"cid": telefono_db, "nom": nombre})
            
            # 2. Guardar mensaje entrante
            conn.execute(text("""
                INSERT INTO messages (contact_id, message_text, direction, status, sender_type, created_at)
                VALUES (:cid, :txt, 'inbound', 'received', 'user', NOW())
            """), {"cid": telefono_db, "txt": texto})
            conn.commit()

            # 🛑 --- EL FRENO DE MANO (CHEQUEO DE ESTADO) --- 🛑
            # Consultamos si el bot tiene permiso para hablar.
            estado_bot = conn.execute(text("SELECT bot_mode FROM contacts WHERE client_id = :uid"), {"uid": telefono_db}).scalar()
            
            # Si el estado es FALSE, cortamos acá. No gastamos IA, no respondemos.
            if estado_bot is False:
                logger.info(f"🤐 Bot APAGADO para {telefono_db}. No se responde.")
                return 
            # ---------------------------------------------------

            # C. INVOCAR AL CEREBRO 🧠
            # Recuperar contexto (últimos 6 mensajes)
            rows = conn.execute(text("SELECT sender_type, message_text FROM messages WHERE contact_id = :uid ORDER BY created_at DESC LIMIT 6"), {"uid": telefono_db}).fetchall()
            
            # Armado de historial limpio para la IA
            historial = []
            for r in reversed(rows):
                sender_db = r[0] 
                texto_db = r[1]
                
                # Mapeo de roles para Groq
                role_api = 'user'
                if sender_db in ['bot', 'human']: role_api = 'assistant'
                
                if texto_db: historial.append({"role": role_api, "content": texto_db})
            
            # --- LA IA PIENSA ---
            respuesta_ia = cerebro.procesar_mensaje(texto, historial)
            texto_resp = respuesta_ia.get('respuesta', '')
            intencion = respuesta_ia.get('intencion', 'General')
            prio = respuesta_ia.get('prioridad', 5)

            # D. Guardar respuesta y Enviar
            if texto_resp:
                
                # --- DOBLE CHEQUEO (Seguridad Extra) ---
                # Por si lo apagaste mientras la IA pensaba
                rechequeo = conn.execute(text("SELECT bot_mode FROM contacts WHERE client_id = :uid"), {"uid": telefono_db}).scalar()
                if rechequeo is False:
                    logger.info(f"🤐 Bot apagado durante el proceso para {telefono_db}. Abortando.")
                    return

                # 1. Guardar respuesta en DB
                conn.execute(text("""
                    INSERT INTO messages (contact_id, message_text, direction, status, sender_type, intent, priority_score, created_at)
                    VALUES (:cid, :resp, 'outbound', 'generated', 'bot', :intent, :prio, NOW())
                """), {"cid": telefono_db, "resp": texto_resp, "intent": intencion, "prio": prio})
                conn.commit()
                
                # 2. ENVIAR A META 🚀
                # --- FIX ARGENTINA SANDBOX ---
                # Si el numero empieza con 549, le cambiamos a 54 SOLO para el envío.
                dest_final = telefono_para_meta
                if dest_final.startswith("549"):
                    logger.info("🇦🇷 Aplicando corrección Sandbox (549 -> 54)")
                    dest_final = dest_final.replace("549", "54", 1)
                
                enviar_a_whatsapp_api(dest_final, texto_resp)

    except Exception as e:
        logger.error(f"🔥 Error CRÍTICO en background task: {e}")

# --- 4. CLASE JSON OPTIMIZADA ---
class ORJSONResponseCustom(JSONResponse):
    media_type = "application/json"
    def render(self, content: Any) -> bytes:
        return orjson.dumps(content)

# --- 5. ENDPOINTS ---

@app.post("/webhook", response_class=ORJSONResponseCustom)
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    """Endpoint de Alta Velocidad."""
    try:
        body_bytes = await request.body()
        payload = orjson.loads(body_bytes)
        background_tasks.add_task(procesar_mensaje_fondo, payload)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error en recepción: {e}")
        return {"status": "error"} 

@app.get("/webhook")
async def verify_webhook(request: Request):
    """Verificación de Meta"""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    
    if mode == "subscribe" and token == META_VERIFY_TOKEN:
        return int(challenge)
    raise HTTPException(status_code=403, detail="Token inválido")

# Entry point
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)