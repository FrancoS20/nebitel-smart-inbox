import requests
import json

# 1. Poné tu TOKEN PERMANENTE acá adentro (entre las comillas)
TOKEN_META = "EAAQWTcqUHwQBQ4LSXP1iAwEKHMxWR6fAyHrbGpZCcYZCPtNAxC7bKwlASYMPKNy3SKDbC8bbVg3PutXZC4eSpwPplw3guj1cq3WTl4jW9UwvVZB7iHADpU7tPFCyQwuGKq4d8dLwZA3bLAq2x38MDenC4TcSWHrShJ8LDZCFznItCNuo2RY3E2ZAog7LiHAuQZDZD"

# 2. Tu número de teléfono y el ID de teléfono de Meta (ya te los dejé puestos)
NUMERO_DESTINO = "5493434689521"
PHONE_NUMBER_ID = "970497739488622"

url = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"

headers = {
    "Authorization": f"Bearer {TOKEN_META}",
    "Content-Type": "application/json"
}

data = {
    "messaging_product": "whatsapp",
    "to": NUMERO_DESTINO,
    "type": "template",
    "template": {
        "name": "hello_world",
        "language": {
            "code": "en_US"
        }
    }
}

print("Enviando mensaje de prueba a WhatsApp...")
response = requests.post(url, headers=headers, data=json.dumps(data))

print(f"Código de respuesta: {response.status_code}")
print(f"Respuesta de Meta: {response.text}")