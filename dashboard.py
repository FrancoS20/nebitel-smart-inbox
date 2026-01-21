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

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Nebitel CRM", page_icon="🦅", layout="wide", initial_sidebar_state="expanded")

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")
META_TOKEN = os.getenv("META_TOKEN")
META_PHONE_ID = os.getenv("META_PHONE_ID")
engine = create_engine(DB_URL)

# --- 2. CSS (ESTILO WHATSAPP - PRESERVADO) ---
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    .block-container { padding-top: 3rem !important; padding-bottom: 5rem !important; }
    
    /* Burbujas de Chat */
    .chat-bubble { 
        padding: 8px 12px; 
        border-radius: 8px; 
        margin-bottom: 8px; 
        max-width: 75%; 
        font-size: 15px; 
        position: relative; 
        line-height: 1.4;
        box-shadow: 0 1px 0.5px rgba(0,0,0,0.13);
    }
    .user-bubble { background-color: #202c33; color: white; margin-right: auto; border-top-left-radius: 0; } 
    .human-bubble { background-color: #005c4b; color: white; margin-left: auto; border-top-right-radius: 0; } 
    .bot-bubble { background-color: #1f2c34; color: #00bfa5; margin-left: auto; border-top-right-radius: 0; border: 1px solid #00bfa5; } 
    
    .meta-info { 
        font-size: 0.65rem; 
        color: rgba(255,255,255,0.6); 
        text-align: right; 
        margin-top: 4px; 
        display: block; 
    }
    
    /* Botones de la Sidebar y Listas */
    div.stButton > button { 
        width: 100%; 
        text-align: left; 
        background-color: #111b21; 
        border: 1px solid #2a3942; 
        color: #e9edef; 
        padding: 10px;
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
    except: return False

def switch_bot_status(client_id, nuevo_estado):
    try:
        with engine.connect() as conn:
            conn.execute(text("UPDATE contacts SET bot_mode = :modo WHERE client_id = :id"), {"modo": nuevo_estado, "id": client_id})
            conn.commit()
        st.toast(f"Bot {'ACTIVADO 🟢' if nuevo_estado else 'APAGADO 🔴'}")
    except: pass

# --- 4. GESTIÓN DE VISTAS ---
if 'selected_client' not in st.session_state: st.session_state.selected_client = None
if 'view_category' not in st.session_state: st.session_state.view_category = "all"

def ir_al_chat(cid): st.session_state.selected_client = cid
def volver(): st.session_state.selected_client = None; st.rerun()

# --- 5. COMPONENTES VIVOS (FRAGMENTS) ---

@st.fragment(run_every=2)
def bloque_mensajes(client_id):
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text("SELECT * FROM messages WHERE contact_id = :uid ORDER BY created_at ASC"), conn, params={"uid": client_id})
            df = normalizar_hora(df)
    except: df = pd.DataFrame()

    with st.container(height=550):
        if df.empty:
            st.caption("No hay mensajes aún.")
        else:
            for _, row in df.iterrows():
                hora_str = formatear_fecha(row['created_at'])
                d, s = row['direction'], row['status']
                
                if d == 'inbound': 
                    cls, ico, align = "user-bubble", "", "left"
                elif s == 'sent_by_human': 
                    cls, ico, align = "human-bubble", "✓✓", "right"
                else: 
                    cls, ico, align = "bot-bubble", "🤖", "right"
                
                st.markdown(f'''
                    <div style="display:flex; justify-content:{'flex-end' if align=='right' else 'flex-start'};">
                        <div class="chat-bubble {cls}">
                            {row["message_text"]}
                            <span class="meta-info">{ico} {hora_str}</span>
                        </div>
                    </div>
                ''', unsafe_allow_html=True)
            components.html("<script>var c=window.parent.document.querySelectorAll('.stVerticalBlockBorderWrapper'); if(c.length>0){var l=c[c.length-1];l.scrollTop=l.scrollHeight;}</script>", height=0)

@st.fragment(run_every=5)
def bloque_tablero():
    try:
        with engine.connect() as conn:
            # ORDEN POR PRIORIDAD (max_prio DESC) Y LUEGO HORA (last_msg DESC)
            df = pd.read_sql(text("""
                SELECT contact_id, MAX(created_at) as last_msg, MAX(priority_score) as max_prio,
                (SELECT message_text FROM messages m3 WHERE m3.contact_id = messages.contact_id ORDER BY id DESC LIMIT 1) as last_text,
                (SELECT intent FROM messages m2 WHERE m2.contact_id = messages.contact_id ORDER BY id DESC LIMIT 1) as intent
                FROM messages GROUP BY contact_id ORDER BY max_prio DESC, last_msg DESC
            """), conn)
            if not df.empty:
                df = normalizar_hora(df, 'last_msg')
    except: df = pd.DataFrame()

    if df.empty:
        st.info("Sin mensajes recientes.")
        return

    df['cat'] = df.apply(lambda r: 'ventas' if (str(r['intent']) in ['Plan Canje','Precio','Stock','Compra'] or r['max_prio']>=8) else ('tecnico' if str(r['intent']) in ['Tecnico','Reparación','Falla'] else 'varios'), axis=1)

    vista = st.session_state.view_category
    cols = st.columns(3)
    titulos = ["🔥 Oportunidades", "🛠️ Soporte", "💬 General"]
    keys = ['ventas','tecnico','varios']
    
    if vista == 'all':
        for i in range(3):
            with cols[i]:
                st.markdown(f"**{titulos[i]}**")
                sub_df = df[df['cat'] == keys[i]]
                if sub_df.empty: st.caption("Vacío")
                for _, r in sub_df.iterrows():
                    h = formatear_fecha(r['last_msg'])
                    lbl = f"**{r['contact_id']}** ({h})\n\n_{r['last_text'][:40]}..._"
                    if st.button(lbl, key=f"k_{r['contact_id']}"):
                        ir_al_chat(r['contact_id']); st.rerun()
    else:
        st.subheader(f"Filtrado: {vista.upper()}")
        df_show = df[df['cat'] == vista]
        for _, r in df_show.iterrows():
            h = formatear_fecha(r['last_msg'])
            col1, col2 = st.columns([4, 1])
            with col1:
                st.info(f"👤 **{r['contact_id']}** | {h}\n\n{r['last_text']}")
            with col2:
                if st.button("Abrir Chat", key=f"f_{r['contact_id']}"):
                     ir_al_chat(r['contact_id']); st.rerun()

# --- 6. SIDEBAR RECARGADA ---
@st.fragment(run_every=10) # Se actualiza cada 10s para no molestar
def render_sidebar():
    st.markdown("### 🦅 Nebitel CRM")
    if st.button("🏠 Inicio", use_container_width=True): volver()
    
    st.divider()
    st.caption("RECIENTES (Tiempo Real)")
    
    try:
        with engine.connect() as conn:
            # La Sidebar ordena por TIEMPO (last_msg DESC) para ser funcional
            df_side = pd.read_sql(text("""
                SELECT contact_id, MAX(created_at) as last_msg, MAX(priority_score) as prio 
                FROM messages GROUP BY contact_id ORDER BY last_msg DESC LIMIT 15
            """), conn)
    except: df_side = pd.DataFrame()
    
    if not df_side.empty:
        for _, row in df_side.iterrows():
            # Si es prioridad alta (>8) le ponemos un fueguito
            icono = "🔥" if row['prio'] >= 8 else "👤"
            lbl = f"{icono} {row['contact_id']}"
            if st.button(lbl, key=f"side_{row['contact_id']}", use_container_width=True):
                ir_al_chat(row['contact_id'])
                st.rerun()

# --- 7. LAYOUT PRINCIPAL ---

with st.sidebar:
    render_sidebar()

if st.session_state.selected_client:
    # VISTA CHAT
    client_id = st.session_state.selected_client
    with engine.connect() as conn:
        bot_on = conn.execute(text("SELECT bot_mode FROM contacts WHERE client_id=:id"), {"id":client_id}).scalar()
        if bot_on is None: bot_on = True

    c1, c2, c3 = st.columns([1, 8, 3])
    with c1: 
        if st.button("⬅", help="Volver"): volver()
    with c2: st.markdown(f"### 💬 {client_id}")
    with c3:
        nuevo_estado = st.toggle("🤖 Bot Activo", value=bot_on, key=f"tg_{client_id}")
        if nuevo_estado != bot_on:
            switch_bot_status(client_id, nuevo_estado)
            time.sleep(0.1)
            st.rerun()

    st.divider()
    bloque_mensajes(client_id)
    
    texto = st.chat_input(f"Responder a {client_id}...")
    if texto:
        if enviar_whatsapp(client_id, texto):
            st.rerun()
else:
    # VISTA DASHBOARD
    c_title, c_ref = st.columns([8, 1])
    with c_title: st.title("🦅 Nebitel Smart Inbox")
    with c_ref: 
        if st.button("🔄"): st.rerun()
    
    cf = st.columns(4)
    opts = [('all','Todo'), ('ventas','Ventas'), ('tecnico','Soporte'), ('varios','Otros')]
    for i, (k, l) in enumerate(opts):
        estilo = "primary" if st.session_state.view_category==k else "secondary"
        if cf[i].button(l, type=estilo, use_container_width=True):
            st.session_state.view_category = k; st.rerun()
    
    st.divider()
    bloque_tablero()