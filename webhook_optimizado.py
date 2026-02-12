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
import tempfile # <--- AGREGADO: Para manejar los audios temporales

# Tus módulos
import cerebro
from sqlalchemy import create_engine, text

# --- 1. CONFIGURACIÓN ---
load_dotenv()

# Configuración de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("webhook-bionico") # Le cambié el nombre para que sepas que es el nuevo

app = FastAPI()

# Variables de entorno
DB_URL = os.getenv("DATABASE_URL")
META_TOKEN = os.getenv("META_TOKEN")
META_PHONE_ID = os.getenv("META_PHONE_ID")
META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "nebitel_token_secreto")
CLOUDINARY_URL = os.getenv("CLOUDINARY_URL")

# Configurar Cloudinary (BLINDADO) 🛡️
if CLOUDINARY_URL:
    try:
        os.environ["CLOUDINARY_URL"] = CLOUDINARY_URL
        cloudinary.reset_config()
        cloudinary.config(secure=True)
        logger.info(f"☁️ Cloudinary conectado correctamente.")
    except Exception as e:
        logger.error(f"❌ Error configurando Cloudinary: {e}")

# Conexión a DB (Pool Optimizado F1)
engine = create_engine(
    DB_URL, 
    pool_pre_ping=True, 
    pool_size=5, 
    max_overflow=10,
    pool_recycle=1800
)

# --- 2. FUNCIONES AUXILIARES (FOTOS, AUDIOS Y NORMALIZACIÓN) ---

def descargar_media_meta(url_media: str) -> Optional[bytes]:
    """Descarga cualquier archivo de Meta (Imagen o Audio)"""
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
    """Sube a Cloudinary. recurso_tipo puede ser 'image' o 'video' (audios van como video)"""
    try:
        if not CLOUDINARY_URL or not contenido_bytes: return None
        # Subir directo bytes
        res = cloudinary.uploader.upload(contenido_bytes, resource_type=recurso_tipo)
        secure_url = res.get("secure_url")
        logger.info(f"☁️ Archivo guardado en Cloudinary: {secure_url}")
        return secure_url
    except Exception as e:
        logger.error(f"❌ Error Cloudinary: {e}")
        return None

def normalizar_evento(payload: Dict[Any, Any]) -> Optional[Dict]:
    """
    Transforma el JSON de WhatsApp o Instagram en un diccionario estándar.
    Maneja Texto, Fotos, Audios y Publicidad.
    """
    datos = {}
    try:
        entry = payload.get('entry', [])[0]
        
        # --- CASO A: WHATSAPP (changes) ---
        if 'changes' in entry:
            change = entry['changes'][0]['value']
            if 'messages' not in change: return None
            
            mensaje = change['messages'][0]
            datos['platform'] = 'whatsapp'
            datos['sender_id'] = mensaje['from'].replace('+', '').strip()
            datos['name'] = change.get('contacts', [{}])[0].get('profile', {}).get('name', 'Desconocido')
            
            # Detectar Publicidad
            if 'referral' in mensaje:
                ref = mensaje['referral']
                datos['ad_context'] = f"Viene del anuncio: {ref.get('headline', 'Promo')} - {ref.get('body', '')}"
            else:
                datos['ad_context'] = None

            # TIPO DE MENSAJE
            msg_type = mensaje['type']
            datos['type'] = msg_type # Guardamos el tipo para saber si es audio después

            if msg_type == 'text':
                datos['text'] = mensaje['text']['body']
                datos['media_url'] = None
            
            elif msg_type == 'image':
                # FOTO 📸
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
                # AUDIO 🎤 (Esto faltaba)
                media_id = mensaje['audio']['id']
                req = requests.get(f"https://graph.facebook.com/v21.0/{media_id}", headers={"Authorization": f"Bearer {META_TOKEN}"})
                if req.status_code == 200:
                    datos['audio_url_meta'] = req.json().get('url') # Guardamos URL para descargar luego
                    datos['text'] = "(Audio recibiendo...)" 
                    datos['media_type'] = 'audio'
                else:
                    datos['text'] = "(Error Audio)"

        # --- CASO B: INSTAGRAM (messaging) ---
        elif 'messaging' in entry:
            event = entry['messaging'][0]
            if 'message' not in event: return None

            datos['platform'] = 'instagram'
            datos['sender_id'] = event['sender']['id']
            datos['name'] = "Usuario Instagram" 
            
            if 'referral' in event:
                 datos['ad_context'] = f"Viene de anuncio IG ref: {event['referral'].get('ref')}"
            else:
                 datos['ad_context'] = None

            message = event['message']
            if 'text' in message:
                datos['text'] = message['text']
                datos['type'] = 'text'
            elif 'attachments' in message:
                att = message['attachments'][0]
                if att['type'] == 'image':
                    url_temp = att['payload']['url']
                    # En IG la URL es pública, no necesita token, pero descargamos igual para subir a Cloudinary
                    contenido = requests.get(url_temp).content
                    datos['media_url'] = subir_a_cloudinary(contenido, "image")
                    datos['text'] = "(Foto de Instagram)"
                    datos['type'] = 'image'
                    datos['media_type'] = 'image'
                elif att['type'] == 'audio':
                     # IG también manda audios, lógica similar podría ir acá
                     datos['text'] = "(Audio de Instagram - No soportado aún)"

        return datos if 'sender_id' in datos else None

    except Exception as e:
        logger.error(f"⚠️ Error normalizando: {e}")
        return None

