import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Cargar claves
load_dotenv()
db_url = os.getenv("DATABASE_URL")

if not db_url:
    print("❌ ERROR: No se encontró DATABASE_URL en el archivo .env")
else:
    try:
        # Intentar conectar
        engine = create_engine(db_url)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            print("🎉 ¡ÉXITO TOTAL! Tu Python ya está conectado a la Nube de Neon.")
    except Exception as e:
        print("❌ Error de conexión:", e)