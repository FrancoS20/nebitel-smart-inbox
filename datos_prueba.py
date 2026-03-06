import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Carga tu DATABASE_URL desde el archivo .env
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ Error: No se encontró DATABASE_URL en el .env")
    exit()

print("🔌 Conectando a la base de datos...")
engine = create_engine(DATABASE_URL)

# La inyección de clientes falsos
query = text("""
    INSERT INTO contacts (client_id, name, last_message, bot_mode, category, priority)
    VALUES 
        ('5493431111111', 'Matias', 'Hola, a cuánto toman un S20 para canje?', true, 'Venta', 9),
        ('5493432222222', 'Laura', 'Se me astilló la pantalla del iPhone 11, lo arreglan en calle Zanni?', true, 'Tecnico', 7),
        ('5493433333333', 'Carlos', 'A qué hora abren hoy a la tarde?', true, 'General', 2),
        ('5493434444444', 'Sofia', 'No me entiende el bot, pasame con un humano urgente!!', false, 'General', 10);
""")

try:
    with engine.connect() as conn:
        conn.execute(query)
        conn.commit()
        print("✅ ¡ÉXITO! Se inyectaron 4 chats de prueba. Refrescá tu dashboard.")
except Exception as e:
    print(f"❌ Hubo un error al inyectar los datos: {e}")