import requests
import json

# URL de tu webhook (Usamos la local para que sea instantáneo)
url = "http://127.0.0.1:8000/webhook"

# --- DATOS DEL "ACTOR" (El usuario falso de Instagram) ---
payload = {
    "object": "instagram",
    "entry": [
        {
            "messaging": [
                {
                    "sender": {
                        "id": "123456789_INSTA_USER"  # ID Falso de Instagram
                    },
                    "recipient": {
                        "id": "987654321_NEBITEL"
                    },
                    "timestamp": 123456789,
                    "message": {
                        "mid": "mid.12345",
                        "text": "Hola, vi la promo en Instagram y quiero info"
                    },
                    # --- SIMULAMOS QUE VIENE DE PUBLICIDAD ---
                    "referral": {
                        "ref": "promo_verano_2026",
                        "source": "AD",
                        "type": "OPEN_THREAD"
                    }
                }
            ]
        }
    ]
}

print("🎭 Enviando mensaje falso de Instagram...")

try:
    # Enviamos el POST request (tal cual lo haría Meta)
    response = requests.post(url, json=payload)
    
    if response.status_code == 200:
        print("✅ ¡ÉXITO! El servidor recibió el mensaje.")
        print("👉 Mirá la terminal donde corre uvicorn para ver la respuesta.")
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)

except Exception as e:
    print(f"🔥 Error de conexión: {e}")
    print("¿Tenés prendido el uvicorn?")