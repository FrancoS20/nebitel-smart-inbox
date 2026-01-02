import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# --- PASO 1: CONFIGURACIÓN ---
# Cargar las claves del archivo .env (DATABASE_URL)
load_dotenv()
db_url = os.getenv("DATABASE_URL")

# Verificar que la clave exista antes de intentar conectar
if not db_url:
    print("❌ Error: No se encontró DATABASE_URL. Revisa tu archivo .env")
    exit()

# Crear el motor de conexión con Neon (PostgreSQL)
engine = create_engine(db_url)

# --- PASO 2: LOS PLANOS (SQL) ---
sql_commands = """
-- 🧹 SECCIÓN DE LIMPIEZA (RESET)
-- Borramos la tabla de mensajes primero porque depende de contactos.
DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS contacts;

-- 👤 TABLA 1: CONTACTOS (La Agenda)
-- Aquí guardamos QUIÉN nos escribe.
CREATE TABLE contacts (
    client_id VARCHAR(50) PRIMARY KEY,  -- El ID único (Celular para Whatsapp, ID largo para Insta)
    name VARCHAR(100),                  -- Nombre del perfil
    platform VARCHAR(20),               -- De dónde viene: 'whatsapp', 'instagram'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,      -- Cuándo apareció por primera vez
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP    -- Cuándo fue la última vez que habló (Para ordenar)
);

-- 💬 TABLA 2: MENSAJES (La Conversación)
-- Aquí guardamos QUÉ se dijo.
CREATE TABLE messages (
    id SERIAL PRIMARY KEY,              -- ID autoincremental (1, 2, 3...)
    contact_id VARCHAR(50),             -- Vinculación con la tabla contacts
    
    -- EL CONTENIDO
    message_text TEXT,                  -- El texto del mensaje
    media_url TEXT,                     -- El Link a la foto/audio (Si hay)
    media_type VARCHAR(20),             -- Tipo: 'text', 'image', 'audio', 'document'
    
    -- EL CONTEXTO (Quién habla y cómo)
    direction VARCHAR(10),              -- 'inbound' (Cliente nos escribe) o 'outbound' (Nosotros respondemos)
    sender_type VARCHAR(10),            -- 'user' (Cliente), 'bot' (IA), 'human' (Vos)
    
    -- ESTADO Y METADATOS
    priority_score INT DEFAULT 0,       -- Puntuación de importancia (0 a 100)
    status VARCHAR(20) DEFAULT 'received', -- 'received', 'sent', 'read', 'failed'
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Hora exacta
    
    -- REGLA DE SEGURIDAD (Foreign Key)
    -- No permite guardar un mensaje si el cliente no existe en la tabla contacts
    FOREIGN KEY (contact_id) REFERENCES contacts(client_id)
);
"""

# --- PASO 3: LA EJECUCIÓN ---
print("👷 Iniciando construcción de la Base de Datos Omnicanal...")

try:
    # Conectamos con la nube
    with engine.connect() as connection:
        # Ejecutamos las instrucciones SQL
        connection.execute(text(sql_commands))
        connection.commit() # Confirmamos los cambios (Guardar)
        
        print("\n✅ ¡ÉXITO TOTAL! La Base de Datos se actualizó correctamente.")
        print("   1. Tablas viejas eliminadas.")
        print("   2. Tabla 'contacts' creada (Soporte Multi-plataforma).")
        print("   3. Tabla 'messages' creada (Soporte Bot/Humano/Multimedia).")
        print("🚀 Tu servidor Neon está listo para la acción.")

except Exception as e:
    print("\n❌ HUBO UN ERROR:", e)