import os
import httpx
import logging
from dotenv import load_dotenv

# Configuración
load_dotenv()
TOKEN = os.getenv("META_TOKEN")
PHONE_NUMBER_ID = os.getenv("META_PHONE_ID")
VERSION = "v21.0"

logger = logging.getLogger(__name__)

async def enviar_mensaje_whatsapp(numero_destino: str, texto: str):
    """
    Envía un mensaje de texto a un usuario de WhatsApp.
    """
    url = f"https://graph.facebook.com/{VERSION}/{PHONE_NUMBER_ID}/messages"
    
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    
    data = {
        "messaging_product": "whatsapp",
        "to": numero_destino,
        "type": "text",
        "text": {"body": texto}
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=data, headers=headers)
            
            if response.status_code == 200:
                logger.info(f"📤 Mensaje enviado a {numero_destino}")
                return True
            else:
                logger.error(f"❌ Error enviando mensaje: {response.text}")
                return False
                
    except Exception as e:
        logger.error(f"⚠️ Excepción al enviar mensaje: {e}")
        return False