import streamlit as st
import pandas as pd
import os
import requests
import time
import pytz 
from datetime import datetime
import streamlit.components.v1 as components
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import cerebro

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Nebitel CRM", page_icon="🦅", layout="wide", initial_sidebar_state="expanded")

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")
META_TOKEN = os.getenv("META_TOKEN")
META_PHONE_ID = os.getenv("META_PHONE_ID")

if not DB_URL:
    st.error("❌ Falta DATABASE_URL en el .env")
    st.stop()

engine = create_engine(DB_URL)

# --- 2. CSS (ESTILO WHATSAPP) ---
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    .block-container { padding-top: 2rem !important; padding-bottom: 5rem !important; }
    
    /* Burbujas */
    .chat-bubble { 
        padding: 10px 14px; 
        border-radius: 10px; 
        margin-bottom: 8px; 
        max-width: 70%; 
        font-size: 15px; 
        line-height: 1.4;
        box-shadow: 0 1px 1px rgba(0,0,0,0.2);
    }
    .user-bubble { background-color: #202c33; color: white; margin-right: auto; border-top-left-radius: 0; } 
    .human-bubble { background-color: #005c4b; color: white; margin-left: auto; border-top-right-radius: 0; } 
    .bot-bubble { background-color: #1f2c34; color: #00bfa5; margin-left: auto; border-top-right-radius: 0; border: 1px solid #00bfa5; } 
    
    .meta-info { 
        font-size: 0.7rem; 
        color: rgba(255,255,255,0.5); 
        text-align: right; 
        margin-top: 4px; 
        display: block; 
    }
    
    /* Botones Sidebar */
    div.stButton > button { 
        width: 100%; 
        text-align: left; 
        background-color: #111b21; 
        border: 1px solid #2a3942; 
        color: #e9edef; 
        padding: 12px;
        border-radius: 8px;
        transition: all 0.2s;
    }
    div.stButton > button:hover { border-color: #00a884; background-color: #202c33; }
</style>
""", unsafe_allow_html=True)

# --- 3. FUNCIONES DE UTILIDAD ---

def normalizar_hora(df, columna='created_at'):
    """Convierte UTC a Hora Argentina"""
    if df.empty: return df
    arg_tz = pytz.timezone('America/Argentina/Buenos_Aires')
    df[columna] = pd.to_datetime(df[columna])
    if df[columna].dt.tz is None:
        df[columna] = df[columna].dt.tz_localize('UTC').dt.tz_convert(arg_tz)
    else:
        df[columna] = df[columna].dt.tz_convert(arg_tz)
    return df

def formatear_fecha(timestamp):
    if pd.isnull(timestamp): return ""
    ahora = datetime.now(pytz.timezone('America/Argentina/Buenos_Aires'))
    if timestamp.date() == ahora.date():
        return timestamp.strftime('%H:%M')
    return timestamp.strftime('%d/%m %H:%M')

def enviar_whatsapp(telefono, texto):
    if not META_TOKEN: return False
    destinatario = telefono.replace("549", "54", 1) if telefono.startswith("549") else telefono
    url = f"https://graph.facebook.com/v21.0/{META_PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {META_TOKEN}", "Content-Type": "application/json"}
    try:
        res = requests.post(url, headers=headers, json={"messaging_product": "whatsapp", "to": destinatario, "type": "text", "text": {"body": texto}})
        if res.status_code == 200:
            with engine.connect() as conn:
                conn.execute(text("INSERT INTO messages (contact_id, message_text, direction, status, intent, priority_score, created_at) VALUES (:cel, :msg, 'outbound', 'sent_by_human', 'Human Reply', 0, NOW())"), {"cel": telefono, "msg": texto})
                conn.execute(text("UPDATE contacts SET bot_mode = FALSE WHERE client_id = :cel"), {"cel": telefono})
                conn.commit()
            return True
        return False
    except Exception as e:
        print(f"Error enviando: {e}")
        return False

def switch_bot_status(client_id, nuevo_estado):
    try:
        with engine.connect() as conn:
            # 1. Actualizamos el estado del bot (ON/OFF)
            conn.execute(text("UPDATE contacts SET bot_mode = :modo WHERE client_id = :id"), {"modo": nuevo_estado, "id": client_id})
            conn.commit()
            
            # 2. SI ACTIVAMOS EL BOT (ON): Hacemos la "Auditoría Silenciosa"
            if nuevo_estado is True:
                st.toast("🕵️‍♂️ La IA está re-evaluando el caso...")
                
                # A. Recuperamos los últimos 10 mensajes para dar contexto
                rows = conn.execute(text("""
                    SELECT sender_type, message_text 
                    FROM messages 
                    WHERE contact_id = :uid 
                    ORDER BY created_at DESC LIMIT 10
                """), {"uid": client_id}).fetchall()
                
                # Formateamos para el cerebro (invertimos porque el SQL trae del más nuevo al más viejo)
                historial = [{"role": r[0], "content": r[1]} for r in reversed(rows)]
                
                # B. Llamamos al Auditor
                analisis = cerebro.analizar_prioridad_silenciosa(historial)
                nueva_prio = analisis.get('prioridad', 1)
                nueva_intencion = analisis.get('intencion', 'Revisión')
                
                # C. Actualizamos la base de datos con la NUEVA realidad
                conn.execute(text("""
                    UPDATE messages 
                    SET priority_score = :p, intent = :i 
                    WHERE contact_id = :id AND id = (SELECT MAX(id) FROM messages WHERE contact_id = :id)
                """), {"p": nueva_prio, "i": nueva_intencion, "id": client_id})
                
                conn.commit()
                st.toast(f"✅ Re-clasificado: Prioridad {nueva_prio} ({nueva_intencion})")

    except Exception as e: 
        st.error(f"Error: {e}")

# --- 4. GESTIÓN DE VISTAS ---
if 'selected_client' not in st.session_state: st.session_state.selected_client = None
if 'view_category' not in st.session_state: st.session_state.view_category = "all"

def ir_al_chat(cid): st.session_state.selected_client = cid
def volver(): st.session_state.selected_client = None; st.rerun()

# --- 5. COMPONENTES VIVOS (FRAGMENTS) ---

@st.fragment(run_every=3)
def bloque_mensajes(client_id):
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text("SELECT * FROM messages WHERE contact_id = :uid ORDER BY created_at ASC"), conn, params={"uid": client_id})
            df = normalizar_hora(df)
    except: df = pd.DataFrame()

    with st.container(height=600):
        if df.empty:
            st.info("📭 No hay mensajes aún.")
        else:
            for _, row in df.iterrows():
                hora_str = formatear_fecha(row['created_at'])
                d, s = row['direction'], row['status']
                
                # Definir estilos
                if d == 'inbound': 
                    cls, ico, align = "user-bubble", "", "left"
                elif s == 'sent_by_human': 
                    cls, ico, align = "human-bubble", "👨‍💻", "right"
                else: 
                    cls, ico, align = "bot-bubble", "🤖", "right"
                
                # Intent tag
                extra_tag = ""
                if row['sender_type'] == 'bot' and row.get('intent'):
                     extra_tag = f"<br><span style='font-size:0.6rem; color:#00bfa5;'>🧠 {row['intent']}</span>"

                # --- CORRECCIÓN DEFINITIVA: HTML EN UNA SOLA LÍNEA ---
                # Esto evita que Python/Streamlit piensen que es código por la indentación
                html_code = f'''<div style="display:flex; justify-content:{'flex-end' if align=='right' else 'flex-start'};"><div class="chat-bubble {cls}">{row["message_text"]}{extra_tag}<span class="meta-info">{ico} {hora_str}</span></div></div>'''
                
                st.markdown(html_code, unsafe_allow_html=True)
            
            # Scroll automático
            components.html("<script>var c=window.parent.document.querySelectorAll('.stVerticalBlockBorderWrapper'); if(c.length>0){var l=c[c.length-1];l.scrollTop=l.scrollHeight;}</script>", height=0)

@st.fragment(run_every=5)
def bloque_tablero():
    try:
        with engine.connect() as conn:
            # Traemos la plataforma y el estado del bot
            df = pd.read_sql(text("""
                SELECT 
                    m.contact_id, 
                    MAX(m.created_at) as last_msg, 
                    MAX(COALESCE(m.priority_score, 0)) as max_prio,
                    (SELECT message_text FROM messages m3 WHERE m3.contact_id = m.contact_id ORDER BY id DESC LIMIT 1) as last_text,
                    (SELECT intent FROM messages m2 WHERE m2.contact_id = m.contact_id ORDER BY id DESC LIMIT 1) as intent,
                    c.bot_mode,
                    c.platform
                FROM messages m
                JOIN contacts c ON m.contact_id = c.client_id
                GROUP BY m.contact_id, c.bot_mode, c.platform
                ORDER BY max_prio DESC, last_msg DESC
            """), conn)
            
            if not df.empty:
                df = normalizar_hora(df, 'last_msg')
    except Exception as e: 
        df = pd.DataFrame()

    if df.empty:
        st.info("Sin mensajes recientes.")
        return

    # --- HELPERS DE ÍCONOS ---
    def get_plat_label(plat_raw):
        p = str(plat_raw).lower()
        if 'instagram' in p: return "📸 Insta"
        if 'facebook' in p or 'messenger' in p: return "💬 Msgr"
        return "📱 WhatsApp" # Por defecto

    # --- CLASIFICACIÓN ---
    def clasificar(r):
        intent = str(r['intent'])
        if intent in ['Plan Canje','Precio','Stock','Compra','Venta'] or r['max_prio'] >= 8:
            return 'ventas'
        elif intent in ['Tecnico','Reparación','Falla','Soporte']:
            return 'tecnico'
        return 'varios'

    df['cat'] = df.apply(clasificar, axis=1)
    vista = st.session_state.view_category
    
    # --- VISTA COLUMNAS (KANBAN) ---
    if vista == 'all':
        cols = st.columns(3)
        titulos = ["🔥 Oportunidades", "🛠️ Soporte", "💬 General"]
        keys = ['ventas','tecnico','varios']
        
        for i in range(3):
            with cols[i]:
                st.markdown(f"##### {titulos[i]}")
                sub_df = df[df['cat'] == keys[i]]
                if sub_df.empty: st.caption("Vacío")
                
                for _, r in sub_df.iterrows():
                    h = formatear_fecha(r['last_msg'])
                    
                    # 1. Identificamos la Plataforma
                    plat_label = get_plat_label(r['platform'])
                    
                    # 2. Identificamos el Estado del Bot (🟢 o 🔴)
                    bot_icon = "🟢" if r['bot_mode'] else "🔴"
                    
                    # 3. Armamos la Tarjeta
                    # Ejemplo: 📱 WhatsApp | **549343...** 🟢
                    lbl = f"{plat_label} | **{r['contact_id']}** {bot_icon}\n\n_{str(r['last_text'])[:35]}..._\n\n🕒 {h}"

                    if st.button(lbl, key=f"card_{r['contact_id']}"):
                        ir_al_chat(r['contact_id']); st.rerun()
    
    # --- VISTA FILTRO (LISTA) ---
    else:
        st.subheader(f"📂 {vista.upper()}")
        df_show = df[df['cat'] == vista]
        for _, r in df_show.iterrows():
            h = formatear_fecha(r['last_msg'])
            
            plat_label = get_plat_label(r['platform'])
            bot_icon = "🟢" if r['bot_mode'] else "🔴"
            
            lbl = f"{plat_label} | {r['contact_id']} {bot_icon} | {h}\n\n{r['last_text']}"
            
            if st.button(lbl, key=f"list_{r['contact_id']}"):
                ir_al_chat(r['contact_id']); st.rerun()

# --- 6. SIDEBAR (Con Indicador Numérico) ---
@st.fragment(run_every=5)
def render_sidebar():
    st.title("🦅 Nebitel")
    if st.button("🏠 Tablero Principal", use_container_width=True): volver()
    st.divider()
    st.caption("CHATS RECIENTES")
    
    try:
        with engine.connect() as conn:
            df_side = pd.read_sql(text("""
                SELECT m.contact_id, MAX(m.created_at) as last_msg, c.bot_mode, MAX(m.priority_score) as prio
                FROM messages m
                JOIN contacts c ON m.contact_id = c.client_id
                GROUP BY m.contact_id, c.bot_mode
                ORDER BY last_msg DESC LIMIT 15
            """), conn)
    except: df_side = pd.DataFrame()
    
    if not df_side.empty:
        for _, row in df_side.iterrows():
            # 1. Aseguramos que el puntaje sea un número (si es None ponemos 0)
            puntaje = int(row['prio']) if row['prio'] else 0
            
            # 2. Definimos el Ícono
            if puntaje >= 8:
                icon = "🔥" # Prioridad Alta
            elif not row['bot_mode']:
                icon = "🔴" # Bot Apagado
            else:
                icon = "👤" # Normal
            
            # 3. Armamos la etiqueta: ÍCONO + [PUNTAJE] + TELÉFONO
            # Ejemplo: 🔥 [10] 549343...
            lbl = f"{icon} [{puntaje}] {row['contact_id']}"
            
            if st.button(lbl, key=f"side_{row['contact_id']}", use_container_width=True):
                ir_al_chat(row['contact_id']); st.rerun() 

# --- 7. LAYOUT PRINCIPAL ---
with st.sidebar:
    render_sidebar()

if st.session_state.selected_client:
    client_id = st.session_state.selected_client
    with engine.connect() as conn:
        bot_on = conn.execute(text("SELECT bot_mode FROM contacts WHERE client_id=:id"), {"id":client_id}).scalar()
        if bot_on is None: bot_on = True

    c1, c2, c3 = st.columns([1, 6, 3])
    with c1: 
        if st.button("⬅", help="Volver"): volver()
    with c2: 
        st.markdown(f"### 💬 {client_id}")
    with c3:
        label = "🤖 Bot ACTIVO" if bot_on else "🛑 Bot APAGADO"
        nuevo = st.toggle(label, value=bot_on, key=f"tg_{client_id}")
        if nuevo != bot_on:
            switch_bot_status(client_id, nuevo)
            time.sleep(0.1); st.rerun()

    st.divider()
    bloque_mensajes(client_id)
    
    texto = st.chat_input(f"Escribí tu respuesta para {client_id}...")
    if texto:
        if enviar_whatsapp(client_id, texto): st.rerun()
else:
    c_title, c_ref = st.columns([8, 1])
    with c_title: st.title("Smart Inbox 📥")
    with c_ref: 
        if st.button("🔄"): st.rerun()
    
    cf = st.columns(4)
    opts = [('all','Todo'), ('ventas','💰 Ventas'), ('tecnico','🛠️ Soporte'), ('varios','💤 Otros')]
    for i, (k, l) in enumerate(opts):
        est = "primary" if st.session_state.view_category==k else "secondary"
        if cf[i].button(l, type=est, use_container_width=True):
            st.session_state.view_category = k; st.rerun()
    
    st.divider()
    bloque_tablero()