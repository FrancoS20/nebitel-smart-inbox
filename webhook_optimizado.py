import os
import logging
import tempfile
import hmac
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional

import requests
import orjson
import cloudinary
import cloudinary.uploader
import uvicorn
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Header
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# --- IMPORTACIONES ORM ---
from sqlalchemy.orm import Session
# IMPORTANTE: Asegúrate de que el archivo de tus modelos se llame 'BD_V3.py'
from BD_V3 import Contact, Message, engine 

import cerebro

# ==========================================
# CONFIGURACIÓN GLOBAL Y ENTORNO
# ==========================================
load_dotenv()

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("nebitel-webhook")

app = FastAPI(title="Nebitel Smart Inbox Webhook", version="4.0.0") # Versión actualizada

# Variables de Entorno
META_TOKEN = os.getenv("META_TOKEN")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
META_PHONE_ID = os.getenv("META_PHONE_ID")
META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "nebitel_token_secreto")
CLOUDINARY_URL = os.getenv("CLOUDINARY_URL")
APP_SECRET = os.getenv("APP_SECRET") # NUEVO: Obligatorio para Graph API v25.0

# ==========================================
# SEGURIDAD HMAC (v25.0)
# ==========================================
def verify_meta_signature(payload_body: bytes, signature_header: str) -> bool:
    """Verifica la firma criptográfica de Meta para evitar ataques."""
    if not APP_SECRET or not signature_header:
        return False
    try:
        expected_signature = hmac.new(
            bytes(APP_SECRET, 'latin-1'),
            msg=payload_body,
            digestmod=hashlib.sha256
        ).hexdigest()
        
        provided_signature = signature_header.split("=")[1]
        return hmac.compare_digest(expected_signature, provided_signature)
    except Exception as e:
        logger.error(f"Error en verificación HMAC: {e}")
        return False

# ==========================================
# INICIALIZACIÓN DE SERVICIOS EXTERNOS
# ==========================================
def init_cloudinary() -> None:
    """Configura la conexión con Cloudinary de forma segura."""
    if CLOUDINARY_URL:
        try:
            os.environ["CLOUDINARY_URL"] = CLOUDINARY_URL
            cloudinary.reset_config()
            cloudinary.config(secure=True)
            logger.info("☁️ Cloudinary conectado correctamente.")
        except Exception as e:
            logger.error(f"❌ Error configurando Cloudinary: {e}")

init_cloudinary()

# ==========================================
# SERVICIOS DE MEDIOS (MEDIA SERVICES)
# ==========================================
def procesar_y_subir_media(url_media: str, token: str, resource_type: str = "image") -> Optional[str]:
    try:
        # NUEVO: User-Agent Spoofing para evitar bloqueos
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url_media, headers=headers, timeout=15)
        response.raise_for_status()
        
        if CLOUDINARY_URL:
            res = cloudinary.uploader.upload(response.content, resource_type=resource_type)
            secure_url = res.get("secure_url")
            logger.info(f"☁️ Media procesada y subida: {secure_url}")
            return secure_url
    except Exception as e:
        logger.error(f"❌ Error procesando media: {e}")
    return None

