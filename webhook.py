# webhook.py
import os
import uvicorn
from fastapi import FastAPI, Request, HTTPException, status
from dotenv import load_dotenv
from simulador_chat import recibir_mensaje_simulado # Reusamos tu lógica probada

# Cargar variables de entorno
load_dotenv()

app = FastAPI(title="Nebitel Smart Inbox API")

# Configuración
VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "nebitel_secreto_2025")

@app.get("/webhook", status_code=200)
async def verificar_token(request: Request):
    """
    Endpoint de Verificación (Handshake).
    Meta llama a esto UNA sola vez para confirmar que el servidor es tuyo.
    """
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    # Verificación estricta según documentación de Meta
    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            print("✅ Conexión con Meta verificada exitosamente.")
            return int(challenge) # Se debe devolver el challenge como entero/texto
        else:
            print("❌ Intento de verificación fallido: Token incorrecto.")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="Token de verificación incorrecto"
            )
    
    # Si no mandan nada, es un error
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Faltan parámetros")

@app.post("/webhook", status_code=200)
async def recibir_notificacion(request: Request):
    """
    Endpoint de Recepción (Inbound).
    Aquí llegan los mensajes de WhatsApp en tiempo real.
    """
    data = await request.json()
    
    # Imprimimos el payload para debug (esto lo quitaremos en producción real para no ensuciar logs)
    # print("📦 Payload recibido:", data) 

    try:
        # Navegamos la estructura JSON compleja de WhatsApp Cloud API
        # Documentación: entry -> changes -> value -> messages
        entry = data.get('entry', [])[0]
        changes = entry.get('changes', [])[0]
        value = changes.get('value', {})
        
        # Verificamos si es un mensaje (y no un estado de "leído" o "escribiendo")
        if 'messages' in value:
            mensaje_data = value['messages'][0]
            contact_data = value.get('contacts', [{}])[0]
            
            # Extracción de datos limpios
            telefono_cliente = mensaje_data.get('from') # ID del usuario (wa_id)
            nombre_cliente = contact_data.get('profile', {}).get('name', 'Desconocido')
            tipo_mensaje = mensaje_data.get('type')

            texto_mensaje = ""
            es_multimedia = False

            # Manejo básico de tipos de mensaje
            if tipo_mensaje == 'text':
                texto_mensaje = mensaje_data['text']['body']
            elif tipo_mensaje in ['image', 'audio', 'document']:
                texto_mensaje = f"[{tipo_mensaje} recibido]"
                es_multimedia = True
            
            print(f"📩 Nuevo Mensaje de {nombre_cliente}: {texto_mensaje}")
            
            # --- GUARDADO EN BASE DE DATOS ---
            # Llamamos a tu función existente en simulador_chat.py
            recibir_mensaje_simulado(
                cliente_id=telefono_cliente,
                nombre=nombre_cliente,
                plataforma="whatsapp",
                mensaje=texto_mensaje,
                es_multimedia=es_multimedia
            )
            
    except IndexError:
        # El payload no tenía la estructura esperada (puede ser un ping de status)
        pass
    except Exception as e:
        print(f"⚠️ Error procesando webhook: {e}")

    # Siempre devolver 200 OK a Meta, o te bloquearán el webhook
    return {"status": "received"}

if __name__ == "__main__":
    # En producción real, esto no se corre con python webhook.py, sino con gunicorn/uvicorn desde la terminal
    print("🚀 Iniciando Servidor de Producción Nebitel (Local)...")
    uvicorn.run(app, host="0.0.0.0", port=8000)