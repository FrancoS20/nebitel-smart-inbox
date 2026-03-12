import os
import logging
import requests
import cloudinary
import cloudinary.uploader
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import orjson
from dotenv import load_dotenv
import tempfile
from datetime import datetime 

import cerebro
from sqlalchemy import create_engine, text

# CONFIGURACIÓN 
load_dotenv()

# Configuración de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("webhook-bionico")

app = FastAPI()

# Variables de entorno 
DB_URL = os.getenv("DATABASE_URL")
META_TOKEN = os.getenv("META_TOKEN")           # Llave del Local (IG y FB)
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")   # Llave del Edificio (WhatsApp)
META_PHONE_ID = os.getenv("META_PHONE_ID")
META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "nebitel_token_secreto")
CLOUDINARY_URL = os.getenv("CLOUDINARY_URL")

# Configurar Cloudinary
if CLOUDINARY_URL:
    try:
        os.environ["CLOUDINARY_URL"] = CLOUDINARY_URL
        cloudinary.reset_config()
        cloudinary.config(secure=True)
        logger.info(f"☁️ Cloudinary conectado correctamente.")
    except Exception as e:
        logger.error(f"❌ Error configurando Cloudinary: {e}")

# Conexión a DB
engine = create_engine(
    DB_URL, 
    pool_pre_ping=True, 
    pool_size=5, 
    max_overflow=10,
    pool_recycle=1800
)

