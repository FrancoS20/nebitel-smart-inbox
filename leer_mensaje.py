import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))

with engine.connect() as conn:
    # Esta consulta une las dos tablas para mostrarte Nombre + Mensaje
    query = text("""
        SELECT c.name, c.platform, m.message_text, m.timestamp 
        FROM messages m
        JOIN contacts c ON m.contact_id = c.client_id
        ORDER BY m.timestamp DESC;
    """)
    
    result = conn.execute(query)
    
    print("\n📨 BANDEJA DE ENTRADA NEBITEL:")
    print("-" * 50)
    for row in result:
        print(f"👤 {row[0]} ({row[1]}): {row[2]}")
        print(f"   🕒 {row[3]}")
        print("-" * 50)