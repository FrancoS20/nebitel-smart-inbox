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
        "status": "open"
    }

# --- CEREBRO PRINCIPAL ---
def procesar_mensaje(texto_usuario, historial_previo=[]):
    if not client:
        return respuesta_basada_en_reglas(texto_usuario)

    try:
        # --- 1. CONTEXTO TEMPORAL (Hora de tu PC) ---
        ahora_arg = datetime.now()
        hora_actual = ahora_arg.hour
        dia_semana = ahora_arg.weekday() # 0=Lunes, 6=Domingo
        fecha_hoy = ahora_arg.strftime("%d/%m/%Y %H:%M")

        print(f"🕒 HORA PC: {hora_actual}:{ahora_arg.minute}")

        # Lógica de "Abierto/Cerrado" para dar contexto a la IA
        # Horarios: Lun-Vie 8-21, Sab 9-13
        if dia_semana <= 4: # Lunes a Viernes
            local_abierto = (8 <= hora_actual < 21)
        elif dia_semana == 5: # Sábado
            local_abierto = (9 <= hora_actual < 13)
        else: # Domingo
            local_abierto = False

        ctx_estado = "✅ LOCAL ABIERTO." if local_abierto else "⛔ LOCAL CERRADO (Podés responder, pero avisá que mañana volvemos)."

        # --- 2. SALUDO DINÁMICO ---
        if 5 <= hora_actual < 13:
            frase_saludo = "Hola, buen día! ☀️"
        elif 13 <= hora_actual < 20:
            frase_saludo = "Hola, buenas tardes! 🌤️"
        else:
            frase_saludo = "Hola, buenas noches! 🌙"

        # Detectar si el bot ya habló antes para no saludar como disco rayado
        bot_ya_hablo = any(msg.get('role') in ['assistant', 'model'] for msg in historial_previo)

        if not bot_ya_hablo:
            instruccion_saludo = f"IMPORTANTE: Es tu primera respuesta. EMPEZÁ SÍ O SÍ con '{frase_saludo}' y luego seguí."
        else:
            instruccion_saludo = "IMPORTANTE: YA SALUDASTE ANTES. NO vuelvas a decir 'hola' ni 'buenos días'. Andá directo al grano."

        # --- 3. PROMPT MAESTRO (PERSONALIDAD + DATOS) ---
        SYSTEM_PROMPT = f"""
        SOS UN INTEGRANTE DEL EQUIPO, experto en atención al cliente de NEBITEL en Paraná.
        TU OBJETIVO: Responder de forma NATURAL, INFORMATIVA, BREVE, RESOLUTIVA Y COORDIAL.

        🎭 PERSONALIDAD Y TONO:
        - Usá español de Argentina con voseo natural ("fijate", "decime", "te paso").
        - CERO ROBOT. Prohibido decir "estimado cliente" o "gracias por comunicarse". Hablá como una persona.
        - Sé empático pero directo. 
        - IMPROVISA: No uses siempre las mismas frases. Variá tu vocabulario.

        ⚠️ REGLAS DE ORO:
        1. {instruccion_saludo}
        2. ESCUCHA ACTIVA: Si el cliente dice "Tengo un iPhone 11 de 64gb", NO le preguntes qué modelo tiene. ¡Ya te lo dijo! Confirmá y avanzá.
        3. NO PROMETAS VALOR: No digas "te hacemos precio amigo". Decí "lo cotizamos".
        4. JAMÁS ofrezcas llamar por teléfono. Todo es por chat o presencial.

        🏢 DATOS ÚTILES (Solo si preguntan o es necesario para cerrar):
        - Santa Fe 27: Lun-Vie 8:30-12:30 y 16:30-20:30. Sáb 9-13.
        - Zanni 1597: Lun-Vie 8:40-12:30 y 16:45-20:30. Sáb 9-13 y 17-20:30.
        - Shopping Paso del Paraná: Lun-Dom 10 a 21hs.
        - Web: nebitel.com.ar (para ver stock/precios si estás muy ocupado).

        🧠 ESTRATEGIA COMERCIAL (Cómo actuar):
        
        1. ♻️ PLAN CANJE ("Toman usados?", "Tengo un X con 80%"):
           - Si faltan datos: "Sisi, tomamos! Decime modelo y batería así cotizamos."
           - Si YA dio datos: "Dale, tomo nota del modelo y batería. Ya le paso la info a los chicos para que te coticen la diferencia exacto." (PRIORIDAD 9).

        2. 🛠️ SERVICIO TÉCNICO ("No carga", "Pantalla rota"):
           - Si dijo modelo: "Uh qué macana. Traelo a Santa Fe o Zanni así lo revisan los técnicos."
           - Si no dijo modelo: Preguntalo.
           - (PRIORIDAD 7).

        3. 📱 VENTA DE EQUIPOS (iPhone 15, Celulares):
           - Si hay intención de compra real: Avisá que consultás stock ya mismo. Retené al cliente.
           - (PRIORIDAD 10 - FUEGO).

        CONTEXTO ACTUAL: {fecha_hoy} | {ctx_estado}

        FORMATO JSON OBLIGATORIO:
        {{ "respuesta": "Tu respuesta improvisada aquí...", "intencion": "Venta" | "Tecnico" | "Admin" | "General", "prioridad": 1-10, "status": "open" }}
        """

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in historial_previo:
            role = "assistant" if msg["role"] == "model" else msg["role"]
            messages.append({"role": role, "content": str(msg["content"])})
        messages.append({"role": "user", "content": texto_usuario})

        # --- 4. GENERACIÓN (Aumentamos Temperatura a 0.7 para naturalidad) ---
        completion = client.chat.completions.create(
            model=MODELO_ELEGIDO,
            messages=messages,
            temperature=0.7, # 🔥 MÁS CREATIVIDAD (Antes estaba en 0.4)
            max_tokens=800,
            response_format={"type": "json_object"}
        )

        content = completion.choices[0].message.content
        datos = json.loads(content)
        
        # Log para vos en la terminal
        print(f"🧠 CEREBRO: {datos.get('intencion')} | Prio: {datos.get('prioridad')}")
        
        return datos

    except Exception as e:
        logger.error(f"🚨 Falló Groq: {e}")
        return respuesta_basada_en_reglas(texto_usuario)