# FUNCIONES AUXILIARES
def descargar_media_meta(url_media: str, token_a_usar: str) -> Optional[bytes]:
    try:
        headers = {"Authorization": f"Bearer {token_a_usar}"}
        response = requests.get(url_media, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.content
        return None
    except Exception as e:
        logger.error(f"❌ Error descarga Meta: {e}")
        return None

def subir_a_cloudinary(contenido_bytes, recurso_tipo="image") -> Optional[str]:
    try:
        if not CLOUDINARY_URL or not contenido_bytes: return None
        res = cloudinary.uploader.upload(contenido_bytes, resource_type=recurso_tipo)
        secure_url = res.get("secure_url")
        return secure_url
    except Exception as e:
        logger.error(f"❌ Error Cloudinary: {e}")
        return None

def normalizar_evento(payload: Dict[Any, Any]) -> Optional[Dict]:
    datos = {}
    try:
        object_type = payload.get('object') 
        entry = payload.get('entry', [])[0]
        
        # WHATSAPP
        if 'changes' in entry:
            change = entry['changes'][0]['value']
            if 'messages' not in change: return None
            
            mensaje = change['messages'][0]
            datos['platform'] = 'whatsapp'
            datos['sender_id'] = mensaje['from'].replace('+', '').strip()
            datos['name'] = change.get('contacts', [{}])[0].get('profile', {}).get('name', 'Desconocido')
            
            if 'referral' in mensaje:
                ref = mensaje['referral']
                datos['ad_context'] = f"Viene del anuncio: {ref.get('headline', 'Promo')} - {ref.get('body', '')}"
            else:
                datos['ad_context'] = None

            msg_type = mensaje['type']
            datos['type'] = msg_type 

            if msg_type == 'text':
                datos['text'] = mensaje['text']['body']
                datos['media_url'] = None
            elif msg_type == 'image':
                media_id = mensaje['image']['id']
                req = requests.get(f"https://graph.facebook.com/v21.0/{media_id}", headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"})
                if req.status_code == 200:
                    url_temp = req.json().get('url')
                    contenido = descargar_media_meta(url_temp, WHATSAPP_TOKEN)
                    datos['media_url'] = subir_a_cloudinary(contenido, "image")
                    datos['text'] = mensaje['image'].get('caption', '(Foto enviada)')
                    datos['media_type'] = 'image'
                else:
                    datos['text'] = "(Error Foto)"
            elif msg_type == 'audio':
                media_id = mensaje['audio']['id']
                req = requests.get(f"https://graph.facebook.com/v21.0/{media_id}", headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"})
                if req.status_code == 200:
                    datos['audio_url_meta'] = req.json().get('url') 
                    datos['text'] = "(Audio recibiendo...)" 
                    datos['media_type'] = 'audio'
                else:
                    datos['text'] = "(Error Audio)"

        # INSTAGRAM Y FACEBOOK MESSENGER 
        elif 'messaging' in entry:
            event = entry['messaging'][0]
            if 'message' not in event: return None

            if object_type == 'instagram':
                datos['platform'] = 'instagram'
                datos['name'] = "Usuario Instagram"
            else:
                datos['platform'] = 'facebook'
                datos['name'] = "Usuario Facebook"

            datos['sender_id'] = event['sender']['id']
            message = event['message']
            
            if message.get('is_echo') == True:
                datos['is_echo'] = True
                datos['sender_id'] = event['recipient']['id'] 
                datos['text'] = message.get('text', '(Mensaje de empleado)')
                datos['app_id'] = message.get('app_id')
                return datos 
            else:
                datos['is_echo'] = False

            if 'referral' in event:
                 datos['ad_context'] = f"Viene de anuncio IG ref: {event['referral'].get('ref')}"
            else:
                 datos['ad_context'] = None

            if 'text' in message:
                datos['text'] = message['text']
                datos['type'] = 'text'
            elif 'attachments' in message:
                att = message['attachments'][0]
                if att['type'] == 'image':
                    url_temp = att['payload']['url']
                    contenido = requests.get(url_temp).content
                    datos['media_url'] = subir_a_cloudinary(contenido, "image")
                    datos['text'] = "(Foto)"
                    datos['type'] = 'image'
                    datos['media_type'] = 'image'
                elif att['type'] == 'audio':
                     datos['text'] = "(Audio de IG/FB - No soportado aún)"

        return datos if 'sender_id' in datos else None

    except Exception as e:
        logger.error(f"⚠️ Error normalizando: {e}")
        return None

# FUNCIÓN PARA ENVIAR (ACÁ ESTÁ LA MAGIA DE FRANCO RESTAURADA)
def enviar_respuesta_meta(destinatario_id, texto, plataforma):
    token_a_usar = WHATSAPP_TOKEN if plataforma == 'whatsapp' else META_TOKEN

    if not token_a_usar: 
        logger.error(f"❌ Error: No hay token configurado para {plataforma}.")
        return

    headers = {"Authorization": f"Bearer {token_a_usar}", "Content-Type": "application/json"}
    
    try:
        if plataforma == 'whatsapp':
            if not META_PHONE_ID: return
            url = f"https://graph.facebook.com/v21.0/{META_PHONE_ID}/messages"
            
            dest_meta = destinatario_id
            if dest_meta.startswith("549"):
                dest_meta = dest_meta.replace("549", "54", 1)
                
            payload = {
                "messaging_product": "whatsapp",
                "to": dest_meta,
                "type": "text",
                "text": {"body": texto}
            }

        elif plataforma in ['instagram', 'facebook']:
            url = "https://graph.facebook.com/v21.0/me/messages"
            payload = {
                "recipient": {"id": destinatario_id},
                "message": {"text": texto},
                "messaging_type": "RESPONSE"
            }
        else:
            return

        res = requests.post(url, headers=headers, json=payload, timeout=15)
        
        if res.status_code == 200:
            logger.info(f"✅ ¡Éxito! Mensaje enviado a {plataforma} ({destinatario_id})")
        else:
            logger.error(f"❌ Error de Meta enviando a {plataforma}: {res.text}")

    except Exception as e:
        logger.error(f"🔥 Excepción crítica enviando mensaje: {e}")

# TAREA DE FONDO 
def procesar_mensaje_fondo(payload: Dict[Any, Any]):
    try:
        datos = normalizar_evento(payload)
        if not datos: return

        sender_id = datos['sender_id']
        platform = datos['platform']
        nombre = datos.get('name', 'Desconocido')
        texto_usuario = datos.get('text', '').strip()

        if not texto_usuario and not datos.get('is_echo'): return

        with engine.connect() as conn:
            if datos.get('is_echo') == True:
                if datos.get('app_id'): return
                
                ultimo_mensaje_bot = conn.execute(text(
                    "SELECT message_text FROM messages WHERE contact_id = :uid AND sender_type = 'bot' ORDER BY created_at DESC LIMIT 1"
                ), {"uid": sender_id}).scalar()

                if ultimo_mensaje_bot and ultimo_mensaje_bot.strip() == texto_usuario: return
                
                logger.info(f"🛡️ ESCUDO ANTI-ECOS: Empleado escribió. Apagando bot para {sender_id}.")
                conn.execute(text("UPDATE contacts SET bot_mode = False, last_activity = NOW() WHERE client_id = :uid"), {"uid": sender_id})
                conn.execute(text("""
                    INSERT INTO messages (contact_id, message_text, direction, status, sender_type, created_at)
                    VALUES (:cid, :txt, 'outbound', 'sent', 'human', NOW())
                """), {"cid": sender_id, "txt": texto_usuario})
                conn.commit()
                return 

            contacto = conn.execute(text("SELECT bot_mode, last_activity FROM contacts WHERE client_id = :uid"), {"uid": sender_id}).fetchone()
            if contacto and contacto.last_activity:
                horas_inactivo = (datetime.now() - contacto.last_activity).total_seconds() / 3600
                if horas_inactivo > 12:
                    conn.execute(text("UPDATE contacts SET bot_mode = True WHERE client_id = :uid"), {"uid": sender_id})
                    conn.commit()

            conn.execute(text("""
                INSERT INTO contacts (client_id, name, platform) VALUES (:cid, :nom, :plat) 
                ON CONFLICT (client_id) DO UPDATE SET last_activity = NOW(), name = :nom
            """), {"cid": sender_id, "nom": nombre, "plat": platform})
            
            if datos.get('type') == 'audio' and datos.get('audio_url_meta'):
                token_para_audio = WHATSAPP_TOKEN if platform == 'whatsapp' else META_TOKEN
                audio_bytes = descargar_media_meta(datos['audio_url_meta'], token_para_audio)
                
                if audio_bytes:
                    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as temp_audio:
                        temp_audio.write(audio_bytes)
                        temp_path = temp_audio.name
                    texto_transcrito = cerebro.transcribir_audio(temp_path)
                    try: os.remove(temp_path)
                    except: pass
                    texto_usuario = texto_transcrito
                else:
                    texto_usuario = "(Audio vacío)"

            conn.execute(text("""
                INSERT INTO messages (contact_id, message_text, media_url, media_type, direction, status, sender_type, created_at)
                VALUES (:cid, :txt, :url, :mtype, 'inbound', 'received', 'user', NOW())
            """), {"cid": sender_id, "txt": texto_usuario, "url": datos.get('media_url'), "mtype": datos.get('media_type')})
            conn.commit()

            estado_bot = conn.execute(text("SELECT bot_mode FROM contacts WHERE client_id = :uid"), {"uid": sender_id}).scalar()
            if estado_bot is False: return 

            rows = conn.execute(text("SELECT sender_type, message_text FROM messages WHERE contact_id = :uid ORDER BY created_at DESC LIMIT 6"), {"uid": sender_id}).fetchall()
            historial = [{"role": "assistant" if r[0] in ['bot'] else "user", "content": r[1]} for r in reversed(rows)]
            
            prompt_final = texto_usuario
            notas_contexto = []
            if datos.get('ad_context'): notas_contexto.append(f"[SISTEMA: Viene de anuncio: '{datos['ad_context']}']")
            if notas_contexto: prompt_final += " " + " ".join(notas_contexto)

            respuesta_ia = cerebro.procesar_mensaje(prompt_final, historial)
            texto_resp = respuesta_ia.get('respuesta', '')
            intencion = respuesta_ia.get('intencion', 'General')
            prio = respuesta_ia.get('prioridad', 5)
            necesita_humano = respuesta_ia.get('necesita_humano', False)

            if texto_resp:
                if necesita_humano:
                    conn.execute(text("UPDATE contacts SET bot_mode = False WHERE client_id = :uid"), {"uid": sender_id})

                conn.execute(text("""
                    INSERT INTO messages (contact_id, message_text, direction, status, sender_type, intent, priority_score, created_at)
                    VALUES (:cid, :resp, 'outbound', 'generated', 'bot', :intent, :prio, NOW())
                """), {"cid": sender_id, "resp": texto_resp, "intent": intencion, "prio": prio})
                conn.commit()
                
                enviar_respuesta_meta(sender_id, texto_resp, platform)

    except Exception as e:
        logger.error(f"🔥 Error CRÍTICO en background task: {e}")

class ORJSONResponseCustom(JSONResponse):
    media_type = "application/json"
    def render(self, content: Any) -> bytes:
        return orjson.dumps(content)

@app.post("/webhook", response_class=ORJSONResponseCustom)
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        body_bytes = await request.body()
        payload = orjson.loads(body_bytes)
        background_tasks.add_task(procesar_mensaje_fondo, payload)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error"} 

@app.get("/webhook")
async def verify_webhook(request: Request):
    if request.query_params.get("hub.verify_token") == META_VERIFY_TOKEN:
        return int(request.query_params.get("hub.challenge"))
    raise HTTPException(status_code=403)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)