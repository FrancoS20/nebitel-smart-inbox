import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# --- CONFIGURACIÓN ---
load_dotenv()
db_url = os.getenv("DATABASE_URL")

if not db_url:
    print("❌ Error: No se encontró DATABASE_URL en el .env")
    exit()

engine = create_engine(db_url)

# --- EL ESQUEMA CORREGIDO (CONSISTENCIA TOTAL) ---
sql_commands = """
-- 1. LIMPIEZA (Borrar lo viejo)
DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS contacts;

-- 2. TABLA CONTACTOS
CREATE TABLE contacts (
    client_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100),
    platform VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- ✅ Usamos created_at
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. TABLA MENSAJES
CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    contact_id VARCHAR(50),
    
    -- Contenido
    message_text TEXT,
    media_url TEXT,
    media_type VARCHAR(20),
    
    -- Contexto
    direction VARCHAR(10),   -- 'inbound' / 'outbound'
    sender_type VARCHAR(10), -- 'user' / 'bot' / 'human'
    
    -- Metadatos
    priority_score INT DEFAULT 0,
    status VARCHAR(20) DEFAULT 'received',
    
    -- ✅ CORRECCIÓN DEFINITIVA: 
    -- Ahora se llama 'created_at' igual que en contacts y en tu código Python.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
    
    -- Relación
    FOREIGN KEY (contact_id) REFERENCES contacts(client_id)
);
"""

# --- EJECUCIÓN ---
print("👷 Estandarizando Base de Datos (created_at en todo)...")

try:
    with engine.connect() as connection:
        connection.execute(text(sql_commands))
        connection.commit()
        
        print("\n✅ ¡LISTO! Tablas sincronizadas.")
        print("   - Tabla 'contacts': Usa 'created_at'")
        print("   - Tabla 'messages': Usa 'created_at'")
        print("   - Python 'webhook.py': Busca 'created_at'")
        print("🚀 Todo coincide. Reinicia tu servidor.")

except Exception as e:
    print("\n❌ Error:", e)