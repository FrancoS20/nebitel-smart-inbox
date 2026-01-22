import os
import json
import logging
from datetime import datetime, timezone, timedelta # <--- IMPORTANTE: Agregamos timedelta
from groq import Groq
from dotenv import load_dotenv

# --- CONFIGURACIÓN ---
load_dotenv()
logger = logging.getLogger("cerebro")
logging.basicConfig(level=logging.INFO)

# 1. Cargar API Key
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    logger.error("❌ ERROR CRÍTICO: No encontré la GROQ_API_KEY en el archivo .env")

# 2. Iniciar Cliente Groq
try:
    client = Groq(api_key=api_key)
    MODELO_ELEGIDO = "llama-3.3-70b-versatile" 
    logger.info(f"✅ Motor Groq activado: {MODELO_ELEGIDO}")
except Exception as e:
    logger.error(f"❌ Error al iniciar Groq: {e}")
    client = None

# --- PLAN B: CEREBRO DE RESPALDO (Reglas Fijas) ---
def respuesta_basada_en_reglas(texto_usuario):
    """
    Se activa si Groq falla. Devuelve JSON válido siempre.
    """
    mensaje = texto_usuario.lower().strip()
    
    texto_ventas = "🛒 Para precios y stock actualizados, por favor visitá nuestra web: www.nebitel.com.ar"
    texto_tecnico = "🛠️ Para cotizar una reparación, decime: ¿Qué modelo es y qué falla tiene?"
    texto_info = "📍 Estamos en Paraná: Santa Fe 27, Av. P. Zanni 1597 y Shopping Paso del Paraná."
    texto_default = "👋 ¡Hola! Bienvenido a NEBITEL. En breve un asesor humano te contesta."

    respuesta = texto_default
    intencion = "General"
    prioridad = 5

    if any(x in mensaje for x in ["reparar", "arreglo", "roto", "falla", "pantalla", "bateria"]):
        respuesta = texto_tecnico
        intencion = "Tecnico"
        prioridad = 7
    elif any(x in mensaje for x in ["precio", "comprar", "iphone", "stock", "cuanto sale"]):
        respuesta = texto_ventas
        intencion = "Venta"
        prioridad = 5
    elif any(x in mensaje for x in ["donde", "ubicacion", "horario", "direccion"]):
        respuesta = texto_info
        intencion = "Info"
        prioridad = 3

    return {
        "respuesta": respuesta,
        "intencion": intencion,
        "prioridad": prioridad,
        "status": "open"
    }

