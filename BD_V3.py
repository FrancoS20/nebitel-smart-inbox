import os
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index, text
from sqlalchemy.orm import declarative_base
from dotenv import load_dotenv

# --- 1. CONFIGURACIÓN DE PRODUCCIÓN ---
load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

if not DB_URL:
    print("❌ Error: DATABASE_URL no encontrada.")
    exit()

# pool_pre_ping asegura que la conexión no se caiga en servidores como Koyeb/Render
engine = create_engine(DB_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)
Base = declarative_base()

print("🦅 NEBITEL SCHEMA V3.0 - PRODUCTION READY 🦅")

# --- 2. TABLA DE CONTACTOS ---
class Contact(Base):
    __tablename__ = 'contacts'

    client_id = Column(String(255), primary_key=True) # Soporta BSUID y Teléfonos
    name = Column(String(150), nullable=True)        # Aquí guardaremos el nombre real
    phone_number = Column(String(50), nullable=True) 
    platform = Column(String(20), nullable=False)    # whatsapp, instagram, messenger
    
    # Timestamps inteligentes
    created_at = Column(DateTime(timezone=True), server_default=text('NOW()'))
    last_activity = Column(DateTime(timezone=True), server_default=text('NOW()'), onupdate=text('NOW()'))
    
    bot_mode = Column(Boolean, default=True)         # Control manual/IA

# --- 3. TABLA DE MENSAJERÍA ---
class Message(Base):
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    contact_id = Column(String(255), ForeignKey('contacts.client_id', ondelete='CASCADE'), nullable=False)
    
    message_text = Column(Text, nullable=True)
    direction = Column(String(10), nullable=False)   # inbound / outbound
    sender_type = Column(String(10), nullable=False) # user / bot / human
    
    # Multimedia (Clave para Cloudinary)
    media_url = Column(Text, nullable=True)          # Link permanente de Cloudinary
    media_type = Column(String(20), nullable=True)   # image, audio, video, document
    
    # Inteligencia y Metadatos
    priority_score = Column(Integer, default=0)
    intent = Column(String(50), nullable=True)
    status = Column(String(20), default='received')
    message_category = Column(String(50), default='service') # Para costos de Meta
    created_at = Column(DateTime(timezone=True), server_default=text('NOW()'))

    # Índices para que el Dashboard vuele (aunque haya miles de mensajes)
    __table_args__ = (
        Index('idx_chat_history', 'contact_id', 'created_at'),
        Index('idx_priority_inbox', 'priority_score', 'created_at'),
    )

def setup_production_db():
    try:
        print("⚠️  Limpiando base de datos de prueba...")
        Base.metadata.drop_all(engine)
        
        print("🏗️  Construyendo tablas de producción...")
        Base.metadata.create_all(engine)
        print("✅ ¡Sistema de base de datos listo para salir a producción!")
    except Exception as e:
        print(f"❌ Error crítico: {e}")

if __name__ == "__main__":
    setup_production_db()