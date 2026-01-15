import streamlit as st
import pandas as pd
import os
import streamlit.components.v1 as components
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# --- 1. CONFIGURACIÓN ---
st.set_page_config(
    page_title="Nebitel CRM",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. ESTILOS CSS (CORREGIDOS) ---
st.markdown("""
<style>
    /* 1. FONDO Y SIDEBAR */
    .stApp { background-color: #0e1117; }
    [data-testid="stSidebar"] { background-color: #1a1a1a; border-right: 1px solid #333; }

    /* 2. ESPACIADO SUPERIOR (EL ARREGLO CLAVE) */
    /* Antes era 1rem y se escondía detrás del menú. Ahora 3.5rem es el punto dulce. */
    .block-container {
        padding-top: 3.5rem !important; 
        padding-bottom: 1rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: 100% !important;
    }
    
    /* 3. BURBUJAS DE CHAT */
    .chat-bubble { padding: 8px 12px; border-radius: 8px; margin-bottom: 5px; max-width: 85%; font-size: 14px; line-height: 1.4; }
    .user-bubble { background-color: #005c4b; color: white; margin-left: auto; border-top-right-radius: 0; }
    .bot-bubble { background-color: #202c33; color: white; margin-right: auto; border-top-left-radius: 0; }
    .meta-info { font-size: 0.65rem; color: rgba(255,255,255,0.5); text-align: right; margin-top: 2px; display: block; }
    
    /* 4. BOTONES GENÉRICOS */
    div.stButton > button {
        width: 100%;
        border-radius: 6px;
        border: 1px solid #333;
        background-color: #1e1e1e;
        color: #e0e0e0;
        text-align: left;
        padding: 10px;
        transition: all 0.2s;
    }
    div.stButton > button:hover {
        border-color: #00a884;
        background-color: #2a2a2a;
    }

    /* 5. HEADER DEL CHAT (Ajustado para que se vea bien el número) */
    .chat-header {
        font-size: 1.2rem;
        font-weight: 600;
        color: white;
        margin: 0;
        padding-top: 2px; /* Alineación fina con el botón */
    }
    
    /* 6. TÍTULO COMPACTO */
    .compact-title {
        font-size: 1.4rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. GESTIÓN DE ESTADO ---
if 'selected_client' not in st.session_state:
    st.session_state.selected_client = None
if 'view_category' not in st.session_state:
    st.session_state.view_category = "all"

# --- 4. BASE DE DATOS ---
load_dotenv()
DB_URL = os.getenv("DATABASE_URL")
engine = create_engine(DB_URL)

# --- 5. FUNCIONES ---

def ir_al_chat(client_id):
    st.session_state.selected_client = client_id

def volver_al_tablero():
    st.session_state.selected_client = None
    st.rerun()

def cambiar_filtro(categoria):
    st.session_state.view_category = categoria

def get_data_dashboard():
    try:
        sql = text("""
            SELECT 
                contact_id, 
                MAX(created_at) as last_msg, 
                MAX(priority_score) as max_prio,
                (SELECT intent FROM messages m2 WHERE m2.contact_id = messages.contact_id ORDER BY id DESC LIMIT 1) as intent,
                (SELECT message_text FROM messages m3 WHERE m3.contact_id = messages.contact_id ORDER BY id DESC LIMIT 1) as last_text
            FROM messages 
            GROUP BY contact_id 
            ORDER BY max_prio DESC, last_msg DESC 
        """)
        with engine.connect() as conn:
            return pd.read_sql(sql, conn)
    except Exception:
        return pd.DataFrame()

def clasificar_categoria(row):
    intent = str(row['intent'])
    prio = row['max_prio']
    if intent in ['Plan Canje', 'Precio', 'Stock', 'Compra'] or prio >= 8:
        return 'ventas'
    elif intent in ['Tecnico', 'Reparación', 'Garantía']:
        return 'tecnico'
    else:
        return 'varios'

# --- 6. FRAGMENTO DE CHAT ---
@st.fragment(run_every=4)
def render_chat_window(client_id):
    
    # HEADER (Ahora con columnas más anchas para que no se corte el botón)
    # [1, 15] le da suficiente espacio al botón para no cortarse
    c1, c2 = st.columns([1, 15]) 
    
    with c1:
        if st.button("⬅", help="Volver", key="btn_back_chat", use_container_width=True):
            volver_al_tablero()
    with c2:
        # El número debería aparecer ahora porque bajamos el padding general
        st.markdown(f'<p class="chat-header">💬 {client_id}</p>', unsafe_allow_html=True)
    
    st.markdown("<hr style='margin-top: 0.5rem; margin-bottom: 0.5rem; border-color: #333;'>", unsafe_allow_html=True)

    try:
        sql = text("SELECT * FROM messages WHERE contact_id = :uid ORDER BY created_at ASC")
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn, params={"uid": client_id})
    except:
        df = pd.DataFrame()

    # Altura ajustada a 650 para asegurar que entre en laptops sin scroll doble
    container_height = 650 
    
    with st.container(height=container_height):
        if df.empty:
            st.info("Inicio.")
        else:
            for _, row in df.iterrows():
                hora = row['created_at'].strftime('%H:%M')
                if row['direction'] == 'outbound':
                    st.markdown(f"""
                    <div class="chat-bubble user-bubble">
                        {row['message_text']}
                        <span class="meta-info">🦅 {hora}</span>
                    </div>""", unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="chat-bubble bot-bubble">
                        {row['message_text']}
                        <span class="meta-info">👤 {hora}</span>
                    </div>""", unsafe_allow_html=True)
            
            # Script Scroll
            js = f"""
            <script>
                function scrollDown() {{
                    const scrollers = window.parent.document.querySelectorAll('.stVerticalBlockBorderWrapper');
                    if (scrollers.length > 0) {{
                        const chat = scrollers[scrollers.length - 1];
                        chat.scrollTop = chat.scrollHeight;
                    }}
                }}
                scrollDown();
                setTimeout(scrollDown, 100);
            </script>
            """
            components.html(js, height=0)

    st.text_input("Responder...", placeholder="Escribí aquí...", disabled=True, key="fake_input", label_visibility="collapsed")

# --- 7. SIDEBAR ---
df_data = get_data_dashboard()

with st.sidebar:
    st.markdown('<p class="compact-title">🦅 Nebitel CRM</p>', unsafe_allow_html=True)
    
    c_ref, c_home = st.columns(2)
    with c_ref:
        if st.button("🔄 Refrescar", use_container_width=True): st.rerun()
    with c_home:
        if st.button("🏠 Inicio", use_container_width=True): volver_al_tablero()
    
    st.caption("Filtros Rápidos")
    if st.button(f"🔥 Ventas ({len(df_data[df_data.apply(clasificar_categoria, axis=1)=='ventas']) if not df_data.empty else 0})", use_container_width=True):
        st.session_state.view_category = 'ventas'
        st.session_state.selected_client = None
        st.rerun()
        
    st.caption("Recientes")
    if not df_data.empty:
        for _, row in df_data.head(5).iterrows():
            lbl = f"{'🔥' if row['max_prio']>=8 else '👤'} {row['contact_id'][-4:]}..."
            if st.button(lbl, key=f"s_{row['contact_id']}", use_container_width=True):
                ir_al_chat(row['contact_id'])
                st.rerun()

# --- 8. LÓGICA PRINCIPAL ---

if st.session_state.selected_client:
    render_chat_window(st.session_state.selected_client)
else:
    # VISTA TABLERO
    # Este título debería ser visible ahora
    st.markdown('<p class="compact-title">📊 Panel de Control</p>', unsafe_allow_html=True)

    if df_data.empty:
        st.info("Sin mensajes.")
    else:
        df_data['categoria'] = df_data.apply(clasificar_categoria, axis=1)
        
        f1, f2, f3, f4 = st.columns(4)
        if f1.button("👁️ Todo", use_container_width=True, type="primary" if st.session_state.view_category=='all' else "secondary"):
            cambiar_filtro('all')
            st.rerun()
        if f2.button("💰 Ventas", use_container_width=True, type="primary" if st.session_state.view_category=='ventas' else "secondary"):
            cambiar_filtro('ventas')
            st.rerun()
        if f3.button("🛠️ Tec", use_container_width=True, type="primary" if st.session_state.view_category=='tecnico' else "secondary"):
            cambiar_filtro('tecnico')
            st.rerun()
        if f4.button("❓ Varios", use_container_width=True, type="primary" if st.session_state.view_category=='varios' else "secondary"):
            cambiar_filtro('varios')
            st.rerun()
            
        st.markdown("<hr style='margin: 1rem 0; border-color: #333;'>", unsafe_allow_html=True)

        def dibujar_tarjeta(row):
            prio_icon = "🔥" if row['max_prio'] >= 8 else "👤"
            card_label = f"{prio_icon} {row['contact_id']}\n_{row['last_text'][:40]}..._" 
            
            if st.button(card_label, key=f"c_{row['contact_id']}", use_container_width=True):
                ir_al_chat(row['contact_id'])
                st.rerun()

        view = st.session_state.view_category
        
        if view == 'all':
            c_ventas, c_tec, c_varios = st.columns(3)
            with c_ventas:
                st.markdown("##### 🔥 Ventas")
                for _, row in df_data[df_data['categoria'] == 'ventas'].iterrows(): dibujar_tarjeta(row)
            with c_tec:
                st.markdown("##### 🛠️ Técnico")
                for _, row in df_data[df_data['categoria'] == 'tecnico'].iterrows(): dibujar_tarjeta(row)
            with c_varios:
                st.markdown("##### ❓ Varios")
                for _, row in df_data[df_data['categoria'] == 'varios'].iterrows(): dibujar_tarjeta(row)
        else:
            st.markdown(f"##### {view.upper()}")
            df_filtrada = df_data[df_data['categoria'] == view]
            cols = st.columns(2)
            for index, row in df_filtrada.iterrows():
                with cols[index % 2]: dibujar_tarjeta(row)