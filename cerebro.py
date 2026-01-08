import os
import google.generativeai as genai
import logging
import json
from datetime import datetime, timezone
from dotenv import load_dotenv

# --- CONFIGURACIÓN INICIAL ---
load_dotenv()

# Configuración de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración Gemini
API_KEY = os.getenv("GEMINI_API_KEY")
ia_activa = False

try:
    if API_KEY:
        genai.configure(api_key=API_KEY)
        # Usamos flash por velocidad y eficiencia
        model = genai.GenerativeModel('gemini-2.5-flash')
        ia_activa = True
        logger.info("✅ Cerebro IA conectado y listo (Con Memoria Temporal).")
    else:
        logger.warning("⚠️ No se encontró GEMINI_API_KEY. Usando modo Manual.")
except Exception as e:
    logger.error(f"❌ Error al iniciar la IA: {e}")

# --- CEREBRO DE RESPALDO (Reglas fijas) ---
def respuesta_basada_en_reglas(texto_usuario):
    """
    Plan B: Se activa si la IA falla o no está configurada.
    """
    mensaje = texto_usuario.lower().strip()
    
    texto_menu = "👋 ¡Hola! Bienvenido a NEBITEL.\n1️⃣ Ventas\n2️⃣ Técnico\n3️⃣ Ubicación"
    texto_ventas = "🛒 Para precios y stock, podés ver todo en www.nebitel.com.ar"
    texto_tecnico = "🛠️ Para cotizar una reparación, por favor decime: ¿Qué modelo es y qué falla tiene?"
    texto_info = "📍 Estamos en Zona Centro. Horarios: Lun a Sab de 9 a 20hs."

    if any(x in mensaje for x in ["reparar", "arreglo", "roto", "falla", "2"]):
        return texto_tecnico
    elif any(x in mensaje for x in ["precio", "comprar", "iphone", "stock", "1"]):
        return texto_ventas
    elif any(x in mensaje for x in ["donde", "ubicacion", "horario", "3"]):
        return texto_info
    elif "humano" in mensaje:
        return "👤 Ya aviso a un vendedor para que te atienda."
    else:
        return texto_menu

# --- CEREBRO PRINCIPAL (IA + Contexto) ---
def procesar_mensaje(texto_usuario, historial_previo=[]):
    """
    Función principal inteligente.
    Args:
        texto_usuario (str): El mensaje nuevo que acaba de llegar.
        historial_previo (list): Lista de dicts con la conversación anterior.
    """
    global ia_activa
    
    # 1. ANÁLISIS TEMPORAL 
    instruccion_saludo = "✅ Podés saludar cortésmente (Hola, Buen día) si corresponde."
    tiempo_texto = "Desconocido"

    if historial_previo:
        ultimo_mensaje = historial_previo[-1]
        
        if 'timestamp' in ultimo_mensaje and ultimo_mensaje['timestamp']:
            try:
                hora_ultimo = ultimo_mensaje['timestamp']
                
                # CORRECCIÓN DE ZONA HORARIA 🌍
                # Si la fecha de la DB viene sin zona (naive), asumimos que es UTC
                if hora_ultimo.tzinfo is None:
                    hora_ultimo = hora_ultimo.replace(tzinfo=timezone.utc)
                
                # Obtenemos la hora actual TAMBIÉN en UTC
                ahora_utc = datetime.now(timezone.utc)
                
                # Ahora restamos peras con peras (UTC con UTC)
                diferencia = ahora_utc - hora_ultimo
                minutos = int(diferencia.total_seconds() / 60)
                
                # Si sale negativo (por milisegundos), lo ponemos en 0
                if minutos < 0: minutos = 0
                
                tiempo_texto = f"{minutos} minutos"

                # REGLA DE LOS 15 MINUTOS
                if minutos < 15:
                    instruccion_saludo = "⛔️ PROHIBIDO SALUDAR (Hola, Buen día, etc). La conversación es fluida y reciente. Respondé directo al grano."
                else:
                    instruccion_saludo = "✅ Pasó un tiempo, podés saludar de nuevo si es necesario."
                    
            except Exception as e:
                logger.warning(f"⚠️ No se pudo calcular tiempo: {e}")

    # CASO A: Usar IA
    if ia_activa:
        try:
            logger.info(f"🤖 IA Pensando... Contexto: {len(historial_previo)} msgs previos. Tiempo: {tiempo_texto}")
            
            fecha_hoy = datetime.now().strftime("%d/%m/%Y %H:%M")
            
            # Formatear el historial como guion
            guion_chat = ""
            if historial_previo:
                for msg in historial_previo:
                    nombre = "Cliente" if msg['role'] == 'user' else "Nebitel"
                    # Limpiamos saltos de línea extra
                    contenido = str(msg['content']).replace('\n', ' ')
                    guion_chat += f"- {nombre}: {contenido}\n"
            else:
                guion_chat = "(Sin mensajes previos)"

            # EL PROMPT DE SISTEMA
            prompt_sistema = f"""
            Sos el asistente virtual de NEBITEL (Rosario, Argentina). Hoy es {fecha_hoy}.
            Tu objetivo es clasificar la consulta y dar una respuesta útil y corta.
            
            CONTEXTO DE TIEMPO:
            - Último mensaje previo hace: {tiempo_texto}.
            - INSTRUCCIÓN DE SALUDO: {instruccion_saludo}
            
            HISTORIAL DE CONVERSACIÓN:
            {guion_chat}
            
            MENSAJE NUEVO DEL CLIENTE:
            "{texto_usuario}"
            
            TUS REGLAS:
            1. NO inventes precios. Mandá a www.nebitel.com.ar.
            2. Si es Servicio Técnico, pedí Modelo y Falla.
            3. Si el cliente sigue el hilo (ej: "¿y en negro?"), usá el historial para saber de qué habla.
            4. Respondé en UNA sola frase amigable (máx 40 palabras).
            
            Respuesta:
            """
            
            # Generar respuesta
            response = model.generate_content(prompt_sistema)
            return response.text.strip()

        except Exception as e:
            logger.error(f"🚨 Falló la IA (Error: {e}). Usando reglas fijas.")
            return respuesta_basada_en_reglas(texto_usuario)
            
    # CASO B: Sin IA
    else:
        return respuesta_basada_en_reglas(texto_usuario)