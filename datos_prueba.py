import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import random
from datetime import datetime, timedelta

# Cargar entorno
load_dotenv()
DB_URL = os.getenv("DATABASE_URL")
engine = create_engine(DB_URL)

# Datos simulados (Celular, Mensaje, Dirección, Intención, Prioridad)
clientes = [
    ("5491122334455", "Hola, me toman un iPhone 11 en parte de pago?", "outbound", "Plan Canje", 9),
    ("5491155667788", "Necesito cambiar la batería de un 7 Plus", "inbound", "Tecnico", 6),
    ("5491199887766", "A qué hora cierran hoy?", "inbound", "Horarios", 3),
    ("5491144332211", "Tienen stock del 14 Pro morado?", "inbound", "Stock", 8),
    ("5493430001122", "El celular me calienta mucho cuando carga", "inbound", "Tecnico", 7),
    ("5493411122334", "VENDEN FUNDAS?", "inbound", "Varios", 2),
]

def inyectar_datos():
    print("💉 Inyectando pacientes falsos al CRM...")
    
    with engine.connect() as conn:
        for cel, msg, direction, intent, prio in clientes:
            try:
                # PASO 1: Crear el contacto (Usando 'client_id' que es lo que pide tu base)
                # Agregamos 'platform' = 'whatsapp' para completar
                sql_contact = text("""
                    INSERT INTO contacts (client_id, name, platform, created_at)
                    VALUES (:cel, 'Cliente Test', 'whatsapp', NOW())
                    ON CONFLICT (client_id) DO NOTHING
                """)
                conn.execute(sql_contact, {"cel": cel})
                conn.commit()

                # PASO 2: Crear el mensaje
                minutos_atras = random.randint(1, 20)
                fecha = datetime.now() - timedelta(minutes=minutos_atras)
                
                sql_msg = text("""
                    INSERT INTO messages (contact_id, message_text, direction, status, intent, priority_score, created_at)
                    VALUES (:cel, :msg, :dir, 'received', :intent, :prio, :fecha)
                """)
                
                conn.execute(sql_msg, {
                    "cel": cel, "msg": msg, "dir": direction, 
                    "intent": intent, "prio": prio, "fecha": fecha
                })
                conn.commit()
                
                print(f"✅ Cargado: {cel} - {intent}")
                
            except Exception as e:
                print(f"❌ Error con {cel}: {e}")
                conn.rollback()

    print("✨ ¡Listo! Ahora andá al Dashboard y tocá 'Refrescar'.")

if __name__ == "__main__":
    inyectar_datos()