# --- CEREBRO PRINCIPAL (GROQ IA) ---
def procesar_mensaje(texto_usuario, historial_previo=[]):
    """
    Motor de Inteligencia usando Groq Cloud con identidad NEBITEL + Control Horario.
    """
    # Si el cliente no cargó, vamos al Plan B directo
    if not client:
        return respuesta_basada_en_reglas(texto_usuario)

    try:
        # --- 1. CONFIGURACIÓN DE TIEMPO (ARGENTINA UTC-3) ---
        ahora_utc = datetime.now(timezone.utc)
        ahora_arg = ahora_utc - timedelta(hours=3) # Restamos 3 horas para Argentina
        
        hora_actual = ahora_arg.hour     # 0 a 23
        dia_semana = ahora_arg.weekday() # 0=Lunes, 6=Domingo

        # --- 2. LÓGICA DE APERTURA/CIERRE ---
        # Definimos horario de atención del BOT: Lunes a Sábado (0-5) de 8 a 21hs.
        # Domingo (6): Cerrado.
        
        local_abierto = False
        if 0 <= dia_semana <= 5: # Si es Lunes a Sábado
            if 8 <= hora_actual < 21: # Y son entre las 8:00 y las 20:59
                local_abierto = True
        
        # (Si querés que el Domingo abra en horario shopping, podés agregar un elif acá)

        # --- 3. INSTRUCCIÓN DINÁMICA PARA EL BOT ---
        if local_abierto:
            instruccion_horario = "✅ ESTADO: EL LOCAL ESTÁ ABIERTO. Atendé normal."
        else:
            instruccion_horario = """
            ⛔ ESTADO: EL LOCAL ESTÁ CERRADO AHORA MISMO.
            INSTRUCCIÓN CLAVE: Respondé la consulta del cliente (dá la info que pide, SIGUIENDO LAS REGLAS DE NEGOCIO), 
            PERO al final de tu respuesta debés agregar amablemente:
            'Igual te cuento que ahora estamos cerrados 🌙, pero dejame tu mensaje que mañana a las 8:30 hs un vendedor lo revisa.'
            """

        # --- 4. ANÁLISIS TEMPORAL (Tu lógica de saludo de 120 mins) ---
        instruccion_saludo = "✅ Podés saludar (Hola, Buen día)."
        tiempo_texto = "Desconocido"

        if historial_previo:
            ultimo_mensaje = historial_previo[-1]
            if 'timestamp' in ultimo_mensaje and ultimo_mensaje['timestamp']:
                try:
                    hora_ultimo = ultimo_mensaje['timestamp']
                    # Asegurar zona horaria UTC
                    if hora_ultimo.tzinfo is None:
                        hora_ultimo = hora_ultimo.replace(tzinfo=timezone.utc)
                    
                    diferencia = ahora_utc - hora_ultimo
                    minutos = int(diferencia.total_seconds() / 60)
                    if minutos < 0: minutos = 0
                    tiempo_texto = f"{minutos} minutos"

                    # Si pasaron menos de 120 min, no saludar de nuevo
                    if minutos < 120:
                        instruccion_saludo = "⛔️ NO SALUDES de nuevo (la charla es fluida). Andá directo al punto."
                    else:
                        instruccion_saludo = "✅ Pasó tiempo, podés saludar de nuevo."
                except Exception as e:
                    logger.warning(f"⚠️ Error calculando tiempo: {e}")

        # --- 5. DEFINIR PROMPT DEL SISTEMA ---
        fecha_hoy = ahora_arg.strftime("%d/%m/%Y %H:%M") # Hora Argentina para el prompt
        
        SYSTEM_PROMPT = f"""
        ROL: Sos "Nebitel Bot", asistente de ventas de NEBITEL (Tienda de tecnología en PARANÁ, Entre Ríos).
        Tu objetivo es atender natural, amable,cordial y filtrar intenciones.

        UBICACIONES:
        - Centro: Santa Fe 27 (8:30-12:30 / 16:30-20:30).
        - Zanni: Av. P. Zanni 1597 (8:30-12:30 / 16:30-20:30).
        - Shopping: Shopping Paso del Paraná (10 a 21hs de corrido).

        REGLAS DE NEGOCIO (ESTRICTAS):
        1. PRECIOS: NO des precios fijos (cambian por el dólar). Decí: "Los precios varían, fijate los actualizados en la web: www.nebitel.com.ar".
        2. SERVICIO TÉCNICO: Si reportan fallas ("roto", "no carga"), preguntá MODELO y FALLA.
        3. PLAN CANJE (Importante):
           - SÍ tomamos usados (iPhone).
           - RESPUESTA: "Sisi, tomamos usados! 📱 Decime modelo, gigas y porcentaje de batería así le paso el dato a un vendedor para que te cotice."

        CONTEXTO ACTUAL:
        - Fecha y Hora: {fecha_hoy}
        - Tiempo inactivo charla: {tiempo_texto}
        - {instruccion_saludo}
        - {instruccion_horario} <--- ¡IMPORTANTE: ESTADO DEL LOCAL!

        FORMATO DE SALIDA (JSON OBLIGATORIA):
        Tu respuesta debe ser SIEMPRE un objeto JSON puro.
        {{
            "respuesta": "Texto amable para el cliente (usá emojis moderados)...",
            "intencion": "Venta" | "Tecnico" | "Admin" | "Plan Canje" | "Info",
            "prioridad": 1-10 (10=Urgente/Venta cerrada, 5=Consulta, 1=Saludo),
            "status": "open" | "closed"
        }}
        """

        # --- 6. CONSTRUIR HISTORIAL ---
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        
        for msg in historial_previo:
            role = "assistant" if msg["role"] == "model" else msg["role"]
            content = str(msg["content"])
            messages.append({"role": role, "content": content})
            
        messages.append({"role": "user", "content": texto_usuario})

        logger.info(f"⚡ Consultando a Groq ({MODELO_ELEGIDO})...")

        # --- 7. LLAMADA A LA API ---
        completion = client.chat.completions.create(
            model=MODELO_ELEGIDO,
            messages=messages,
            temperature=0.6,
            max_tokens=1024,
            response_format={"type": "json_object"}
        )

        respuesta_str = completion.choices[0].message.content
        return json.loads(respuesta_str)

    except Exception as e:
        logger.error(f"🚨 Error en Groq: {e}")
        return respuesta_basada_en_reglas(texto_usuario)

def analizar_prioridad_silenciosa(historial):
    """
    Lee el chat pero NO genera respuesta para el cliente.
    Solo devuelve la Prioridad y la Intención actualizadas.
    """
    try:
        # Prompt específico para auditoría
        SYSTEM_PROMPT_AUDITOR = """
        ROL: Auditor de Calidad de NEBITEL.
        TAREA: Analizar el historial de chat y determinar el estado ACTUAL de la conversación.
        
        CRITERIO DE PRIORIDAD:
        - 1: Conversación cerrada, despedida, agradecimiento o "todo ok".
        - 5: Conversación en pausa, espera de datos normales.
        - 8-10: El cliente hizo una pregunta y NADIE le respondió todavía, o hay una venta caliente sin cerrar.
        
        OUTPUT JSON:
        {
            "intencion": "Venta" | "Tecnico" | "Cierre" | "Pendiente",
            "prioridad": 1-10
        }
        NO GENERES RESPUESTA DE TEXTO. SOLO CLASIFICA.
        """
        
        messages = [{"role": "system", "content": SYSTEM_PROMPT_AUDITOR}]
        
        # Cargamos el historial (incluyendo lo que escribió el humano)
        for msg in historial:
            role = "assistant" if msg["role"] == "model" or msg["role"] == "bot" else "user"
            messages.append({"role": role, "content": str(msg["content"])})
            
        # Consultamos a Groq (usamos un modelo rápido si querés ahorrar, o el mismo)
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.1, # Muy frío y analítico
            max_tokens=100,
            response_format={"type": "json_object"}
        )
        
        return json.loads(completion.choices[0].message.content)

    except Exception as e:
        logger.error(f"Error auditoria: {e}")
        return {"intencion": "Error", "prioridad": 5}