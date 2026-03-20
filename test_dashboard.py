import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")
engine = create_engine(DB_URL)

print("🌪️ Preparando la Tormenta Nivel 5: Inyectando caos en la base de datos...")

with engine.connect() as conn:
    # 1. Limpiamos pruebas anteriores para que quede el tablero limpio
    conn.execute(text("DELETE FROM messages WHERE contact_id LIKE 'TEST_%' OR contact_id LIKE 'CHAOS_%'"))
    conn.execute(text("DELETE FROM contacts WHERE client_id LIKE 'TEST_%' OR client_id LIKE 'CHAOS_%'"))
    
    # 2. Creamos 7 contactos distintos (WhatsApp, IG, FB, con y sin bot)
    conn.execute(text("""
        INSERT INTO contacts (client_id, name, platform, bot_mode)
        VALUES 
        ('CHAOS_IG_LEAD', 'Usuario IG', 'instagram', TRUE),
        ('CHAOS_FURIA', 'Cliente Enojado', 'whatsapp', TRUE),
        ('CHAOS_OLVIDADO', 'El Colgado FB', 'facebook', TRUE),
        ('CHAOS_TRANQUI', 'Mirando Vidriera', 'whatsapp', TRUE),
        ('CHAOS_HUMANO', 'Atendido por Franco', 'whatsapp', FALSE),  -- Bot Apagado
        ('CHAOS_SPAM', 'El que dice OK', 'instagram', TRUE),
        ('CHAOS_ANUNCIO', 'Lead de Publicidad', 'instagram', TRUE)
        ON CONFLICT (client_id) DO NOTHING;
    """))

    # 3. Inyectamos los mensajes simulando distintos horarios e intenciones
    mensajes = [
        # El olvidado: FB, hace 4 horas. Prioridad 6. Debería explotar de puntos por la espera.
        ("CHAOS_OLVIDADO", "Hola, te pregunté a la mañana por el S23, tienen al final?", "Venta", 6, "4 hours"),
        
        # El Furioso: WA, hace 15 minutos. Prioridad 10. Debería estar súper alto en Soporte.
        ("CHAOS_FURIA", "Loco, el modulo que me cambiaron ayer no anda el tactil. Quiero una solucion YA.", "Tecnico", 10, "15 minutes"),
        
        # El del Anuncio: IG, hace 45 minutos. Trae el tag de anuncio de Meta.
        ("CHAOS_ANUNCIO", "Viene del anuncio: Promo iPhone 13. Hola quiero info", "Venta", 7, "45 minutes"),
        
        # El Atendido: WA, hace 1 hora, el bot está apagado (vas a ver el punto rojo).
        ("CHAOS_HUMANO", "Bueno, paso por el local a las 18hs entonces. Gracias Franco.", "Tecnico", 5, "1 hour"),
        
        # El Spam: IG, hace 10 horas. Prioridad 1. NO DEBE SUMAR PUNTOS nunca.
        ("CHAOS_SPAM", "👍 Dale buenisimo rey", "General", 1, "10 hours"),
        
        # El Tranqui: WA, hace 2 minutos. Recién entra.
        ("CHAOS_TRANQUI", "hola, a que hora abren a la tarde?", "General", 4, "2 minutes"),
        
        # IG Lead: Mandó dos mensajes. El último es hace 30 min. (Prueba si lee el último msj bien).
        ("CHAOS_IG_LEAD", "tienen fundas?", "Venta", 5, "35 minutes"),
        ("CHAOS_IG_LEAD", "y templado para el moto g52?", "Venta", 6, "30 minutes")
    ]

    for cid, msg, intent, prio, tiempo in mensajes:
        conn.execute(text(f"""
            INSERT INTO messages (contact_id, message_text, direction, status, sender_type, intent, priority_score, created_at)
            VALUES ('{cid}', '{msg}', 'inbound', 'unread', 'user', '{intent}', {prio}, NOW() - INTERVAL '{tiempo}')
        """))

    conn.commit()

print("✅ ¡Tormenta inyectada con éxito! Actualizá tu Streamlit y preparate para ver la magia.")