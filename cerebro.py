import os
import google.generativeai as genai
import logging
import json
from datetime import datetime, timezone
from dotenv import load_dotenv

#  CONFIGURACIÓN INICIAL 
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
        #  Modelo Gemini 2.5 Flash
        model = genai.GenerativeModel('gemini-2.5-flash') 
        ia_activa = True
        logger.info("✅ Cerebro IA conectado (Identidad: Nebitel Paraná).")
    else:
        logger.warning("⚠️ No se encontró GEMINI_API_KEY. Usando modo Manual.")
except Exception as e:
    logger.error(f"❌ Error al iniciar la IA: {e}")

# CEREBRO DE RESPALDO (Plan B - Reglas Fijas)
def respuesta_basada_en_reglas(texto_usuario):
    """
    Se activa si la IA falla o explota. 
    Devuelve un DICCIONARIO para no romper el webhook.
    """
    mensaje = texto_usuario.lower().strip()
    
    # Textos predefinidos con las direcciones exactas
    texto_ventas = "🛒 Para precios y stock, podés ver todo actualizado en www.nebitel.com.ar"
    texto_tecnico = "🛠️ Para cotizar una reparación, decime: ¿Qué modelo es y qué falla tiene?"
    texto_info = "📍 Estamos en Paraná: Santa Fe 27, Av. P. Zanni 1597 de 8:30 a 12:30hs / 16:30 a 20:30hs y Shopping Paso del Paraná 10 a 21hs (Horario Corrrido)."
    texto_default = "👋 ¡Hola! Bienvenido a NEBITEL. En breve te atiende un humano."

    respuesta_final = texto_default
    intencion = "General"
    prioridad = 5

    if any(x in mensaje for x in ["reparar", "arreglo", "roto", "falla", "2"]):
        respuesta_final = texto_tecnico
        intencion = "Tecnico"
        prioridad = 6
    elif any(x in mensaje for x in ["precio", "comprar", "iphone", "stock", "1", "valor", "sale"]):
        respuesta_final = texto_ventas
        intencion = "Venta"
        prioridad = 5
    elif any(x in mensaje for x in ["donde", "ubicacion", "horario", "3"]):
        respuesta_final = texto_info
        intencion = "Info"
        prioridad = 2

    return {
        "respuesta": respuesta_final,
        "prioridad": prioridad,
        "intencion": intencion,
        "status": "open"
    }

