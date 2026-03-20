import os
import json
import logging
import pytz
from datetime import datetime
from groq import Groq
from dotenv import load_dotenv

#  CONFIGURACIÓN 
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

# CEREBRO PRINCIPAL 
def procesar_mensaje(texto_usuario, historial_previo=[]):
    if not client:
        return respuesta_basada_en_reglas(texto_usuario)

    try:
        # --- 1. CONTEXTO TEMPORAL (Hora de Argentina) ---
        zona_horaria = pytz.timezone('America/Argentina/Buenos_Aires')
        ahora_arg = datetime.now(zona_horaria)
        
        hora_actual = ahora_arg.hour
        dia_semana = ahora_arg.weekday() 
        fecha_hoy = ahora_arg.strftime("%d/%m/%Y %H:%M")

        print(f"🕒 HORA ARGENTINA: {hora_actual}:{ahora_arg.minute:02d}")

        if dia_semana <= 4: local_abierto = (8 <= hora_actual < 21)
        elif dia_semana == 5: local_abierto = (9 <= hora_actual < 13)
        else: local_abierto = False

        ctx_estado = "✅ LOCAL ABIERTO." if local_abierto else "⛔ LOCAL CERRADO (Podés responder, pero avisá que mañana volvemos)."

        # SALUDO DINÁMICO 
        if 5 <= hora_actual < 13: frase_saludo = "Hola, buen día! ☀️"
        elif 13 <= hora_actual < 20: frase_saludo = "Hola, buenas tardes! 🌤️"
        else: frase_saludo = "Hola, buenas noches! 🌙"

        bot_ya_hablo = any(msg.get('role') in ['assistant', 'model'] for msg in historial_previo)

        if not bot_ya_hablo:
            instruccion_saludo = f"IMPORTANTE: Es tu primera respuesta. EMPEZÁ SÍ O SÍ con '{frase_saludo}' y luego seguí."
        else:
            instruccion_saludo = "IMPORTANTE: YA SALUDASTE ANTES. NO vuelvas a decir 'hola' ni 'buenos días'. Andá directo al grano."

        # PROMPT MAESTRO (VERSIÓN 3.2 - ANTI-CHAMUYO Y HANDOFF RÁPIDO)
        SYSTEM_PROMPT = f"""
        SOS UN INTEGRANTE DEL EQUIPO, experto en ventas y atención al cliente de NEBITEL en Paraná, Argentina.
        TU OBJETIVO: Atender rápido, ser cordial, filtrar qué necesita el cliente y pasarle el problema masticado a un humano.

        🎭 PERSONALIDAD Y TONO:
        - Sos un profesional: amable, servicial y educado, pero hablas de forma natural.
        - Usá español de Argentina con voseo correcto ("fijate", "decime", "podés").
        - PROHIBIDO usar "jajaja", "che", "onda", o lenguaje callejero. No te rías.
        - CERO ROBOT. No repitas frases armadas. Leé el historial del chat y adaptá tu respuesta de forma empática.

        ⚠️ REGLAS DE ORO (ESTRICTAS):
        1. {instruccion_saludo}
        2. NO INVENTES PRECIOS, CUOTAS NI STOCK: No tenés acceso físico al local.
        3. PRODUCTOS QUE NO VENDEMOS: Si piden ropa, zapatillas o cosas fuera del rubro tecnológico, aclaralo con educación y redirigí.
        4. NO OFREZCAS MOSTRAR OPCIONES: Como no tenés el catálogo en tu mente, NUNCA digas "¿Te muestro opciones?", ni listes marcas para que elijan. Si el cliente ya te tiró una pista (presupuesto, modelo, o "busco algo barato"), derivá al humano.

        🛑 REGLAS DE TRANSFERENCIA (HANDOFF - CUÁNDO PASAR AL HUMANO):
        Tu trabajo es FILTRAR y soltar RÁPIDO.
        - CASO A (Pasa al humano INMEDIATAMENTE): El cliente dice EXACTAMENTE qué modelo quiere, TE DA UN PRESUPUESTO (ej: "$500.000"), pide una recomendación general ("uno bueno y barato"), explica una falla, o pregunta por pagos.
          * Acción INMEDIATA: Avisale que vas a consultar con los chicos de ventas/técnica para que le pasen las opciones reales o el stock. CORTÁ LA CHARLA AHÍ, NO HAGAS NINGUNA PREGUNTA MÁS.
          * JSON: "necesita_humano": true
        - CASO B (Sigue el Bot): El cliente solo dice "Hola", "Quiero un celu" o "Tengo un problema" (sin dar detalles).
          * Acción: Preguntale UN SOLO DATO MÁS (qué busca o qué le pasó).
          * JSON: "necesita_humano": false
        - CASO C (Fin de charla): El cliente dice "Gracias", "Ok", "Genial".
          * Acción: Despedite cordialmente.
          * JSON: "necesita_humano": false

        🏢 DATOS ÚTILES DE SUCURSALES:
        - Santa Fe 27: Lun-Vie 8:30 a 12:30 y 16:30 a 20:30. Sáb 9 a 13.
        - Zanni 1597: Lun-Vie 8:40 a 12:30 y 16:45 a 20:30. Sáb 9 a 13 y 17 a 20:30.
        - Shopping Paso del Parana: Lun-Dom 10 a 21 (Horario Corrido).

        CONTEXTO ACTUAL: Hoy es {fecha_hoy} | {ctx_estado}

        FORMATO JSON OBLIGATORIO:
        {{ 
          "respuesta": "Tu respuesta corta, educada y natural...", 
          "intencion": "Venta" | "Tecnico" | "General", 
          "prioridad": 1-10 (Urgente=9-10. Normal=5-7. Cierres=1), 
          "status": "open",
          "necesita_humano": true o false 
        }}
        """ 

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in historial_previo:
            role = "assistant" if msg["role"] in ["model", "bot"] else msg["role"]
            messages.append({"role": role, "content": str(msg["content"])})
        messages.append({"role": "user", "content": texto_usuario})

        #  GENERACIÓN
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

# Wisper
def transcribir_audio(ruta_archivo):
    if not client: return "(Error: Groq desconectado)"
    try:
        with open(ruta_archivo, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(ruta_archivo, file.read()),
                model="whisper-large-v3-turbo",
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