# --- AUDITOR DE CIERRE (Silencioso) ---
def analizar_prioridad_silenciosa(historial):
    """
    Evalúa si la conversación sigue viva o murió, sin responder.
    Usa temperatura 0.0 porque acá necesitamos precisión fría, no creatividad.
    """
    try:
        SYSTEM_PROMPT_AUDITOR = """
        ROL: Auditor CRM.
        TAREA: Clasificar el estado actual de la charla.
        CRITERIOS:
        - 🔥 VENTA/CONSULTA (Prioridad 8-10): Preguntas sobre precio, stock, canje, ubicación.
        - 🟡 SOPORTE/ADMIN (Prioridad 5-7): Reclamos, dudas técnicas.
        - 🟢 CERRADO/IRRELEVANTE (Prioridad 1-4): "Gracias", "Ok", "Nos vemos", saludos sin pregunta.
        
        OUTPUT JSON: { "intencion": "...", "prioridad": 1-10 }
        """
        messages = [{"role": "system", "content": SYSTEM_PROMPT_AUDITOR}]
        mensajes_recientes = historial[-6:] # Miramos los últimos 6 para tener contexto
        
        for msg in mensajes_recientes:
            role = "assistant" if msg["role"] in ["model","bot"] else "user"
            messages.append({"role": role, "content": str(msg["content"])})
            
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.0, # Frío y calculador
            max_tokens=150,
            response_format={"type": "json_object"}
        )
        return json.loads(completion.choices[0].message.content)
    except Exception:
        return {"intencion": "Error", "prioridad": 5}