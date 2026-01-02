import os
import logging
from fastapi import FastAPI, Request, HTTPException
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from mensajeria import enviar_mensaje_whatsapp

# --- CONFIGURACIÓN ---
load_dotenv()
TOKEN_VERIFICACION = os.getenv("META_VERIFY_TOKEN")
DB_URL = os.getenv("DATABASE_URL")

# Configurar Logs (Para ver mensajes en la pantalla negra)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Conectar a la Base de Datos
engine = create_engine(DB_URL)
app = FastAPI()

# --- RUTAS ---
@app.get("/")
async def home():
    return {"status": "Nebitel Smart Inbox V2 Activo 🚀"}

# 1. VERIFICACIÓN DE META (El saludo inicial)
@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == TOKEN_VERIFICACION:
        logger.info("✅ Verificación de Webhook exitosa")
        return int(params.get("hub.challenge"))
    logger.error("❌ Falló la verificación del token")
    raise HTTPException(status_code=403, detail="Token inválido")

# 2. RECEPCIÓN DE MENSAJES (La magia)
@app.post("/webhook")
async def receive_message(request: Request):
    data = await request.json()
    
    try:
        # Navegamos el JSON que manda Facebook
        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]
        
        # ¿Es un mensaje nuevo?
        if "messages" in value:
            message_data = value["messages"][0]
            contact_data = value["contacts"][0]
            
            # --- DATOS DEL CLIENTE ---
            client_id = contact_data["wa_id"]           # Teléfono (Ej: 549343...)
            name = contact_data["profile"]["name"]      # Nombre (Ej: Franco)
            platform = "whatsapp"
            
            sender_type = 'user'
            
            # --- DATOS DEL MENSAJE ---
            msg_type = message_data.get("type")
            text_body = ""
            media_url = None
            
            # Extraer contenido según el tipo
            if msg_type == "text":
                text_body = message_data["text"]["body"]
            else:
                text_body = f"[{msg_type.upper()}] Archivo recibido"
                # (Aquí a futuro procesaremos la URL de la imagen)

            logger.info(f"📩 Mensaje de {name}: {text_body}")

            # --- GUARDAR EN BASE DE DATOS OMNICANAL ---
            with engine.connect() as connection:
                # A. Guardamos al Contacto (Si ya existe, actualizamos la fecha)
                sql_contact = text("""
                    INSERT INTO contacts (client_id, name, platform, last_activity)
                    VALUES (:id, :name, :plat, NOW())
                    ON CONFLICT (client_id) 
                    DO UPDATE SET name = :name, last_activity = NOW()
                """)
                connection.execute(sql_contact, {"id": client_id, "name": name, "plat": platform})
                
                # B. Guardamos el Mensaje (Con las columnas nuevas)
                sql_msg = text("""
                    INSERT INTO messages (contact_id, message_text, media_type, direction, sender_type, status)
                    VALUES (:id, :body, :type, 'inbound', 'user', 'received')
                """)
                connection.execute(sql_msg, {"id": client_id, "body": text_body, "type": msg_type})
                
                connection.commit() # Confirmar guardado
                logger.info("💾 Guardado correctamente en DB Nueva.")
                # --- 🤖 RESPUESTA AUTOMÁTICA (MODO PRUEBA) ---
                # Por ahora, repetimos lo que dijo el usuario para probar que "habla"
                if sender_type == 'user': # Solo respondemos si nos habla un humano, no a nosotros mismos
                    logger.info("🗣️ Nebitel intentando responder...")
                    respuesta = f"🤖 Recibí tu mensaje: '{text_body}'. (Guardado en DB)"
                
                    # Llamamos a la función asíncrona (await es clave)
                    await enviar_mensaje_whatsapp(client_id, respuesta)
                    
                    # Guardamos nuestra respuesta en la base de datos también
                    sql_outbound = text("""
                        INSERT INTO messages (contact_id, message_text, direction, sender_type, status)
                        VALUES (:id, :body, 'outbound', 'bot', 'sent')
                    """)
                    connection.execute(sql_outbound, {"id": client_id, "body": respuesta})
                    connection.commit()
                    logger.info("💾 Respuesta del Bot guardada en DB.")

    except Exception as e:
        logger.error(f"⚠️ Error procesando: {e}")
        pass # No le decimos a Meta que falló para que no nos bloquee

    return {"status": "received"}

# --- ARRANQUE DEL SERVIDOR ---
if __name__ == "__main__":
    import uvicorn
    print("🚀 Iniciando servidor Nebitel...")
    uvicorn.run(app, host="0.0.0.0", port=8000)