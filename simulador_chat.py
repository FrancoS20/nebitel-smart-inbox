import os
from sqlalchemy import create_engine, inspect
from dotenv import load_dotenv
import pandas as pd

# 1. Cargar configuración
load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

if not DB_URL:
    print("❌ Error: No encontré DATABASE_URL en el archivo .env")
    exit()

# 2. Conectar
try:
    engine = create_engine(DB_URL)
    inspector = inspect(engine)
    print("✅ Conexión exitosa a la Base de Datos.\n")
except Exception as e:
    print(f"❌ Error conectando: {e}")
    exit()

# 3. Obtener Tablas
tablas = inspector.get_table_names()

print(f"📊 TABLAS ENCONTRADAS: {len(tablas)}")
print("="*40)

for tabla in tablas:
    print(f"\n📂 TABLA: {tabla.upper()}")
    print("-" * 40)
    
    # Obtener columnas
    columnas = inspector.get_columns(tabla)
    
    # Armar lista linda para mostrar
    data = []
    for col in columnas:
        # Detectar si es Primary Key (aunque inspector no lo da directo en get_columns, lo inferimos visualmente)
        # O mejor, usamos get_pk_constraint
        es_pk = ""
        pk_info = inspector.get_pk_constraint(tabla)
        if col['name'] in pk_info.get('constrained_columns', []):
            es_pk = "🔑 PK"
            
        # Detectar Foreign Keys
        es_fk = ""
        fks = inspector.get_foreign_keys(tabla)
        for fk in fks:
            if col['name'] in fk['constrained_columns']:
                es_fk = f"🔗 FK -> {fk['referred_table']}.{fk['referred_columns'][0]}"

        data.append({
            "Columna": col['name'],
            "Tipo": str(col['type']),
            "Nulo?": "Sí" if col['nullable'] else "No",
            "Clave": f"{es_pk} {es_fk}".strip()
        })
    
    # Mostrar con Pandas para que quede alineado perfecto
    df = pd.DataFrame(data)
    print(df.to_string(index=False))
    print("-" * 40)

print("\n✅ Fin del reporte.")