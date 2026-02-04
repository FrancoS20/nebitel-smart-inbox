import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# 1. Cargar el link desde el archivo .env
load_dotenv()
url = os.getenv("DATABASE_URL")

if not url:
    print("❌ ERROR: No encontré la DATABASE_URL en el archivo .env")
    exit()

# Conectar
engine = create_engine(url)

def limpiar_todo():
    print(f"🔌 Conectando a la base de datos...")
    
    try:
        with engine.connect() as conn:
            # 1. Borrar MENSAJES (Siempre primero, porque dependen de los contactos)
            print("🗑️  Eliminando TODOS los mensajes...")
            conn.execute(text("DELETE FROM messages"))
            
            # 2. Borrar CONTACTOS (Ahora sí, descomentado)
            print("🗑️  Eliminando TODOS los contactos...")
            conn.execute(text("DELETE FROM contacts"))
            
            # Confirmar cambios
            conn.commit()
            
        print("✨ ¡Listo! Base de datos vacía (Tablas messages y contacts quedaron en 0).")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    confirmacion = input("⚠️  ATENCIÓN: Se borrarán TODOS los clientes y chats. ¿Seguro? (escribí 'si'): ")
    if confirmacion.lower() == 'si':
        limpiar_todo()
    else:
        print("🛑 Cancelado.")