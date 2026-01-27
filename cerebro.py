import os
import json
import logging
from datetime import datetime, timezone, timedelta
from groq import Groq
from dotenv import load_dotenv

# --- CONFIGURACIÓN ---
load_dotenv()
logger = logging.getLogger("cerebro")
logging.basicConfig(level=logging.INFO)

api_key = os.getenv("GROQ_API_KEY")

try:
    client = Groq(api_key=api_key)
    MODELO_ELEGIDO = "llama-3.3-70b-versatile" 
    logger.info(f"✅ Motor Groq activado: {MODELO_ELEGIDO}")
except Exception as e:
    logger.error(f"❌ Error al iniciar Groq: {e}")
    client = None

# --- PLAN B ---
def respuesta_basada_en_reglas(texto_usuario):
    mensaje = texto_usuario.lower().strip()
    
    # Canje
    if any(x in mensaje for x in ["canje", "usado", "toman", "parte de pago", "permuta"]):
        return {
            "respuesta": "👋 Hola! Sí, tomamos equipos en parte de pago. Decime qué modelo tenés y estado de batería para cotizar.",
            "intencion": "Venta", 
            "prioridad": 8, 
            "status": "open"
        }
    
    # Técnico
    if any(x in mensaje for x in ["reparar", "roto", "falla", "arreglo"]):
        return {
            "respuesta": "🛠️ Uh, qué paso? Decime porfa el modelo exacto y la falla así te cotizamos.",
            "intencion": "Tecnico", 
            "prioridad": 7, 
            "status": "open"
        }

    # Default
    return {
        "respuesta": "👋 Hola! Podés ver precios y stock en www.nebitel.com.ar. Si buscás algo puntual avisame.", 
        "intencion": "Venta", 
        "prioridad": 5, 
        "status": "open"
    }

# --- CEREBRO PRINCIPAL ---
def procesar_mensaje(texto_usuario, historial_previo=[]):
    if not client:
        return respuesta_basada_en_reglas(texto_usuario)

    try:
        # --- CONTEXTO ---
        ahora_utc = datetime.now(timezone.utc)
        ahora_arg = ahora_utc - timedelta(hours=3)
        hora_actual = ahora_arg.hour
        dia_semana = ahora_arg.weekday()
        fecha_hoy = ahora_arg.strftime("%d/%m/%Y %H:%M")

        local_abierto = (0 <= dia_semana <= 5 and 8 <= hora_actual < 21)
        ctx_estado = "✅ LOCAL ABIERTO. Respondé con buena onda." if local_abierto else "⛔ LOCAL CERRADO. Avisá que mañana 8:30hs retomamos."

        # --- SALUDO ---
        saludo_time = "Hola!" 
        if 5 <= hora_actual < 13: saludo_time = "Hola, buen día! ☀️"
        elif 13 <= hora_actual < 20: saludo_time = "Hola, buenas tardes! 👋"
        else: saludo_time = "Hola, buenas noches! 🌙"

        instruccion_saludo = f"⚠️ OBLIGATORIO: Tu mensaje TIENE que empezar con la frase '{saludo_time}'."
        if historial_previo:
            instruccion_saludo = "⛔ NO SALUDES DE NUEVO. Sé fluido."

        # --- PROMPT MAESTRO ---
        SYSTEM_PROMPT = f"""
        ROL: Asistente de Ventas y Soporte de NEBITEL (Paraná).
        PERSONALIDAD: Vendedor argentino joven, empático y resolutivo.
        
        OBJETIVO:
        Responder NATURALMENTE (Improvisá).

        REGLAS DE JUEGO:
        1. {instruccion_saludo}
        2. VARIACIÓN: Usá tus palabras.
        3. BREVEDAD: Máximo 2 oraciones.

        ESTRATEGIA DE NEGOCIO (QUÉ HACER):

        ♻️ CASO 1: PLAN CANJE / TOMAMOS USADOS ("Toman usados?", "Permutan?", "Entrego el mío")
        - SITUACIÓN: Cliente quiere entregar su equipo.
        - TU MISIÓN: Confirmar que SÍ tomamos.
        - INSPIRACIÓN: "Sisi, tomamos usados! Decime qué modelo tenés y batería así cotizamos."
        - PRIORIDAD: 9.

        🛠️ CASO 2: SERVICIO TÉCNICO ("Se me rompió el iPhone 11", "Pantalla rota")
        - TU MISIÓN: 
          * SI EL CLIENTE YA DIJO EL MODELO: No lo preguntes de nuevo. Confirmalo (Ej: "Uh qué bajón lo del 11").
          * SI NO LO DIJO: Preguntá modelo y falla.
        - INSPIRACIÓN: "Uh qué macana. Traelo y lo revisan los técnicos a ver si tiene arreglo."
        - PRIORIDAD: 7.

        🎧 CASO 3: ACCESORIOS (Fundas, Cargadores)
        - TU MISIÓN: Derivar amablemente a la web (nebitel.com.ar).
        - PRIORIDAD: 5.

        📱 CASO 4: VENTA DE EQUIPOS (Celulares, iPhones) 🔥
        - TU MISIÓN: Retener y avisar que un humano atiende YA.
        - INSPIRACIÓN: "Es un caño ese equipo. Bancame que le aviso a un vendedor para que te confirme stock ya mismo."
        - PRIORIDAD: 10 (FUEGO).

        📍 CASO 5: GENERAL / UBICACIÓN
        - Santa Fe 27, Zanni 1597.
        - PRIORIDAD: 5.

        CONTEXTO ACTUAL:
        - {fecha_hoy}
        - {ctx_estado}

        FORMATO JSON:
        {{
            "respuesta": "Tu respuesta improvisada aquí...",
            "intencion": "Venta" | "Tecnico" | "Info" | "Cierre",
            "prioridad": 1-10,
            "status": "open"
        }}
        """

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in historial_previo:
            role = "assistant" if msg["role"] == "model" else msg["role"]
            messages.append({"role": role, "content": str(msg["content"])})
        messages.append({"role": "user", "content": texto_usuario})

        completion = client.chat.completions.create(
            model=MODELO_ELEGIDO,
            messages=messages,
            temperature=0.6,
            max_tokens=800,
            response_format={"type": "json_object"}
        )

        return json.loads(completion.choices[0].message.content)

    except Exception as e:
        logger.error(f"🚨 Falló Groq: {e}")
        return respuesta_basada_en_reglas(texto_usuario)