#  CEREBRO PRINCIPAL (IA + Contexto + JSON) 
def procesar_mensaje(texto_usuario, historial_previo=[]):
    """
    Función principal inteligente con identidad de Paraná y salida Estructurada.
    """
    global ia_activa
    
    # ANÁLISIS TEMPORAL 
    instruccion_saludo = "✅ Podés saludar cortésmente (Hola, Buen día)."
    tiempo_texto = "Desconocido"

    if historial_previo:
        ultimo_mensaje = historial_previo[-1]
        if 'timestamp' in ultimo_mensaje and ultimo_mensaje['timestamp']:
            try:
                hora_ultimo = ultimo_mensaje['timestamp']
                # Corrección Zona Horaria (UTC)
                if hora_ultimo.tzinfo is None:
                    hora_ultimo = hora_ultimo.replace(tzinfo=timezone.utc)
                ahora_utc = datetime.now(timezone.utc)
                
                diferencia = ahora_utc - hora_ultimo
                minutos = int(diferencia.total_seconds() / 60)
                if minutos < 0: minutos = 0
                tiempo_texto = f"{minutos} minutos"

                # Regla de fluidez (15 mins)
                if minutos < 15:
                    instruccion_saludo = "⛔️ PROHIBIDO SALUDAR (Hola, Buen día). La charla es fluida. Andá al grano."
                else:
                    instruccion_saludo = "✅ Pasó un tiempo, podés saludar de nuevo."
            except Exception as e:
                logger.warning(f"⚠️ No se pudo calcular tiempo: {e}")

    # IA CON LÓGICA DE NEGOCIO Y ESTRUCTURA JSON 
    if ia_activa:
        try:
            fecha_hoy = datetime.now().strftime("%d/%m/%Y %H:%M")
            
            # Formatear historial
            guion_chat = ""
            if historial_previo:
                for msg in historial_previo:
                    nombre = "Cliente" if msg['role'] == 'user' else "Nebitel"
                    contenido = str(msg['content']).replace('\n', ' ')
                    guion_chat += f"- {nombre}: {contenido}\n"

            # PROMPT MAESTRO
            prompt_sistema = f"""
            ROL: Sos un asistente de ventas de NEBITEL (Tienda de tecnología en PARANÁ, Entre Ríos).
            Tu misión es responder con naturalidad Y clasificar el mensaje internamente en formato JSON.
            
            UBICACIONES REALES:
            - Centro: Santa Fe 27 (Horario: 8:30 a 12:30 / 16:30 a 20:30).
            - Zanni: Av. P. Zanni 1597 (Horario: 8:30 a 12:30 / 16:30 a 20:30).
            - Shopping: Shopping Paso del Paraná (Horario corrido 10 a 21hs).
            
            PERSONALIDAD:
            - Sos un paranaense más. Hablás natural, usás "vos".
            - Tono: Amigable ("dale", "fijate", "capaz", "chiflá").
            - Emojis: Moderados.
            
            REGLAS DE ORO (NEGOCIO):
            1. PRECIOS: NO des precios fijos. Decí: "Los precios varían, fijate los actualizados en la web: www.nebitel.com.ar".
            2. TÉCNICA: Si dicen "se me rompió", preguntá MODELO y FALLA.
            3. PLAN CANJE (PRIORIDAD ALTA):
               - SI tomamos usados (iPhone).
               - RESPUESTA: "Sisi, tomamos usados! 📱 Decime modelo, gigas y batería así le paso el dato a un vendedor humano para que te lo cotice."
               - NO cotices vos. Derivá.
            
            CRITERIOS DE CLASIFICACIÓN (JSON):
            - Prioridad 10: Venta cerrada, Urgencia técnica.
            - Prioridad 8: Plan Canje, Stock específico.
            - Prioridad 5: Precios generales.
            - Prioridad 1: Saludos finales.
            
            CONTEXTO:
            - Fecha: {fecha_hoy}. Tiempo inactivo: {tiempo_texto}.
            - Saludo: {instruccion_saludo}
            
            EJEMPLOS DE RESPUESTA (Output JSON):
            
            Caso 1: Venta (Precios)
            Usuario: "precio del iphone 15?"
            JSON: {{
                "respuesta": "Hola! 👋 Mirá, los precios cambian seguido por el dólar. Te conviene fijarte en la web www.nebitel.com.ar que está todo actualizado.",
                "intencion": "Venta",
                "prioridad": 5,
                "status": "open"
            }}
            
            Caso 2: Técnico
            Usuario: "no me carga el pin"
            JSON: {{
                "respuesta": "Uh, qué macana. 😕 ¿Qué modelo es el equipo? Así le consulto a los chicos del taller.",
                "intencion": "Tecnico",
                "prioridad": 6,
                "status": "open"
            }}

            Caso 3: Plan Canje (Lead Calificado)
            Usuario: "toman usados en parte de pago?"
            JSON: {{
                "respuesta": "Sisi, tomamos! 📱 Decime qué modelo es, cuántos gigas tiene y cómo está de batería, así le paso el dato a un vendedor para que te lo cotice ya.",
                "intencion": "Plan Canje",
                "prioridad": 8,
                "status": "open"
            }}
            
            Caso 4: Cierre
            Usuario: "gracias capo"
            JSON: {{
                "respuesta": "De nada! Cualquier cosa chiflá. 😉",
                "intencion": "Cierre",
                "prioridad": 1,
                "status": "closed"
            }}

            INPUT REAL:
            {guion_chat}
            Cliente: "{texto_usuario}"
            
            OUTPUT OBLIGATORIO (JSON PURO):
            """
            
            # Generar respuesta
            response = model.generate_content(prompt_sistema)
            
            # Limpiar JSON (quitar ```json y ```)
            texto_limpio = response.text.replace("```json", "").replace("```", "").strip()
            
            return json.loads(texto_limpio)

        except Exception as e:
            logger.error(f"🚨 Falló la IA o el JSON (Error: {e}). Usando reglas fijas.")
            # Si falla la IA, se usa el Plan B que ahora devuelve diccionario
            return respuesta_basada_en_reglas(texto_usuario)
            
    # Caso Sin IA (Modo Manual)
    else:
        return respuesta_basada_en_reglas(texto_usuario)