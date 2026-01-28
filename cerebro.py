import os
import json
import logging
from datetime import datetime # 👈 Usamos solo esto, sin timezone ni timedelta
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
    return {"respuesta": "Hola! 👋 Podés ver precios y stock en www.nebitel.com.ar.", "intencion": "Venta", "prioridad": 5, "status": "open"}

# --- CEREBRO PRINCIPAL ---
def procesar_mensaje(texto_usuario, historial_previo=[]):
    if not client:
        return respuesta_basada_en_reglas(texto_usuario)

    try:
        # --- HORA LOCAL DIRECTA (LA DE TU COMPU) ---
        # Sin conversiones. Si tu Windows dice 10:30, esto vale 10:30.
        ahora_arg = datetime.now()
        
        hora_actual = ahora_arg.hour
        dia_semana = ahora_arg.weekday()
        fecha_hoy = ahora_arg.strftime("%d/%m/%Y %H:%M")

        print(f"🕒 HORA DE TU PC: {hora_actual}:{ahora_arg.minute} (El bot usará esto)")

        # Horarios: Lun-Vie 8-21, Sab 9-13
        if dia_semana <= 4: # Lunes a Viernes
            local_abierto = (8 <= hora_actual < 21)
        elif dia_semana == 5: # Sábado
            local_abierto = (9 <= hora_actual < 13)
        else: # Domingo
            local_abierto = False

        ctx_estado = "✅ LOCAL ABIERTO." if local_abierto else "⛔ LOCAL CERRADO (Avisá que mañana 8:30 volvemos)."

        # --- LÓGICA DE SALUDO ---
        # Mañana: 5 a 12
        if 5 <= hora_actual < 13:
            frase_saludo = "Hola, buen día! ☀️"
        # Tarde: 13 a 19
        elif 13 <= hora_actual < 20:
            frase_saludo = "Hola, buenas tardes! 🌤️"
        # Noche: 20 en adelante
        else:
            frase_saludo = "Hola, buenas noches! 🌙"

        # Detectar si el bot ya habló
        bot_ya_hablo = any(msg.get('role') in ['assistant', 'model'] for msg in historial_previo)

        if not bot_ya_hablo:
            instruccion_saludo = f"IMPORTANTE: Es mi primera intervención. TU RESPUESTA DEBE EMPEZAR SÍ O SÍ con '{frase_saludo}' antes de responder."
        else:
            instruccion_saludo = "IMPORTANTE: NO saludes de nuevo (ya saludaste antes). Sé directo y fluido."

        # --- PROMPT MAESTRO ---
        SYSTEM_PROMPT = f"""
        ROL: Asistente de Ventas de NEBITEL (Paraná).
        OBJETIVO: Responder de forma NATURAL, INTELIGENTE y PRUDENTE.

        ⚠️ REGLAS CRÍTICAS:
        1. {instruccion_saludo}
        2. ESCUCHA ACTIVA: Si el cliente YA TE DIO la información (modelo, gigas, batería), NO LA VUELVAS A PEDIR. Confirmá que leíste el dato.
        3. NO PROMETAS VALOR: Nunca digas "te damos buen precio". Solo recolectá info.
        4. BREVEDAD: Máximo 2 oraciones.

        ESTRATEGIA COMERCIAL:

        ♻️ PLAN CANJE ("Toman usados?", "Tengo un iPhone 11 con 88%"):
        - SITUACIÓN A (Faltan datos): "Sisi, tomamos! Decime qué modelo tenés y porcentaje de batería así cotizamos."
        - SITUACIÓN B (Datos completos): "Sisi, lo tomamos! Ya le paso esos datos exactos (Modelo y Batería) a los chicos para que te coticen la diferencia."
        - ⛔ PROHIBIDO volver a preguntar qué modelo o batería tiene si ya lo dijo.
        - PRIORIDAD: 9.

        🛠️ SERVICIO TÉCNICO ("Se rompió", "No anda"):
        - SITUACIÓN A: No dijo modelo -> Preguntalo.
        - SITUACIÓN B: Ya dijo modelo -> "Uh qué macana. Traelo así lo revisan los técnicos."
        - PRIORIDAD: 7.

        🎧 ACCESORIOS (Fundas, Cables):
        - Derivar a la web (nebitel.com.ar).
        - PRIORIDAD: 5.

        📱 VENTA DE EQUIPOS (iPhone 15, Celulares) 🔥:
        - Retener al cliente. Avisar que un vendedor confirma stock ya.
        - PRIORIDAD: 10 (FUEGO).

        📍 DATOS ÚTILES:
        - Santa Fe 27 / Zanni 1597. 
        - Shopping Paso del Paraná (Lunes a Domingo 10 a 21hs).
        
        CONTEXTO: {fecha_hoy} | {ctx_estado}

        FORMATO JSON:
        {{ "respuesta": "Texto...", "intencion": "...", "prioridad": 1-10, "status": "open" }}
        """

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in historial_previo:
            role = "assistant" if msg["role"] == "model" else msg["role"]
            messages.append({"role": role, "content": str(msg["content"])})
        messages.append({"role": "user", "content": texto_usuario})

        completion = client.chat.completions.create(
            model=MODELO_ELEGIDO,
            messages=messages,
            temperature=0.4,
            max_tokens=800,
            response_format={"type": "json_object"}
        )

        return json.loads(completion.choices[0].message.content)

    except Exception as e:
        logger.error(f"🚨 Falló Groq: {e}")
        return respuesta_basada_en_reglas(texto_usuario)


# --- AUDITOR DE CIERRE ---
def analizar_prioridad_silenciosa(historial):
    try:
        SYSTEM_PROMPT_AUDITOR = """
        ROL: Auditor CRM.
        TAREA: Definir si la charla sigue VIVA o si TERMINÓ.
        CRITERIOS:
        1. 🟢 CERRADO (Prioridad 1): "Gracias", "Listo", "Nos vemos", "Paso hoy".
        2. 🔥 ACTIVO (Prioridad 9-10): Pregunta de compra abierta.
        3. 🟡 PENDIENTE (Prioridad 5): Charla normal.
        OUTPUT JSON: { "intencion": "Cierre" | "Venta" | "Pendiente", "prioridad": 1-10 }
        """
        messages = [{"role": "system", "content": SYSTEM_PROMPT_AUDITOR}]
        mensajes_recientes = historial[-4:] 
        for msg in mensajes_recientes:
            role = "assistant" if msg["role"] in ["model","bot"] else "user"
            messages.append({"role": role, "content": str(msg["content"])})
            
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.0,
            max_tokens=150,
            response_format={"type": "json_object"}
        )
        return json.loads(completion.choices[0].message.content)
    except Exception:
        return {"intencion": "Error", "prioridad": 5}