def obtener_url_media_meta(media_id: str, token: str) -> Optional[str]:
    try:
        req = requests.get(
            f"https://graph.facebook.com/v25.0/{media_id}", # NUEVO: Endpoint v25.0
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        req.raise_for_status()
        return req.json().get('url')
    except Exception as e:
        logger.error(f"❌ Error obteniendo URL de media_id {media_id}: {e}")
        return None

# ==========================================
# NORMALIZACIÓN DE PAYLOADS
# ==========================================
def normalizar_evento(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        object_type = payload.get('object') 
        entry = payload.get('entry', [])[0]
        
        # --- PARSER WHATSAPP ---
        if 'changes' in entry:
            change = entry['changes'][0]['value']
            if 'messages' not in change: return None
            
            mensaje = change['messages'][0]
            datos = {
                'platform': 'whatsapp',
                'sender_id': mensaje['from'].replace('+', '').strip(),
                'name': change.get('contacts', [{}])[0].get('profile', {}).get('name', 'Desconocido'),
                'type': mensaje['type'],
                'media_url': None,
                'media_type': None,
                'is_echo': False,
                'message_category': 'service' # Por defecto para DB
            }
            
            if 'referral' in mensaje:
                ref = mensaje['referral']
                datos['ad_context'] = f"Viene del anuncio: {ref.get('headline', 'Promo')} - {ref.get('body', '')}"
                if ref.get('source_type') == 'ad':
                    datos['message_category'] = 'ctwa' # Click-to-WhatsApp (Gratis 72h)
            
            if datos['type'] == 'text':
                datos['text'] = mensaje['text']['body']
            elif datos['type'] == 'image':
                url_temp = obtener_url_media_meta(mensaje['image']['id'], WHATSAPP_TOKEN)
                if url_temp:
                    datos['media_url'] = procesar_y_subir_media(url_temp, WHATSAPP_TOKEN, "image")
                datos['text'] = mensaje['image'].get('caption', '(Foto enviada)')
                datos['media_type'] = 'image'
            elif datos['type'] == 'audio':
                datos['audio_url_meta'] = obtener_url_media_meta(mensaje['audio']['id'], WHATSAPP_TOKEN)
                datos['text'] = "(Audio recibiendo...)"
                datos['media_type'] = 'audio'
                
            return datos

        # --- PARSER INSTAGRAM/FACEBOOK ---
        elif 'messaging' in entry:
            event = entry['messaging'][0]
            if 'message' not in event: return None

            message = event['message']
            plataforma = 'instagram' if object_type == 'instagram' else 'facebook'
            
            datos = {
                'platform': plataforma,
                'name': f"Usuario {plataforma.capitalize()}",
                # Maneja el nuevo BSUID si está, sino usa el ID clásico
                'sender_id': event['sender'].get('user_ref', event['sender']['id']), 
                'is_echo': message.get('is_echo', False),
                'media_url': None,
                'media_type': None,
                'message_category': 'service'
            }
            
            if datos['is_echo']:
                datos['sender_id'] = event['recipient']['id'] 
                datos['text'] = message.get('text', '(Mensaje de empleado)')
                datos['app_id'] = message.get('app_id')
                return datos 

            if 'referral' in event:
                datos['ad_context'] = f"Viene de anuncio IG ref: {event['referral'].get('ref')}"

            texto_base = message.get('text', '').strip()

            if 'reply_to' in message and 'story' in message['reply_to']:
                story_url = message['reply_to']['story'].get('url', 'URL_Oculta')
                datos['text'] = f"[Respondió a historia: {story_url}] {texto_base}".strip()
                datos['type'] = 'text'
            elif 'attachments' in message:
                att = message['attachments'][0]
                if 'story_url' in att:
                    datos['text'] = f"[Respondió a historia: {att['story_url']}] {texto_base}".strip()
                    datos['type'] = 'text'
                elif att['type'] == 'image':
                    url_temp = att['payload']['url']
                    try:
                        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                        contenido = requests.get(url_temp, headers=headers, timeout=10).content
                        if CLOUDINARY_URL:
                            datos['media_url'] = cloudinary.uploader.upload(contenido, resource_type="image").get("secure_url")
                    except Exception as e:
                        logger.error(f"Error subiendo adjunto IG/FB: {e}")
                    datos['text'] = texto_base if texto_base else "(Foto)"
                    datos['type'] = 'image'
                    datos['media_type'] = 'image'
                elif att['type'] == 'audio':
                    datos['text'] = "(Audio de IG/FB - No soportado aún)"
                    datos['type'] = 'audio'
            else:
                datos['text'] = texto_base
                datos['type'] = 'text'

            return datos

    except Exception as e:
        logger.error(f"⚠️ Error crítico normalizando evento: {e}")
        return None

# ==========================================
# COMUNICACIÓN SALIENTE
# ==========================================
def enviar_respuesta_meta(destinatario_id: str, texto: str, plataforma: str) -> None:
    token = WHATSAPP_TOKEN if plataforma == 'whatsapp' else META_TOKEN
    if not token: 
        logger.error(f"❌ Error: Token no configurado para {plataforma}.")
        return

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        if plataforma == 'whatsapp':
            if not META_PHONE_ID: return
            dest_meta = destinatario_id.replace("549", "54", 1) if destinatario_id.startswith("549") else destinatario_id
            url = f"https://graph.facebook.com/v25.0/{META_PHONE_ID}/messages" # NUEVO: v25.0
            payload = {
                "messaging_product": "whatsapp",
                "to": dest_meta,
                "type": "text",
                "text": {"body": texto}
            }
        else:
            url = "https://graph.facebook.com/v25.0/me/messages" # NUEVO: v25.0
            payload = {
                "recipient": {"id": destinatario_id},
                "message": {"text": texto},
                "messaging_type": "RESPONSE"
            }

        res = requests.post(url, headers=headers, json=payload, timeout=15)
        res.raise_for_status()
        logger.info(f"✅ Respuesta enviada a {plataforma} ({destinatario_id})")
    except requests.RequestException as e:
        logger.error(f"❌ Error de red enviando mensaje a Meta: {e}")

# ==========================================
# LÓGICA CORE ORM (BACKGROUND WORKER)
# ==========================================
def procesar_mensaje_fondo(payload: Dict[str, Any]) -> None:
    datos = normalizar_evento(payload)
    if not datos: 
        return

    sender_id, platform, nombre = datos['sender_id'], datos['platform'], datos.get('name', 'Desconocido')
    texto_usuario = datos.get('text', '').strip()

    if not texto_usuario and not datos.get('is_echo'):
        logger.info(f"😶 Mensaje vacío/sticker ({sender_id}). Ignorado.")
        return

    try:
        with Session(engine) as session:
            
            # --- 1. GESTIÓN DE SESIÓN Y CLIENTE ---
            contacto = session.query(Contact).filter_by(client_id=sender_id).first()
            
            if not contacto:
                contacto = Contact(client_id=sender_id, name=nombre, platform=platform)
                session.add(contacto)
            else:
                contacto.name = nombre
                
                if contacto.last_activity:
                    horas_inactivo = (datetime.now(timezone.utc) - contacto.last_activity).total_seconds() / 3600
                    if horas_inactivo > 12:
                        logger.info(f"🌅 Sesión expirada ({horas_inactivo:.1f}h). Reactivando bot para {sender_id}")
                        contacto.bot_mode = True

            # --- 2. ESCUDO ANTI-DUPLICADOS Y GESTIÓN DE ECOS ---
            if datos.get('is_echo'):
                if datos.get('app_id'): 
                    return 
                
                ultimo_msg_out = session.query(Message).filter_by(
                    contact_id=sender_id, direction='outbound'
                ).order_by(Message.created_at.desc()).first()

                if ultimo_msg_out and ultimo_msg_out.message_text == texto_usuario:
                    logger.info("🤖 Eco duplicado detectado. Abortando flujo.")
                    return
                
                logger.info(f"🛡️ HANDOFF: Empleado escribió desde Meta. Apagando bot para {sender_id}.")
                contacto.bot_mode = False
                
                msg_humano = Message(
                    contact_id=sender_id,
                    message_text=texto_usuario,
                    direction='outbound',
                    sender_type='human',
                    status='sent'
                )
                session.add(msg_humano)
                session.commit()
                return 

            # --- 3. PROCESAMIENTO MULTIMEDIA ---
            if datos.get('type') == 'audio' and datos.get('audio_url_meta'):
                logger.info("🎤 Transcribiendo audio...")
                token_audio = WHATSAPP_TOKEN if platform == 'whatsapp' else META_TOKEN
                audio_bytes = obtener_url_media_meta(datos['audio_url_meta'], token_audio)
                
                # NUEVO: User Agent para Audio
                headers_audio = {"Authorization": f"Bearer {token_audio}", "User-Agent": "Mozilla/5.0"}
                req = requests.get(datos['audio_url_meta'], headers=headers_audio)
                
                if req.status_code == 200:
                    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as temp_audio:
                        temp_audio.write(req.content)
                        temp_path = temp_audio.name
                        
                    texto_usuario = cerebro.transcribir_audio(temp_path)
                    try: os.remove(temp_path)
                    except OSError: pass
                else:
                    texto_usuario = "(Audio vacío o no procesable)"

            logger.info(f"📨 [{platform.upper()}] {nombre}: '{texto_usuario}'")

            # --- 4. PERSISTENCIA INBOUND ---
            nuevo_mensaje = Message(
                contact_id=sender_id,
                message_text=texto_usuario,
                media_url=datos.get('media_url'),
                media_type=datos.get('media_type'),
                direction='inbound',
                sender_type='user',
                status='received',
                message_category=datos.get('message_category', 'service') # Persistencia del tipo de costo
            )
            session.add(nuevo_mensaje)
            session.commit() 

            # --- 5. LÓGICA DE BOT Y RESPUESTA IA ---
            if not contacto.bot_mode:
                logger.info(f"🤐 Bot en modo silencioso (Humano atendiendo) para {sender_id}.")
                return 

            historial_db = session.query(Message).filter_by(contact_id=sender_id).order_by(Message.created_at.desc()).limit(6).all()
            historial = [{"role": "assistant" if m.sender_type == 'bot' else "user", "content": m.message_text} for m in reversed(historial_db)]
            
            prompt_final = texto_usuario
            if datos.get('ad_context'): 
                prompt_final += f" [CONTEXTO DE SISTEMA: {datos['ad_context']}]"

            respuesta_ia = cerebro.procesar_mensaje(prompt_final, historial)
            texto_resp = respuesta_ia.get('respuesta', '')
            
            if texto_resp:
                if respuesta_ia.get('necesita_humano', False):
                    logger.info(f"🔄 HANDOFF IA: Transfiriendo {sender_id} a humano.")
                    contacto.bot_mode = False

                msg_bot = Message(
                    contact_id=sender_id,
                    message_text=texto_resp,
                    direction='outbound',
                    sender_type='bot',
                    intent=respuesta_ia.get('intencion', 'General'),
                    priority_score=respuesta_ia.get('prioridad', 5),
                    status='generated'
                )
                session.add(msg_bot)
                session.commit()
                
                enviar_respuesta_meta(sender_id, texto_resp, platform)

    except Exception as e:
        logger.error(f"🔥 Error CRÍTICO en la cadena de procesamiento de fondo: {e}", exc_info=True)

# ==========================================
# RUTAS FASTAPI (ENDPOINTS)
# ==========================================
class ORJSONResponseCustom(JSONResponse):
    media_type = "application/json"
    def render(self, content: Any) -> bytes:
        return orjson.dumps(content)

@app.post("/webhook", response_class=ORJSONResponseCustom)
async def receive_webhook(
    request: Request, 
    background_tasks: BackgroundTasks,
    x_hub_signature_256: Optional[str] = Header(None) # NUEVO: Captura de firma
):
    try:
        body_bytes = await request.body()
        
        # NUEVO: Validación estricta
        if APP_SECRET and not verify_meta_signature(body_bytes, x_hub_signature_256):
            logger.warning("🚨 Intento de ataque rechazado: Firma HMAC inválida.")
            raise HTTPException(status_code=403, detail="Invalid signature")

        payload = orjson.loads(body_bytes)
        background_tasks.add_task(procesar_mensaje_fondo, payload)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error parseando webhook: {e}")
        return {"status": "error"} 

@app.get("/webhook")
async def verify_webhook(request: Request):
    if request.query_params.get("hub.verify_token") == META_VERIFY_TOKEN:
        return int(request.query_params.get("hub.challenge"))
    raise HTTPException(status_code=403, detail="Invalid verification token")

@app.get("/")
async def health_check():
    return {"status": "Nebitel Smart Inbox Activo", "timestamp": datetime.now(timezone.utc).isoformat()}

@app.get("/")
async def health_check():
    return {"status": "estoy_despierto"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)