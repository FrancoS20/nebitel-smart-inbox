import streamlit as st
import pandas as pd
import os
import time
import streamlit.components.v1 as components
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# --- 1. CONFIGURACIÓN INICIAL ---
st.set_page_config(
    page_title="Nebitel CRM",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS
st.markdown("""
<style>
    /* Sidebar Oscura */
    [data-testid="stSidebar"] { background-color: #1a1a1a; border-right: 1px solid #333; }
    
    /* Radio Buttons */
    .stRadio label { color: #e0e0e0 !important; padding: 12px; border-radius: 8px; margin-bottom: 2px; }
    .stRadio label:hover { background-color: #333; cursor: pointer; }
    
    /* Burbujas de Chat */
    .chat-bubble { padding: 12px 16px; border-radius: 12px; margin-bottom: 8px; max-width: 85%; position: relative; font-size: 16px; line-height: 1.4; }
    .user-bubble { background-color: #005c4b; color: white; margin-left: auto; border-top-right-radius: 0; box-shadow: 0 1px 2px rgba(0,0,0,0.3); }
    .bot-bubble { background-color: #202c33; color: white; margin-right: auto; border-top-left-radius: 0; box-shadow: 0 1px 2px rgba(0,0,0,0.3); }
    
    /* Info de hora */
    .meta-info { font-size: 0.70rem; color: rgba(255,255,255,0.6); text-align: right; margin-top: 4px; display: block; }
    
    /* Tarjetas del Dashboard */
    div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] { background-color: #262730; border-radius: 10px; padding: 15px; border: 1px solid #444; }
</style>
""", unsafe_allow_html=True)

# --- 2. GESTIÓN DE ESTADO ---
if 'selected_client' not in st.session_state:
    st.session_state.selected_client = None

# --- 3. CONEXIÓN BASE DE DATOS ---
load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

@st.cache_resource
def get_engine():
    return create_engine(DB_URL)

engine = get_engine()

# --- 4. FUNCIONES DE DATOS ---
def get_sidebar_data():
    """Consulta ultraligera para la barra lateral"""
    sql = text("""
        SELECT 
            contact_id, 
            MAX(created_at) as last_msg, 
            MAX(priority_score) as max_prio,
            (SELECT intent FROM messages m2 WHERE m2.contact_id = messages.contact_id ORDER BY id DESC LIMIT 1) as intent
        FROM messages 
        GROUP BY contact_id 
        ORDER BY last_msg DESC
    """)
    try:
        with engine.connect() as conn:
            return pd.read_sql(sql, conn)
    except Exception:
        return pd.DataFrame()

def get_messages_for_client(client_id):
    sql = text("SELECT * FROM messages WHERE contact_id = :uid ORDER BY created_at ASC")
    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params={"uid": client_id})

def get_global_metrics():
    sql = text("SELECT * FROM messages ORDER BY created_at DESC LIMIT 500")
    with engine.connect() as conn:
        return pd.read_sql(sql, conn)

# --- 5. CALLBACK DE NAVEGACIÓN ---
def actualizar_navegacion():
    seleccion = st.session_state.menu_selector
    if "Tablero General" in seleccion:
        st.session_state.selected_client = None
    else:
        id_limpio = seleccion.split("|")[0].replace("🔥", "").replace("👤", "").strip()
        st.session_state.selected_client = id_limpio

