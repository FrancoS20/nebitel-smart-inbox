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
from datetime import datetime # <--- AGREGADO PARA EL TIMEOUT DE 12HS

# Tus módulos
import cerebro
from sqlalchemy import create_engine, text

# --- 1. CONFIGURACIÓN ---
load_dotenv()

# Configuración de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("webhook-bionico")

app = FastAPI()

# Variables de entorno
DB_URL = os.getenv("DATABASE_URL")
META_TOKEN = os.getenv("META_TOKEN")
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

# --- 2. FUNCIONES AUXILIARES ---

def descargar_media_meta(url_media: str) -> Optional[bytes]:
    try:
        headers = {"Authorization": f"Bearer {META_TOKEN}"}
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
        logger.info(f"☁️ Archivo guardado en Cloudinary: {secure_url}")
        return secure_url
    except Exception as e:
        logger.error(f"❌ Error Cloudinary: {e}")
        return None

def normalizar_evento(payload: Dict[Any, Any]) -> Optional[Dict]:
    datos = {}
    try:
        entry = payload.get('entry', [])[0]
        
        # --- CASO A: WHATSAPP ---
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
                req = requests.get(f"https://graph.facebook.com/v21.0/{media_id}", headers={"Authorization": f"Bearer {META_TOKEN}"})
                if req.status_code == 200:
                    url_temp = req.json().get('url')
                    contenido = descargar_media_meta(url_temp)
                    datos['media_url'] = subir_a_cloudinary(contenido, "image")
                    datos['text'] = mensaje['image'].get('caption', '(Foto enviada)')
                    datos['media_type'] = 'image'
                else:
                    datos['text'] = "(Error Foto)"
            elif msg_type == 'audio':
                media_id = mensaje['audio']['id']
                req = requests.get(f"https://graph.facebook.com/v21.0/{media_id}", headers={"Authorization": f"Bearer {META_TOKEN}"})
                if req.status_code == 200:
                    datos['audio_url_meta'] = req.json().get('url') 
                    datos['text'] = "(Audio recibiendo...)" 
                    datos['media_type'] = 'audio'
                else:
                    datos['text'] = "(Error Audio)"

        # --- CASO B: INSTAGRAM ---
        elif 'messaging' in entry:
            event = entry['messaging'][0]
            if 'message' not in event: return None

            datos['platform'] = 'instagram'
            datos['sender_id'] = event['sender']['id']
            datos['name'] = "Usuario Instagram" 
            
            message = event['message']
            
            # 🛡️ ESCUDO ANTI-ECOS: Detecta si lo mandó un humano de la empresa
            if message.get('is_echo') == True:
                datos['is_echo'] = True
                datos['text'] = message.get('text', '(Mensaje de empleado)')
                return datos # Retorna rápido para cortar ejecución
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
                    datos['text'] = "(Foto de Instagram)"
                    datos['type'] = 'image'
                    datos['media_type'] = 'image'
                elif att['type'] == 'audio':
                     datos['text'] = "(Audio de Instagram - No soportado aún)"

        return datos if 'sender_id' in datos else None

    except Exception as e:
        logger.error(f"⚠️ Error normalizando: {e}")
        return None

# --- 3. FUNCIÓN PARA ENVIAR ---
def enviar_respuesta_meta(destinatario_id, texto, plataforma):
    if plataforma == 'whatsapp':
        if not META_TOKEN or not META_PHONE_ID: return
        url = f"https://graph.facebook.com/v21.0/{META_PHONE_ID}/messages"
        headers = {"Authorization": f"Bearer {META_TOKEN}", "Content-Type": "application/json"}
        
        if destinatario_id.startswith("549"):
            destinatario_id = destinatario_id.replace("549", "54", 1)
            
        data = {"messaging_product": "whatsapp", "to": destinatario_id, "type": "text", "text": {"body": texto}}
        try:
            requests.post(url, headers=headers, json=data, timeout=10)
        except Exception as e:
            logger.error(f"❌ Error enviando WA: {e}")

    elif plataforma in ['instagram', 'facebook']:
        # TODO: Implementar envío real de IG cuando haya permisos. Por ahora simulamos.
        logger.info(f"🚀 [SIMULACIÓN IG] Enviando a {destinatario_id}: {texto}")

