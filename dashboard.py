import streamlit as st
import pandas as pd
import os
import requests
import time
import pytz 
from datetime import datetime, timezone, timedelta
import streamlit.components.v1 as components
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# CONFIGURACIÓN 
st.set_page_config(page_title="Nebitel CRM", page_icon="🦅", layout="wide", initial_sidebar_state="expanded")

load_dotenv()

# DATOS DE META PARA EL REVISOR 
APP_ID = "1150423273840388" 
REDIRECT_URI = "https://nebitel-smart-inbox-b7xr2f42bdrvyvpdmpgrew.streamlit.app/" 

# 👇 --- INICIO SISTEMA DE LOGIN --- 👇
if 'logeado' not in st.session_state:
    st.session_state.logeado = False

if "code" in st.query_params:
    st.session_state.logeado = True

if not st.session_state.logeado:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.write("") 
        st.write("") 
        st.title("🔒 Acceso Interno")
        st.info("Para auditar el cumplimiento de Meta (Apartado 7.a) y el permiso 'human_agent', inicie sesión con Facebook.")
        
        # --- BOTÓN DE FACEBOOK PARA EL REVISOR ---
        auth_url = (
            f"https://www.facebook.com/v20.0/dialog/oauth?"
            f"client_id={APP_ID}&"
            f"redirect_uri={REDIRECT_URI}&"
            f"scope=pages_messaging,human_agent,pages_show_list,public_profile"
        )
        
        st.markdown(f'''
            <a href="{auth_url}" target="_self">
                <button style="
                    background-color: #1877F2; 
                    color: white; 
                    border: none; 
                    padding: 12px 24px; 
                    border-radius: 6px; 
                    cursor: pointer; 
                    font-size: 16px; 
                    font-weight: bold;
                    width: 100%;
                    margin-bottom: 20px;
                ">
                    Continuar con Facebook
                </button>
            </a>
        ''', unsafe_allow_html=True)
        
        st.divider()
        st.caption("Acceso alternativo (Personal de Nebitel):")

       
        password_input = st.text_input("Ingrese la contraseña de acceso", type="password")
        
        # Lee la clave de Streamlit Secrets o usa la de por defecto
        MASTER_PASSWORD = os.getenv("PASSWORD_PANEL", "Nebitel2026!")
        
        if st.button("Ingresar al CRM", type="primary", use_container_width=True):
            if password_input == MASTER_PASSWORD:
                st.session_state.logeado = True
                st.success("Acceso concedido. Cargando...")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Contraseña incorrecta. Inténtelo de nuevo.")
                
    st.stop() # Frena la carga del resto de la página si no pusieron la clave ni se loguearon




DB_URL = os.getenv("DATABASE_URL")
META_TOKEN = os.getenv("META_TOKEN")         # Llave del Local (Para Instagram)
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN") # Súper Llave del Edificio (Para WhatsApp)
META_PHONE_ID = os.getenv("META_PHONE_ID")

if not DB_URL:
    st.error("❌ Falta DATABASE_URL en el .env")
    st.stop()

# Conexión Robusta
engine = create_engine(
    DB_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=1800
)

