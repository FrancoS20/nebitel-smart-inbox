import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# 1. Configuración inicial
load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))

def recibir_mensaje_simulado(cliente_id, nombre, plataforma, mensaje, es_multimedia=False):
    print(f"\n📩 Simulando mensaje entrante de {nombre} ({plataforma})...")
    
    with engine.connect() as conn:
        # PASO A: Asegurar que el contacto existe
        # Usamos ON CONFLICT DO NOTHING: Si ya existe el ID, no hace nada (no da error).
        sql_contacto = text("""
            INSERT INTO contacts (client_id, name, platform)
            VALUES (:id, :nombre, :plat)
            ON CONFLICT (client_id) DO NOTHING;
        """)
        
        conn.execute(sql_contacto, {"id": cliente_id, "nombre": nombre, "plat": plataforma})
        
        # PASO B: Guardar el mensaje
        # Fíjate que ponemos priority_score en 50 por defecto (todavía no tenemos IA)
        tipo_media = "image" if es_multimedia else "text"
        
        sql_mensaje = text("""
            INSERT INTO messages (contact_id, message_text, media_type, priority_score)
            VALUES (:contact_id, :msg, :media, 50)
        """)
        
        conn.execute(sql_mensaje, {
            "contact_id": cliente_id, 
            "msg": mensaje, 
            "media": tipo_media
        })
        
        conn.commit() # ¡Guardar cambios!
        print("✅ Mensaje guardado en la Base de Datos.")

# --- ZONA DE PRUEBAS ---
if __name__ == "__main__":
    # Vamos a simular que entra un mensaje de WhatsApp
    recibir_mensaje_simulado(
        cliente_id="54911223344", 
        nombre="Juan Pérez", 
        plataforma="whatsapp", 
        mensaje="Hola, necesito presupuesto para un diseño."
    )

    # Vamos a simular que entra otro de Instagram
    recibir_mensaje_simulado(
        cliente_id="insta_user_123", 
        nombre="Maria Design", 
        plataforma="instagram", 
        mensaje="Buenas, ¿hacen envíos?", 
    )