# --- 4. TAREA DE FONDO (LÓGICA PRINCIPAL) ---
def procesar_mensaje_fondo(payload: Dict[Any, Any]):
    try:
        datos = normalizar_evento(payload)
        if not datos: return

        sender_id = datos['sender_id']
        platform = datos['platform']
        nombre = datos.get('name', 'Desconocido')
        texto_usuario = datos.get('text', '')

        with engine.connect() as conn:
            
            # 🛑 1. ESCUDO ANTI-ECOS: Freno de mano si escribió el empleado
            if datos.get('is_echo') == True:
                logger.info(f"🛡️ ESCUDO ANTI-ECOS: Empleado escribió. Apagando bot para {sender_id}.")
                conn.execute(text("UPDATE contacts SET bot_mode = False, last_activity = NOW() WHERE client_id = :uid"), {"uid": sender_id})
                conn.execute(text("""
                    INSERT INTO messages (contact_id, message_text, direction, status, sender_type, created_at)
                    VALUES (:cid, :txt, 'outbound', 'sent', 'human', NOW())
                """), {"cid": sender_id, "txt": texto_usuario})
                conn.commit()
                return 

            # ⏳ 2. RESETEO DE 12 HORAS (Session Timeout)
            contacto = conn.execute(text("SELECT bot_mode, last_activity FROM contacts WHERE client_id = :uid"), {"uid": sender_id}).fetchone()
            if contacto and contacto.last_activity:
                horas_inactivo = (datetime.now() - contacto.last_activity).total_seconds() / 3600
                if horas_inactivo > 12:
                    logger.info(f"🌅 Pasaron {horas_inactivo:.1f} horas. Reseteando bot para {sender_id}")
                    conn.execute(text("UPDATE contacts SET bot_mode = True WHERE client_id = :uid"), {"uid": sender_id})
                    conn.commit()

            # Guardar usuario y actualizar última actividad
            conn.execute(text("""
                INSERT INTO contacts (client_id, name, platform) VALUES (:cid, :nom, :plat) 
                ON CONFLICT (client_id) DO UPDATE SET last_activity = NOW(), name = :nom
            """), {"cid": sender_id, "nom": nombre, "plat": platform})
            
            # LÓGICA DE AUDIO (WHISPER)
            if datos.get('type') == 'audio' and datos.get('audio_url_meta'):
                logger.info("🎤 Mensaje de Audio detectado. Iniciando transcripción...")
                audio_bytes = descargar_media_meta(datos['audio_url_meta'])
                if audio_bytes:
                    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as temp_audio:
                        temp_audio.write(audio_bytes)
                        temp_path = temp_audio.name
                    texto_transcrito = cerebro.transcribir_audio(temp_path)
                    try: os.remove(temp_path)
                    except: pass
                    texto_usuario = texto_transcrito
                else:
                    texto_usuario = "(Audio vacío o error de descarga)"

            logger.info(f"📨 {platform.upper()}: {nombre} ({sender_id}) - '{texto_usuario}'")

            # Guardar mensaje entrante
            conn.execute(text("""
                INSERT INTO messages (contact_id, message_text, media_url, media_type, direction, status, sender_type, created_at)
                VALUES (:cid, :txt, :url, :mtype, 'inbound', 'received', 'user', NOW())
            """), {"cid": sender_id, "txt": texto_usuario, "url": datos.get('media_url'), "mtype": datos.get('media_type')})
            conn.commit()

            # Comprobar si el bot está prendido
            estado_bot = conn.execute(text("SELECT bot_mode FROM contacts WHERE client_id = :uid"), {"uid": sender_id}).scalar()
            if estado_bot is False:
                logger.info(f"🤐 Bot APAGADO para {sender_id}. Bye.")
                return 

            # --- C. CEREBRO IA 🧠 ---
            rows = conn.execute(text("SELECT sender_type, message_text FROM messages WHERE contact_id = :uid ORDER BY created_at DESC LIMIT 6"), {"uid": sender_id}).fetchall()
            historial = [{"role": "assistant" if r[0] in ['bot'] else "user", "content": r[1]} for r in reversed(rows)]
            
            prompt_final = texto_usuario
            notas_contexto = []
            if datos.get('ad_context'): notas_contexto.append(f"[SISTEMA: Viene de anuncio: '{datos['ad_context']}']")
            if datos.get('type') == 'audio': notas_contexto.append("[SISTEMA: El usuario envió un audio. Respondé natural.]")
            if notas_contexto: prompt_final += " " + " ".join(notas_contexto)

            respuesta_ia = cerebro.procesar_mensaje(prompt_final, historial)
            texto_resp = respuesta_ia.get('respuesta', '')
            intencion = respuesta_ia.get('intencion', 'General')
            prio = respuesta_ia.get('prioridad', 5)
            necesita_humano = respuesta_ia.get('necesita_humano', False) # Atrapamos la bandera

            if texto_resp:
                # 🛑 3. AUTO-APAGADO (Handoff desde la IA)
                if necesita_humano:
                    logger.info(f"🔄 HANDOFF: La IA detectó que se requiere un humano. Apagando bot para {sender_id}.")
                    conn.execute(text("UPDATE contacts SET bot_mode = False WHERE client_id = :uid"), {"uid": sender_id})

                conn.execute(text("""
                    INSERT INTO messages (contact_id, message_text, direction, status, sender_type, intent, priority_score, created_at)
                    VALUES (:cid, :resp, 'outbound', 'generated', 'bot', :intent, :prio, NOW())
                """), {"cid": sender_id, "resp": texto_resp, "intent": intencion, "prio": prio})
                conn.commit()
                
                enviar_respuesta_meta(sender_id, texto_resp, platform)

    except Exception as e:
        logger.error(f"🔥 Error CRÍTICO en background task: {e}")

# --- 5. ENDPOINTS & JSON ---
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
        logger.error(f"Error en recepción: {e}")
        return {"status": "error"} 

@app.get("/webhook")
async def verify_webhook(request: Request):
    if request.query_params.get("hub.verify_token") == META_VERIFY_TOKEN:
        return int(request.query_params.get("hub.challenge"))
    raise HTTPException(status_code=403)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)