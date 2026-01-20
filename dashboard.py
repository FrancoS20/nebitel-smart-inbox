import streamlit as st
import pandas as pd
import os
import requests
import time
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

# --- 2. CSS (UI KIT) ---
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    .block-container { padding-top: 3rem !important; padding-bottom: 5rem !important; }
    
    /* Burbujas */
    .chat-bubble { padding: 8px 12px; border-radius: 8px; margin-bottom: 5px; max-width: 80%; font-size: 14px; position: relative; }
    .user-bubble { background-color: #005c4b; color: white; margin-left: auto; border-top-right-radius: 0; }
    .bot-bubble { background-color: #202c33; color: white; margin-right: auto; border-top-left-radius: 0; }
    .human-bubble { background-color: #007bff; color: white; margin-left: auto; border-top-right-radius: 0; border: 1px solid #0056b3; }
    
    .meta-info { font-size: 0.65rem; color: rgba(255,255,255,0.5); text-align: right; margin-top: 4px; display: block; }
    
    /* Botones y Tarjetas */
    div.stButton > button { width: 100%; text-align: left; background-color: #1e1e1e; border: 1px solid #333; color: #e0e0e0; }
    div.stButton > button:hover { border-color: #00a884; background-color: #2a2a2a; }
</style>
""", unsafe_allow_html=True)

# --- 3. FUNCIONES DE BACKEND ---

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

# A. EL CHAT EN VIVO (Se actualiza solo cada 2 segundos SIN tocar el input)
@st.fragment(run_every=2)
def bloque_mensajes(client_id):
    # Consulta rápida
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text("SELECT * FROM messages WHERE contact_id = :uid ORDER BY created_at ASC"), conn, params={"uid": client_id})
    except: df = pd.DataFrame()

    with st.container(height=520):
        if df.empty:
            st.info("No hay mensajes aún.")
        else:
            for _, row in df.iterrows():
                h = row['created_at'].strftime('%H:%M')
                d, s = row['direction'], row['status']
                
                # Lógica de colores
                if d == 'inbound': cls, ico = "user-bubble", "🦅" # Cliente
                elif s == 'sent_by_human': cls, ico = "human-bubble", "👨‍💻" # Vos
                else: cls, ico = "bot-bubble", "👤" # Bot
                
                st.markdown(f'<div class="chat-bubble {cls}">{row["message_text"]}<span class="meta-info">{ico} {h}</span></div>', unsafe_allow_html=True)
            
            # JS Scroll (Solo se ejecuta si hay mensajes nuevos)
            components.html("<script>var c=window.parent.document.querySelectorAll('.stVerticalBlockBorderWrapper'); if(c.length>0){var l=c[c.length-1];l.scrollTop=l.scrollHeight;}</script>", height=0)

# B. EL TABLERO EN VIVO (Se actualiza cada 5 segundos)
@st.fragment(run_every=5)
def bloque_tablero():
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text("""
                SELECT contact_id, MAX(created_at) as last_msg, MAX(priority_score) as max_prio,
                (SELECT message_text FROM messages m3 WHERE m3.contact_id = messages.contact_id ORDER BY id DESC LIMIT 1) as last_text,
                (SELECT intent FROM messages m2 WHERE m2.contact_id = messages.contact_id ORDER BY id DESC LIMIT 1) as intent
                FROM messages GROUP BY contact_id ORDER BY last_msg DESC
            """), conn)
    except: df = pd.DataFrame()

    if df.empty:
        st.info("Esperando mensajes... (Auto-Sync Activo)")
        return

    # Categorización
    df['cat'] = df.apply(lambda r: 'ventas' if (str(r['intent']) in ['Plan Canje','Precio','Stock'] or r['max_prio']>=8) else ('tecnico' if str(r['intent']) in ['Tecnico','Reparación'] else 'varios'), axis=1)

    # Render Columnas
    cols = st.columns(3)
    titulos = ["🔥 Ventas", "🛠️ Técnico", "❓ Varios"]
    keys = ['ventas','tecnico','varios']
    
    # Usamos session_state global para el filtro (se mantiene entre refrescos)
    vista = st.session_state.view_category
    
    if vista == 'all':
        for i in range(3):
            with cols[i]:
                st.markdown(f"##### {titulos[i]}")
                for _, r in df[df['cat']==keys[i]].iterrows():
                    # Usamos un callback para evitar recargas innecesarias
                    if st.button(f"{r['contact_id']}\n\n_{r['last_text'][:30]}..._", key=f"k_{r['contact_id']}"):
                        ir_al_chat(r['contact_id'])
                        st.rerun()
    else:
        # Vista filtrada
        st.caption(f"Filtrado por: {vista.upper()}")
        df_f = df[df['cat'] == vista]
        cx = st.columns(3)
        for i, (_, r) in enumerate(df_f.iterrows()):
            with cx[i%3]:
                if st.button(f"{r['contact_id']}\n\n_{r['last_text'][:30]}..._", key=f"f_{r['contact_id']}"):
                    ir_al_chat(r['contact_id'])
                    st.rerun()

# --- 6. ESTRUCTURA PRINCIPAL (LAYOUT ESTATICO) ---

if st.session_state.selected_client:
    # --- VISTA CHAT ---
    client_id = st.session_state.selected_client
    
    # 1. Header (Estático)
    with engine.connect() as conn:
        bot_on = conn.execute(text("SELECT bot_mode FROM contacts WHERE client_id=:id"), {"id":client_id}).scalar()
        if bot_on is None: bot_on = True

    c1, c2, c3 = st.columns([1, 10, 3])
    with c1: 
        if st.button("⬅", help="Volver"): volver()
    with c2: st.markdown(f"**💬 {client_id}**")
    with c3:
        # Toggle Bot (Con lógica de actualización manual para no romper el flujo)
        nuevo_estado = st.toggle("🤖 Bot", value=bot_on, key=f"tg_{client_id}")
        if nuevo_estado != bot_on:
            switch_bot_status(client_id, nuevo_estado)
            time.sleep(0.2)
            st.rerun()

    st.divider()

    # 2. Bloque de Mensajes (AUTO-ACTUALIZABLE EN SEGUNDO PLANO)
    bloque_mensajes(client_id)

    # 3. Input de Escritura (ESTÁTICO - No se recarga solo)
    texto = st.chat_input(f"Escribir a {client_id}...")
    if texto:
        if enviar_whatsapp(client_id, texto):
            st.rerun() # Acá sí forzamos update para ver nuestro propio mensaje al instante

else:
    # --- VISTA DASHBOARD ---
    st.markdown("### 📊 Panel de Control")
    
    # Filtros (Estáticos)
    cf = st.columns(4)
    for i, (k, l) in enumerate(zip(['all','ventas','tecnico','varios'], ['Todo','Ventas','Tec','Varios'])):
        if cf[i].button(l, type="primary" if st.session_state.view_category==k else "secondary"):
            st.session_state.view_category = k; st.rerun()
    
    st.divider()
    
    # Tablero (AUTO-ACTUALIZABLE)
    bloque_tablero()

# Sidebar fija
with st.sidebar:
    st.markdown("### 🦅 Nebitel CRM")
    if st.button("🏠 Inicio", use_container_width=True): volver()