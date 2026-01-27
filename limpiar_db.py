import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# 1. Cargar el link desde el archivo .env
load_dotenv()
url = os.getenv("DATABASE_URL")

# 2. Truquito para Neon: Si el link dice "postgres://", lo cambiamos a "postgresql://"
# para que Python no se queje.
if url and url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)

# Si no encuentra nada, avisa
if not url:
    print("❌ ERROR: No encontré la DATABASE_URL en el archivo .env")
    exit()

# Conectar
engine = create_engine(url)

def limpiar_todo():
    print(f"🔌 Conectando a la base de datos...")
    
    # Mostramos el host para confirmar que es Neon (ocultando la contraseña)
    try:
        host = url.split("@")[1].split("/")[0]
        print(f"🌍 Servidor detectado: {host} (Neon/Nube)")
    except:
        print("🌍 Servidor detectado: (No pude leer el host, pero conectado)")

    try:
        with engine.connect() as conn:
            # 1. Borrar MENSAJES
            print("🗑️  Eliminando mensajes...")
            conn.execute(text("DELETE FROM messages"))
            
            # 2. Borrar CONTACTOS (Opcional, descomentar si querés borrar clientes también)
            # print("🗑️  Eliminando contactos...")
            # conn.execute(text("DELETE FROM contacts"))
            
            conn.commit()
            
        print("✨ ¡Listo! La base de datos en Neon quedó limpia.")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    confirmacion = input("⚠️  Vas a borrar los datos de la NUBE (Neon). ¿Seguro? (escribí 'si'): ")
    if confirmacion.lower() == 'si':
        limpiar_todo()
    else:
        print("🛑 Cancelado.")