# --- AUDITOR DE CIERRE (LOGICA MEJORADA) ---
def analizar_prioridad_silenciosa(historial):
    try:
        # Prompt más estricto para detectar cierres
        SYSTEM_PROMPT_AUDITOR = """
        ROL: Auditor de Calidad del CRM.
        TAREA: Definir SI LA CONVERSACIÓN ESTÁ ACTIVA O TERMINADA.
        
        CRITERIOS DE PRIORIDAD:
        
        1. 🟢 CERRADO / FINALIZADO (Prioridad 1):
           - Si el cliente dice "Gracias", "Listo", "Nos vemos".
           - IMPORTANTE: Si el cliente confirma que va a ir ("Paso a la tarde", "Voy mañana", "Dale voy"), LA CHARLA DIGITAL TERMINÓ. Se considera CERRADO.
        
        2. 🔥 OPORTUNIDAD ACTIVA (Prioridad 9-10):
           - El cliente preguntó precio/stock y NADIE le contestó todavía.
           - El cliente está esperando respuesta.
        
        3. 🟡 PENDIENTE (Prioridad 5):
           - Charla fluida sin cierre.

        OUTPUT JSON OBLIGATORIO:
        { "intencion": "Cierre" | "Venta" | "Pendiente", "prioridad": 1-10 }
        """
        
        messages = [{"role": "system", "content": SYSTEM_PROMPT_AUDITOR}]
        # Le pasamos solo los últimos mensajes para que no se maree
        mensajes_recientes = historial[-4:] 
        for msg in mensajes_recientes:
            role = "assistant" if msg["role"] in ["model","bot"] else "user"
            messages.append({"role": role, "content": str(msg["content"])})
            
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.0, # Temperatura CERO para máxima precisión lógica
            max_tokens=150,
            response_format={"type": "json_object"}
        )
        return json.loads(completion.choices[0].message.content)

    except Exception:
        return {"intencion": "Error", "prioridad": 5}