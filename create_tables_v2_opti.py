import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# 1. Configuración
load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

if not DB_URL:
    print("❌ Error: Falta DATABASE_URL")
    exit()

engine = create_engine(DB_URL)

print("🦅 APLICANDO OPTIMIZACIÓN NIVEL 2 (COMPOSITE INDEXES) 🦅")
print("=======================================================")

# Estos índices son "Quirúrgicos" basados en tu informe
indices_premium = [
    # 1. EL ÍNDICE MAESTRO PARA EL CHAT
    # Acelera: "Dame los mensajes de ESTE cliente, ordenados por FECHA DESC"
    # Este es el que usa tu función bloque_mensajes() todo el tiempo.
    """
    CREATE INDEX IF NOT EXISTS idx_messages_contact_date 
    ON messages(contact_id, created_at DESC);
    """,

    # 2. EL ÍNDICE PARA EL TABLERO (Dashboard)
    # Acelera: Buscar el último mensaje (created_at) agrupado por prioridad.
    """
    CREATE INDEX IF NOT EXISTS idx_messages_prio_date 
    ON messages(priority_score DESC, created_at DESC);
    """,

    # 3. EL ÍNDICE PARA EL SIDEBAR (Lista de contactos)
    # Acelera: Mostrar contactos ordenados por última actividad.
    """
    CREATE INDEX IF NOT EXISTS idx_contacts_last_activity_prio 
    ON contacts(last_activity DESC, bot_mode);
    """
]

with engine.connect() as conn:
    for sql in indices_premium:
        try:
            # Limpiamos nombre para el print
            nombre_idx = sql.split("EXISTS")[1].split("ON")[0].strip()
            print(f"⚙️  Creando Super Índice: {nombre_idx}...")
            conn.execute(text(sql))
            print("   ✅ Creado (o ya existía).")
        except Exception as e:
            print(f"   ❌ Error: {e}")
            # Si falla, seguimos con el siguiente
            continue
    
    conn.commit()

print("\n🚀 Base de Datos blindada para velocidad.")