#  CSS (ESTILO WHATSAPP + FOTOS COMPACTAS)
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    .block-container { padding-top: 2rem !important; padding-bottom: 5rem !important; }
    
    /* Contenedor del Chat */
    #chat-box-monolith {
        display: flex;
        flex-direction: column !important;
        align-items: flex-start;
    }

    /* Burbujas */
    .chat-bubble { 
        padding: 10px 14px; 
        border-radius: 10px; 
        margin-bottom: 8px; 
        width: fit-content; 
        max-width: 75%; 
        font-size: 15px; 
        line-height: 1.4;
        box-shadow: 0 1px 1px rgba(0,0,0,0.2);
        position: relative;
        word-wrap: break-word;
    }
    
    .user-bubble { 
        background-color: #202c33; 
        color: white; 
        border-top-left-radius: 0; 
        align-self: flex-start; 
    } 
    
    .bot-bubble { 
        background-color: #1f2c34; 
        color: #00bfa5; 
        border-top-right-radius: 0; 
        border: 1px solid #00bfa5; 
        align-self: flex-end; 
    }

    .human-bubble { 
        background-color: #005c4b; 
        color: white; 
        border-top-right-radius: 0; 
        align-self: flex-end; 
    } 
    
    .meta-info { 
        font-size: 0.7rem; 
        color: rgba(255,255,255,0.5); 
        text-align: right; 
        margin-top: 4px; 
        display: block; 
    }

    .badge-ad {
        background-color: #ffd700;
        color: #000;
        font-size: 0.7rem;
        padding: 2px 6px;
        border-radius: 4px;
        font-weight: bold;
        display: inline-block;
        margin-bottom: 4px;
    }
    
    header[data-testid="stHeader"] { visibility: hidden; }
    div.stButton > button { width: 100%; text-align: left; background-color: #111b21; border: 1px solid #2a3942; color: #e9edef; padding: 12px; border-radius: 8px; }
    div.stButton > button:hover { border-color: #00a884; background-color: #202c33; }
</style>
""", unsafe_allow_html=True)

# FUNCIONES DE LÓGICA 

def normalizar_hora(df, columna='created_at'):
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

def apagar_bot_por_terminacion(telefono_completo):
    s = str(telefono_completo).replace("+", "").replace(" ", "").strip()
    patron = f"%{s[-7:]}" if len(s) > 7 else s
    with engine.connect() as conn:
        res = conn.execute(text("UPDATE contacts SET bot_mode = FALSE WHERE client_id LIKE :pat"), {"pat": patron})
        conn.commit()
        return res.rowcount

def enviar_mensaje_omnicanal(telefono, texto):
    s = str(telefono).replace("+", "").strip()
    patron = f"%{s[-7:]}" if len(s) > 7 else s
    with engine.connect() as conn:
        plataforma = conn.execute(text("SELECT platform FROM contacts WHERE client_id LIKE :pat LIMIT 1"), {"pat": patron}).scalar()

    token_a_usar = WHATSAPP_TOKEN if plataforma == 'whatsapp' else META_TOKEN
    
    if not token_a_usar: 
        st.toast(f"❌ Falla: No hay token configurado para {plataforma}")
        return False

    headers = {"Authorization": f"Bearer {token_a_usar}", "Content-Type": "application/json"}
    
    try:
        if plataforma == 'whatsapp':
            dest_meta = s
            if dest_meta.startswith("549"): dest_meta = dest_meta.replace("549", "54", 1)
            url = f"https://graph.facebook.com/v21.0/{META_PHONE_ID}/messages"
            payload = {"messaging_product": "whatsapp", "to": dest_meta, "type": "text", "text": {"body": texto}}
            
        elif plataforma in ['instagram', 'facebook']:
            url = "https://graph.facebook.com/v21.0/me/messages"
            payload = {"recipient": {"id": telefono}, "message": {"text": texto}}
            
        else:
            st.toast(f"❌ Plataforma desconocida: {plataforma}")
            return False

        res = requests.post(url, headers=headers, json=payload)
        
        if res.status_code == 200:
            with engine.connect() as conn:
                conn.execute(text("INSERT INTO messages (contact_id, message_text, direction, status, intent, priority_score, created_at, sender_type) VALUES (:cel, :msg, 'outbound', 'sent_by_human', 'Human Reply', 0, NOW(), 'human')"), {"cel": telefono, "msg": texto})
                conn.commit()
            apagar_bot_por_terminacion(telefono) 
            return True
        else:
            st.toast(f"❌ Error Meta: {res.text}")
            return False
    except Exception as e:
        print(f"Error enviando: {e}")
        return False

def callback_switch_bot():
    try:
        client_id = st.session_state.selected_client
        nuevo_estado = st.session_state[f"tg_{client_id}"]
        if nuevo_estado is False:
            apagar_bot_por_terminacion(client_id)
            st.toast("🛑 Bot APAGADO.")
        else:
            s = str(client_id).replace("+", "").strip()
            patron = f"%{s[-7:]}" if len(s) > 7 else s
            with engine.connect() as conn:
                conn.execute(text("UPDATE contacts SET bot_mode = TRUE WHERE client_id LIKE :pat"), {"pat": patron})
                conn.commit()
            st.toast("🤖 Bot PRENDIDO.")
    except Exception as e: st.error(f"Error Toggle: {e}")

#  GESTIÓN DE VISTAS
if 'selected_client' not in st.session_state: st.session_state.selected_client = None
if 'view_category' not in st.session_state: st.session_state.view_category = "all"

def ir_al_chat(cid): st.session_state.selected_client = cid
def volver(): st.session_state.selected_client = None; st.rerun()

#  COMPONENTES VIVOS (FRAGMENTS)
@st.fragment(run_every=3)
def bloque_mensajes(client_id):
    try:
        s = str(client_id).replace("+", "").strip()
        patron = f"%{s[-7:]}" if len(s) > 7 else s
        
        with engine.connect() as conn:
            sql = """
                SELECT message_text, direction, status, sender_type, intent, created_at, media_url, media_type 
                FROM messages WHERE contact_id LIKE :pat ORDER BY created_at DESC LIMIT 50
            """
            df = pd.read_sql(text(sql), conn, params={"pat": patron})
            df = normalizar_hora(df)
            
            if not df.empty:
                df = df.sort_values(by='created_at', ascending=True)

    except: df = pd.DataFrame()

    if df.empty:
        with st.container(height=600):
            st.info("📭 No hay mensajes aún.")
        return

    #  CONSTRUCCIÓN DEL HTML  
    mensajes_html = ""
    for _, row in df.iterrows():
        hora_str = formatear_fecha(row['created_at'])
        d, s = row['direction'], row['status']
        
        # Clases
        if d == 'inbound': 
            cls = "user-bubble"
            ico = ""
            flex_align = "flex-start"
        elif s == 'sent_by_human' or row['sender_type'] == 'human': 
            cls = "human-bubble"
            ico = "👨‍💻"
            flex_align = "flex-end"
        else: 
            cls = "bot-bubble"
            ico = "🤖"
            flex_align = "flex-end"
        
        # Visuales 
        contenido_visual = ""
        if row.get('media_url') and row.get('media_type') == 'image':
            contenido_visual = f"""<a href="{row['media_url']}" target="_blank"><img src="{row['media_url']}" width="150" style="height: auto; border-radius: 8px; margin-bottom: 5px; cursor: pointer;"></a><br>"""

        #  Audio
        icono_audio = ""
        if row.get('media_type') == 'audio':
            icono_audio = "🎤 <i>(Audio Transcrito):</i> "
        
        #  Texto y Badges
        texto_limpio = str(row["message_text"]).replace("<", "&lt;").replace(">", "&gt;") 
        
        if "Viene del anuncio:" in texto_limpio:
            parts = texto_limpio.split("Viene del anuncio:", 1)
            if len(parts) > 1:
                texto_limpio = f"""<div class="badge-ad">📢 LEAD DE INSTAGRAM</div><br>{parts[1]}"""
            else:
                texto_limpio = f"""<div class="badge-ad">📢 PUBLICIDAD</div><br>{texto_limpio}"""

        #  Intent
        extra_tag = ""
        if row['sender_type'] == 'bot' and row.get('intent'):
             extra_tag = f"""<br><span style='font-size:0.6rem; opacity:0.8;'>🧠 {row['intent']}</span>"""

        #  HTML FINAL 
        mensajes_html += f"""<div style="display:flex; justify-content:{flex_align}; width:100%; margin-bottom: 8px;"><div class="chat-bubble {cls}">{contenido_visual}<div>{icono_audio}{texto_limpio}</div>{extra_tag}<span class="meta-info">{ico} {hora_str}</span></div></div>"""

    unique_id = "chat-box-monolith"
    
    # CONTENEDOR FINAL 
    html_final = f"""<div id="{unique_id}" style="height: 600px; overflow-y: auto; display: flex; flex-direction: column; padding: 10px; border: 1px solid #2a3942; border-radius: 8px; background-color: #0e1117;">{mensajes_html}</div>"""
    
    st.markdown(html_final, unsafe_allow_html=True)

    # JAVASCRIPT
    js_observer = f"""
    <script>
        var chat = window.parent.document.getElementById("{unique_id}");
        if (chat) {{
            chat.scrollTop = chat.scrollHeight;
            var observer = new ResizeObserver(entries => {{
                for (let entry of entries) {{ chat.scrollTop = chat.scrollHeight; }}
            }});
            observer.observe(chat);
            for (let child of chat.children) {{ observer.observe(child); }}
        }}
    </script>
    """
    components.html(js_observer, height=0, width=0)

@st.fragment(run_every=5)
def bloque_tablero():
    try:
        with engine.connect() as conn:
            # Query optimizada Top 50
            sql = """
                SELECT c.client_id, c.bot_mode, c.platform, m.created_at, m.message_text, m.intent, m.priority_score
                FROM contacts c
                JOIN LATERAL (
                    SELECT message_text, created_at, intent, priority_score
                    FROM messages WHERE contact_id = c.client_id ORDER BY created_at DESC LIMIT 1
                ) m ON TRUE
                ORDER BY m.created_at DESC LIMIT 50;
            """
            df = pd.read_sql(text(sql), conn)
            if not df.empty: 
                df = normalizar_hora(df, 'created_at')
    except: df = pd.DataFrame()

    if df.empty:
        st.info("Sin mensajes recientes.")
        return

    ahora_arg = pd.Timestamp.now(tz='America/Argentina/Buenos_Aires')
    df['minutos_espera'] = (ahora_arg - df['created_at']).dt.total_seconds() / 60
    
    # Rellenamos nulos por las dudas
    df['priority_score'] = df['priority_score'].fillna(0)

    # Fórmula: Suma puntos por tiempo solo si la prioridad original es mayor a 2
    df['score_dinamico'] = df.apply(
        lambda row: row['priority_score'] + (row['minutos_espera'] * 0.1) if row['priority_score'] > 2 else row['priority_score'], 
        axis=1
    )
    
    df = df.sort_values(by=['score_dinamico', 'created_at'], ascending=[False, True])
    

   
    def clasificar(r):
        intent = str(r['intent']).strip()
        # Mapeo directo de las 3 opciones del LLM
        if intent == 'Venta': return 'ventas'
        if intent == 'Tecnico': return 'tecnico'
        if intent == 'General': return 'varios'
        
        
        if intent in ['Precio','Stock','Compra'] or r['score_dinamico'] >= 9: return 'ventas'
        if intent in ['Reparación','Falla','Soporte']: return 'tecnico'
        return 'varios'

    df['cat'] = df.apply(clasificar, axis=1)
    vista = st.session_state.view_category
    
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
                    h = formatear_fecha(r['created_at'])
                    p_icon = "🔵" if 'facebook' in str(r['platform']) else ("📸" if 'instagram' in str(r['platform']) else "🟢")
                    bot_icon = "🟢" if r['bot_mode'] else "🔴"
                    
                    texto_preview = str(r['message_text'])[:40] + "..." if len(str(r['message_text'])) > 40 else str(r['message_text'])
                    
                    
                    lbl = f"{p_icon} [{int(r['score_dinamico'])}] **{r['client_id']}** {bot_icon}\n\n_{texto_preview}_\n\n🕒 {h}"

                    if st.button(lbl, key=f"card_{r['client_id']}"):
                        ir_al_chat(r['client_id']); st.rerun()
    else:
        st.subheader(f"📂 {vista.upper()}")
        df_show = df[df['cat'] == vista]
        for _, r in df_show.iterrows():
            lbl = f"[{int(r['score_dinamico'])}] {r['client_id']} | {r['message_text']}"
            if st.button(lbl, key=f"list_{r['client_id']}"): ir_al_chat(r['client_id']); st.rerun()

#  SIDEBAR 
@st.fragment(run_every=5)
def render_sidebar():
    # Título y Botón Home
    st.title("🦅 Nebitel")
    if st.button("🏠 Tablero Principal", use_container_width=True): 
        st.session_state.selected_client = None
        st.rerun()
        
    st.divider()
    st.caption("CHATS RECIENTES")
    
    try:
        with engine.connect() as conn:
            df_side = pd.read_sql(text("""
                SELECT m.contact_id, MAX(m.created_at) as last_msg, c.bot_mode, 
                       (SELECT priority_score FROM messages m2 WHERE m2.contact_id = m.contact_id ORDER BY created_at DESC LIMIT 1) as prio
                FROM messages m
                JOIN contacts c ON m.contact_id = c.client_id
                GROUP BY m.contact_id, c.bot_mode
                ORDER BY last_msg DESC LIMIT 15
            """), conn)
    except: df_side = pd.DataFrame()
    
    if not df_side.empty:
        for _, row in df_side.iterrows():
            puntaje = int(row['prio']) if pd.notnull(row['prio']) else 0
            
            if puntaje >= 8: icon = "🔥"
            elif not row['bot_mode']: icon = "🔴"
            else: icon = "👤"
            
            lbl = f"{icon} [{puntaje}] {row['contact_id']}"
            
            if st.button(lbl, key=f"side_{row['contact_id']}", use_container_width=True):
                st.session_state.selected_client = row['contact_id']
                st.rerun()

# LAYOUT PRINCIPAL 
with st.sidebar:
    render_sidebar()

if st.session_state.selected_client:
    client_id = st.session_state.selected_client
    
    # Obtener estado
    s = str(client_id).replace("+", "").strip()
    patron = f"%{s[-7:]}" if len(s) > 7 else s
    with engine.connect() as conn:
        res = conn.execute(text("SELECT bot_mode FROM contacts WHERE client_id LIKE :pat"), {"pat": patron}).fetchall()
        bot_on_db = any(r[0] for r in res)

    # Header
    c1, c2, c3 = st.columns([1, 6, 3])
    with c1: 
        if st.button("⬅", help="Volver"): volver()
    with c2: 
        st.markdown(f"### 💬 {client_id}")
    with c3:
        if st.session_state.get('force_off_next_run') == client_id:
            st.session_state[f"tg_{client_id}"] = False
            del st.session_state['force_off_next_run']
        
        estado_actual = st.session_state.get(f"tg_{client_id}", bot_on_db)
        label_dinamico = "🤖 BOT ON" if estado_actual else "🛑 BOT OFF"

        st.toggle(
            label_dinamico, 
            value=bot_on_db, 
            key=f"tg_{client_id}", 
            on_change=callback_switch_bot
        )

    st.divider()

    #   Capturamos texto primero para que renderice instantáneo 
    texto = st.chat_input(f"Escribí tu respuesta para {client_id}...")
    
    if texto:
        if enviar_mensaje_omnicanal(client_id, texto): 
            st.session_state['force_off_next_run'] = client_id
            st.rerun()
            
    bloque_mensajes(client_id)

else:
    # Inbox
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