# --- 3. FUNCIÓN PARA ENVIAR (MULTI-PLATAFORMA) ---
def enviar_respuesta_meta(destinatario_id, texto, plataforma):
    """Envía la respuesta a WhatsApp o Instagram"""
    
    # CASO 1: WHATSAPP (Real)
    if plataforma == 'whatsapp':
        if not META_TOKEN or not META_PHONE_ID: return
        url = f"https://graph.facebook.com/v21.0/{META_PHONE_ID}/messages"
        headers = {"Authorization": f"Bearer {META_TOKEN}", "Content-Type": "application/json"}
        
        # FIX ARGENTINA
        if destinatario_id.startswith("549"):
            destinatario_id = destinatario_id.replace("549", "54", 1)
            
        data = {
            "messaging_product": "whatsapp",
            "to": destinatario_id,
            "type": "text",
            "text": {"body": texto}
        }
        try:
            requests.post(url, headers=headers, json=data, timeout=10)
        except Exception as e:
            logger.error(f"❌ Error enviando WA: {e}")

    # CASO 2: INSTAGRAM (Simulado hasta tener permisos)
    elif plataforma in ['instagram', 'facebook']:
        logger.info(f"🚀 [SIMULACIÓN IG] Enviando a {destinatario_id}: {texto}")

