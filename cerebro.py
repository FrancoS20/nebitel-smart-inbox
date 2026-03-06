import os
import json
import logging
from datetime import datetime
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

# --- PLAN B (Si se cae Groq) ---
def respuesta_basada_en_reglas(texto_usuario):
    return {
        "respuesta": "Hola! 👋 En este momento estoy con demora. Podés ver precios y stock actualizados en www.nebitel.com.ar mientras te atiendo.", 
        "intencion": "Venta", 
        "prioridad": 5, 
        "status": "open",
        "necesita_humano": False
    }

# --- CEREBRO PRINCIPAL ---
def procesar_mensaje(texto_usuario, historial_previo=[]):
    if not client:
        return respuesta_basada_en_reglas(texto_usuario)

    try:
        # --- 1. CONTEXTO TEMPORAL ---
        ahora_arg = datetime.now()
        hora_actual = ahora_arg.hour
        dia_semana = ahora_arg.weekday() 
        fecha_hoy = ahora_arg.strftime("%d/%m/%Y %H:%M")

        print(f"🕒 HORA PC: {hora_actual}:{ahora_arg.minute}")

        if dia_semana <= 4: local_abierto = (8 <= hora_actual < 21)
        elif dia_semana == 5: local_abierto = (9 <= hora_actual < 13)
        else: local_abierto = False

        ctx_estado = "✅ LOCAL ABIERTO." if local_abierto else "⛔ LOCAL CERRADO (Podés responder, pero avisá que mañana volvemos)."

        # --- 2. SALUDO DINÁMICO ---
        if 5 <= hora_actual < 13: frase_saludo = "Hola, buen día! ☀️"
        elif 13 <= hora_actual < 20: frase_saludo = "Hola, buenas tardes! 🌤️"
        else: frase_saludo = "Hola, buenas noches! 🌙"

        bot_ya_hablo = any(msg.get('role') in ['assistant', 'model'] for msg in historial_previo)

        if not bot_ya_hablo:
            instruccion_saludo = f"IMPORTANTE: Es tu primera respuesta. EMPEZÁ SÍ O SÍ con '{frase_saludo}' y luego seguí."
        else:
            instruccion_saludo = "IMPORTANTE: YA SALUDASTE ANTES. NO vuelvas a decir 'hola' ni 'buenos días'. Andá directo al grano."

        # --- 3. PROMPT MAESTRO (DINÁMICO Y NATURAL) ---
        SYSTEM_PROMPT = f"""
        SOS UN INTEGRANTE DEL EQUIPO, experto en atención al cliente de NEBITEL en Paraná.
        TU OBJETIVO: Responder de forma NATURAL, INFORMATIVA, BREVE, RESOLUTIVA, COORDIAL Y AMABLE.

        🎭 PERSONALIDAD Y TONO:
        - Usá español de Argentina con voseo natural ("fijate", "decime", "te paso").
        - CERO ROBOT. Prohibido decir "estimado cliente" o "gracias por comunicarse". Hablá como una persona.
        - IMPROVISA: No uses siempre las mismas frases. Variá tu vocabulario.

        ⚠️ REGLAS DE ORO:
        1. {instruccion_saludo}
        2. ESCUCHA ACTIVA: Si el cliente ya dio sus datos (ej: modelo de celular), no se los vuelvas a pedir.
        3. NO PROMETAS VALOR: No digas "te hacemos precio". Decí "lo cotizamos" o "te paso el precio exacto".
        4. JAMÁS ofrezcas llamar por teléfono.
        5. NUNCA CONFIRMES STOCK: Vos no tenés acceso al depósito físico. Avisá que lo vas a consultar.
        6. 🛑 REGLA DE TRANSFERENCIA (HANDOFF): Tu trabajo es filtrar. Cuando ya tengas claro qué celular tiene y qué necesita (comprar, arreglar, canjear), IMPROVISÁ una respuesta natural avisando que vas a consultar el precio o el stock con tus compañeros (ej: "Anotado, aguantame que le consulto a los técnicos", "Dale, ahí averiguo si nos queda stock", etc). EN ESE MOMENTO, devolvé "necesita_humano": true.
        7. 👋 REGLA DE CORTESÍA: Si el cliente solo dice "Gracias", "Ok", "Dale" o se despide, respondé amablemente (ej: "¡De nada! Cualquier cosa avisame") pero DEVOLVÉ "necesita_humano": false. No molestes a un humano para leer un "gracias".

        🏢 DATOS ÚTILES:
        - Santa Fe 27: Lun-Vie 8:30-12:30 y 16:30-20:30. Sáb 9-13.
        - Zanni 1597: Lun-Vie 8:40-12:30 y 16:45-20:30. Sáb 9-13 y 17-20:30.
        - Web: nebitel.com.ar (para ver stock/precios).

        CONTEXTO ACTUAL: {fecha_hoy} | {ctx_estado}

        FORMATO JSON OBLIGATORIO:
        {{ 
          "respuesta": "Tu respuesta improvisada y natural...", 
          "intencion": "Venta" | "Tecnico" | "Admin" | "General", 
          "prioridad": 1-10, 
          "status": "open",
          "necesita_humano": true/false 
        }}
        """

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in historial_previo:
            role = "assistant" if msg["role"] in ["model", "bot"] else msg["role"]
            messages.append({"role": role, "content": str(msg["content"])})
        messages.append({"role": "user", "content": texto_usuario})

        # --- 4. GENERACIÓN ---
        completion = client.chat.completions.create(
            model=MODELO_ELEGIDO,
            messages=messages,
            temperature=0.7, 
            max_tokens=800,
            response_format={"type": "json_object"}
        )

        content = completion.choices[0].message.content
        datos = json.loads(content)
        
        print(f"🧠 CEREBRO: {datos.get('intencion')} | Prio: {datos.get('prioridad')} | Pide Humano: {datos.get('necesita_humano', False)}")
        return datos

    except Exception as e:
        logger.error(f"🚨 Falló Groq: {e}")
        return respuesta_basada_en_reglas(texto_usuario)

# --- NUEVA FUNCIÓN: OÍDO BIÓNICO (Whisper) ---
def transcribir_audio(ruta_archivo):
    if not client: return "(Error: Groq desconectado)"
    try:
        with open(ruta_archivo, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(ruta_archivo, file.read()),
                model="whisper-large-v3",
                response_format="json", 
                language="es",
                temperature=0.0
            )
        texto = transcription.text
        print(f"👂 AUDIO ESCUCHADO: '{texto}'")
        return texto
    except Exception as e:
        logger.error(f"❌ Error transcribiendo audio: {e}")
        return "(Audio inaudible o vacío)"