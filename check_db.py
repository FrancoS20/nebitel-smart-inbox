import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

try:
    engine = create_engine(DB_URL)
    inspector = inspect(engine)
    tablas = inspector.get_table_names()
    print(f"✅ Tablas en Neon: {tablas}")
    for t in tablas:
        print(f"\n📊 COLUMNAS DE {t}:")
        for col in inspector.get_columns(t):
            print(f"   - {col['name']} ({col['type']})")
except Exception as e:
    print(f"❌ Error: {e}")