# --- 4. TAREA DE FONDO (LÓGICA PRINCIPAL) ---
def procesar_mensaje_fondo(payload: Dict[Any, Any]):
    try:
        # A. Normalizar
        datos = normalizar_evento(payload)
        if not datos: return

        sender_id = datos['sender_id']
        platform = datos['platform']
        nombre = datos.get('name', 'Desconocido')
        texto_usuario = datos.get('text', '')

        # --- LÓGICA DE AUDIO (WHISPER) 🎤 ---
        # Si detectamos que es un audio y tenemos la URL de Meta
        if datos.get('type') == 'audio' and datos.get('audio_url_meta'):
            logger.info("🎤 Mensaje de Audio detectado. Iniciando transcripción...")
            
            # 1. Descargar audio
            audio_bytes = descargar_media_meta(datos['audio_url_meta'])
            
            if audio_bytes:
                # 2. Guardar en archivo temporal (.ogg es lo que usa WA)
                with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as temp_audio:
                    temp_audio.write(audio_bytes)
                    temp_path = temp_audio.name
                
                # 3. Transcribir con tu función nueva de cerebro.py
                texto_transcrito = cerebro.transcribir_audio(temp_path)
                
                # 4. Limpieza (Borrar archivo temporal del disco)
                try:
                    os.remove(temp_path)
                except: pass
                
                # 5. Reemplazar el texto del usuario con la transcripción
                texto_usuario = texto_transcrito
                logger.info(f"📝 Transcripción final: '{texto_usuario}'")
            else:
                texto_usuario = "(Audio vacío o error de descarga)"

        logger.info(f"📨 {platform.upper()}: {nombre} ({sender_id}) - '{texto_usuario}'")

        with engine.connect() as conn:
            # B. Guardar en Base de Datos
            conn.execute(text("""
                INSERT INTO contacts (client_id, name, platform) VALUES (:cid, :nom, :plat) 
                ON CONFLICT (client_id) DO UPDATE SET last_activity = NOW(), name = :nom
            """), {"cid": sender_id, "nom": nombre, "plat": platform})
            
            conn.execute(text("""
                INSERT INTO messages (contact_id, message_text, media_url, media_type, direction, status, sender_type, created_at)
                VALUES (:cid, :txt, :url, :mtype, 'inbound', 'received', 'user', NOW())
            """), {
                "cid": sender_id, 
                "txt": texto_usuario, # Acá guardamos lo que dijo en el audio
                "url": datos.get('media_url'), 
                "mtype": datos.get('media_type')
            })
            conn.commit()

            # 🛑 FRENO DE MANO
            estado_bot = conn.execute(text("SELECT bot_mode FROM contacts WHERE client_id = :uid"), {"uid": sender_id}).scalar()
            if estado_bot is False:
                logger.info(f"🤐 Bot APAGADO para {sender_id}. Bye.")
                return 

            # C. CEREBRO IA 🧠
            # Recuperar historial
            rows = conn.execute(text("SELECT sender_type, message_text FROM messages WHERE contact_id = :uid ORDER BY created_at DESC LIMIT 6"), {"uid": sender_id}).fetchall()
            historial = [{"role": "assistant" if r[0] in ['bot'] else "user", "content": r[1]} for r in reversed(rows)]
            
            # Contexto extra
            prompt_final = texto_usuario
            notas_contexto = []
            if datos.get('ad_context'):
                notas_contexto.append(f"[SISTEMA: Viene de anuncio: '{datos['ad_context']}']")
            if datos.get('type') == 'audio':
                notas_contexto.append("[SISTEMA: El usuario envió un audio. Respondé natural.]")
            
            if notas_contexto:
                prompt_final += " " + " ".join(notas_contexto)

            # Llamada al cerebro
            respuesta_ia = cerebro.procesar_mensaje(prompt_final, historial)
            texto_resp = respuesta_ia.get('respuesta', '')
            intencion = respuesta_ia.get('intencion', 'General')
            prio = respuesta_ia.get('prioridad', 5)

            # D. Responder
            if texto_resp:
                # Rechequeo seguridad
                rechequeo = conn.execute(text("SELECT bot_mode FROM contacts WHERE client_id = :uid"), {"uid": sender_id}).scalar()
                if rechequeo is False: return

                # Guardar respuesta
                conn.execute(text("""
                    INSERT INTO messages (contact_id, message_text, direction, status, sender_type, intent, priority_score, created_at)
                    VALUES (:cid, :resp, 'outbound', 'generated', 'bot', :intent, :prio, NOW())
                """), {"cid": sender_id, "resp": texto_resp, "intent": intencion, "prio": prio})
                conn.commit()
                
                # ENVIAR
                enviar_respuesta_meta(sender_id, texto_resp, platform)

    except Exception as e:
        logger.error(f"🔥 Error CRÍTICO en background task: {e}")

# --- 5. ENDPOINTS & JSON (F1 ENGINE) ---
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