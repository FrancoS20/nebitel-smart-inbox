import os
import requests
from dotenv import load_dotenv

# 1. Cargar las credenciales del archivo .env
load_dotenv()

token = os.getenv("META_TOKEN")
phone_id = os.getenv("META_PHONE_ID")
recipient_phone = os.getenv("META_RECIPIENT_PHONE")

# Verificamos que todo esté cargado antes de disparar
if not token or not phone_id or not recipient_phone:
    print("❌ ERROR: Faltan datos en el archivo .env")
    print(f"Token: {'OK' if token else 'Falta'}")
    print(f"Phone ID: {'OK' if phone_id else 'Falta'}")
    print(f"Recipient: {'OK' if recipient_phone else 'Falta'}")
    exit()

# 2. Configurar la URL y el Mensaje (Payload)
url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

# Usamos la plantilla "hello_world" que Meta te regala por defecto
data = {
    "messaging_product": "whatsapp",
    "to": recipient_phone,
    "type": "template",
    "template": {
        "name": "hello_world",
        "language": {"code": "en_US"}
    }
}

# 3. ¡DISPARAR! 🔫
print(f"📨 Enviando mensaje a {recipient_phone} desde ID {phone_id}...")

try:
    response = requests.post(url, headers=headers, json=data)
    
    # 4. Analizar la respuesta
    if response.status_code == 200:
        print("\n✅ ¡ÉXITO TOTAL! 🚀")
        print("El mensaje fue enviado. ¡Chequeá tu WhatsApp!")
        print("Respuesta de Meta:", response.json())
    else:
        print("\n❌ HUBO UN PROBLEMA:")
        print(f"Status Code: {response.status_code}")
        print("Detalle del error:", response.text)

except Exception as e:
    print(f"\n💥 Error de conexión: {e}")