# --- 6. COMPONENTE DE CHAT (FRAGMENTO) ---
@st.fragment(run_every=5)
def render_chat_window(client_id):
    """Chat optimizado sin contenedor interno para scroll nativo"""
    
    df_chat = get_messages_for_client(client_id)
    
    # 1. Header Fijo
    c1, c2 = st.columns([6, 1])
    c1.subheader(f"💬 {client_id}")
    if not df_chat.empty:
        prio = df_chat.iloc[-1]['priority_score']
        if prio >= 8:
            c2.error(f"🔥 {prio}")
        else:
            c2.info(f"ℹ️ {prio}")
    st.divider()

    # 2. Renderizado de Mensajes (Directo en la página, sin caja scrollable)
    if df_chat.empty:
        st.warning("Sin mensajes.")
    else:
        # Bucle optimizado
        chat_html = ""
        for _, row in df_chat.iterrows():
            hora = row['created_at'].strftime('%H:%M')
            if row['direction'] == 'outbound':
                # Nosotros
                st.markdown(f"""
                <div class="chat-bubble user-bubble">
                    {row['message_text']}
                    <span class="meta-info">🦅 {hora}</span>
                </div>
                """, unsafe_allow_html=True)
            else:
                # Cliente
                st.markdown(f"""
                <div class="chat-bubble bot-bubble">
                    {row['message_text']}
                    <span class="meta-info">👤 {hora}</span>
                </div>
                """, unsafe_allow_html=True)

    # 3. Input Simulado
    st.text_input("Responder...", disabled=True, key=f"in_{client_id}", placeholder="Escribí desde WhatsApp...")

    # 4. SCROLL AGRESIVO (El arreglo definitivo) 📜
    # Este script busca el contenedor principal de la app y lo baja hasta el fondo.
    # El timeout de 100ms le da tiempo a las imágenes y burbujas para renderizarse antes de bajar.
    js = f"""
    <script>
        function scrollBottom() {{
            const parts = window.parent.document.querySelectorAll('[data-testid="stAppViewContainer"]');
            if (parts.length > 0) {{
                const main = parts[0];
                setTimeout(() => {{
                    main.scrollTop = main.scrollHeight;
                }}, 150);
            }}
        }}
        scrollBottom();
    </script>
    """
    components.html(js, height=0, width=0)

# --- 7. ESTRUCTURA PRINCIPAL ---

# Sidebar Data
df_clients = get_sidebar_data()
lista_opciones = ["📊 Tablero General"]

if not df_clients.empty:
    for _, row in df_clients.iterrows():
        icono = "🔥" if row['max_prio'] >= 8 else "👤"
        lista_opciones.append(f"{icono} {row['contact_id']} | {row['intent']}")

indice_actual = 0
if st.session_state.selected_client:
    # Búsqueda resiliente (si el estado cambia)
    matches = [i for i, x in enumerate(lista_opciones) if st.session_state.selected_client in x]
    if matches:
        indice_actual = matches[0]

# Render Sidebar
with st.sidebar:
    st.title("🦅 Nebitel CRM")
    if st.button("🔄 Refrescar", use_container_width=True):
        st.rerun()
    
    st.markdown("### 📥 Bandeja")
    
    st.radio(
        "Navegación",
        options=lista_opciones,
        index=indice_actual,
        key="menu_selector",
        on_change=actualizar_navegacion,
        label_visibility="collapsed"
    )

# Render Main Area
if st.session_state.selected_client is None:
    # --- VISTA DASHBOARD ---
    st.title("📊 Panel de Control")
    df_metrics = get_global_metrics()
    
    if not df_metrics.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Mensajes", len(df_metrics))
        hot = len(df_clients[df_clients['max_prio'] >= 8]) if not df_clients.empty else 0
        canje = len(df_clients[df_clients['intent'] == 'Plan Canje']) if not df_clients.empty else 0
        c2.metric("🔥 Clientes Hot", hot)
        c3.metric("📱 Leads Canje", canje)
        
        st.divider()
        st.subheader("🚨 Últimas Alertas")
        
        urgentes = df_metrics[df_metrics['priority_score'] >= 8].head(5)
        if not urgentes.empty:
            for _, row in urgentes.iterrows():
                with st.container(border=True):
                    ic, tx = st.columns([1, 15])
                    with ic: st.markdown("# 🔥")
                    with tx:
                        st.markdown(f"**{row['contact_id']}** • {row['intent']}")
                        st.markdown(f"_{row['message_text']}_")
        else:
            st.success("Sin urgencias.")
else:
    # --- VISTA CHAT ---
    render_chat_window(st.session_state.selected_client)