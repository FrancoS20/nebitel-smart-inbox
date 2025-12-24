import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# 1. Cargar las credenciales
load_dotenv()
db_url = os.getenv("DATABASE_URL")

# 2. Conectar
engine = create_engine(db_url)

# 3. Definir los Planos (Actualizado para WhatsApp + Instagram)
sql_commands = """
-- TABLA 1: CONTACTOS (Clientes)
-- Cambiamos 'phone_id' por 'client_id' para que sirva para Insta también.
CREATE TABLE IF NOT EXISTS contacts (
    client_id VARCHAR(50) PRIMARY KEY, -- Puede ser celular (Wsp) o ID de usuario (Insta)
    name VARCHAR(100),                 -- Nombre del perfil
    platform VARCHAR(20),              -- 'whatsapp' o 'instagram' 
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- TABLA 2: MENSAJES (El contenido)
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    contact_id VARCHAR(50),            -- Se vincula con el client_id de arriba
    message_text TEXT,
    media_type VARCHAR(20),            
    priority_score INT DEFAULT 0,      
    status VARCHAR(20) DEFAULT 'received',
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Vinculamos las tablas
    FOREIGN KEY (contact_id) REFERENCES contacts(client_id)
);
"""

# 4. Ejecutar
print("👷 Iniciando la construcción de tablas (Versión Multi-Plataforma)...")

try:
    with engine.connect() as connection:
        connection.execute(text(sql_commands))
        connection.commit()
        print("✅ ¡ÉXITO! Tablas preparadas para recibir WhatsApp e Instagram.")
        
except Exception as e:
    print("❌ Error al crear tablas:", e)