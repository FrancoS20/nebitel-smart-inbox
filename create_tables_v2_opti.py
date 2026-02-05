import os
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index, text
from sqlalchemy.orm import declarative_base, relationship
from dotenv import load_dotenv
from datetime import datetime

# --- 1. CONFIGURACIÓN ---
load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

if not DB_URL:
    print("❌ Error: Falta DATABASE_URL en el .env")
    exit()

# Usamos la configuración optimizada también aquí para mantener el estándar
engine = create_engine(DB_URL, pool_pre_ping=True)
Base = declarative_base()

print("🦅 DEFINICIÓN DE ESQUEMA V2 (OPTIMIZADO) 🦅")
print("===========================================")

# --- 2. MODELO DE CONTACTOS ---
class Contact(Base):
    __tablename__ = 'contacts'

    # Columnas
    client_id = Column(String(50), primary_key=True) # El número de teléfono (ej: 549343...)
    name = Column(String(100), nullable=True)
    platform = Column(String(20), nullable=True)     # whatsapp, instagram, messenger
    created_at = Column(DateTime, server_default=text('NOW()'))
    last_activity = Column(DateTime, server_default=text('NOW()'))
    bot_mode = Column(Boolean, default=True)         # True = Bot responde / False = Humano responde

    # ÍNDICES (Optimizaciones aplicadas el 29/01/2026)
    __table_args__ = (
        # Acelera el Sidebar: Ordenar contactos por actividad y estado del bot
        Index('idx_contacts_last_activity_prio', 'last_activity', 'bot_mode'),
    )

# --- 3. MODELO DE MENSAJES ---
class Message(Base):
    __tablename__ = 'messages'

    # Columnas
    id = Column(Integer, primary_key=True, autoincrement=True)
    contact_id = Column(String(50), ForeignKey('contacts.client_id'))
    message_text = Column(Text, nullable=True)
    
    # Multimedia (Audios, Fotos)
    media_url = Column(Text, nullable=True)
    media_type = Column(String(20), nullable=True) # image, audio, document
    
    # Metadatos del Chat
    direction = Column(String(10), nullable=False)   # inbound (Entra) / outbound (Sale)
    sender_type = Column(String(10), nullable=False) # user / bot / human
    priority_score = Column(Integer, default=0)      # 0 a 10 (10 = Venta caliente)
    status = Column(String(20), default='received')  # received, sent, read
    created_at = Column(DateTime, server_default=text('NOW()'))
    
    # Cerebro / IA
    intent = Column(String(50), nullable=True)             # Venta, Soporte, Saludo
    conversation_status = Column(String(20), default='open') # open, closed, pending

    # ÍNDICES (Optimizaciones aplicadas el 29/01/2026)
    __table_args__ = (
        # Acelera el Chat Individual: Buscar mensajes de UN cliente ordenados por FECHA
        Index('idx_messages_contact_date', 'contact_id', 'created_at'),
        
        # Acelera el Tablero Kanban: Agrupar por prioridad y fecha
        Index('idx_messages_prio_date', 'priority_score', 'created_at'),
    )

# --- 4. EJECUCIÓN ---
def crear_tablas():
    try:
        # Esto crea las tablas SOLO si no existen.
        # Si ya existen, no borra nada, pero asegura que SQLAlchemy conozca el modelo.
        Base.metadata.create_all(engine)
        print("✅ Esquema verificado. (Si las tablas no existían, se crearon. Si existían, se respetaron).")
        print("🚀 Los índices de optimización están definidos en el modelo.")
    except Exception as e:
        print(f"❌ Error creando tablas: {e}")

if __name__ == "__main__":
    crear_tablas()