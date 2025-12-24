import os
from dotenv import load_dotenv
from google import genai

# 1. Cargar clave
load_dotenv()
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

def analizar_prioridad(mensaje_cliente):
    """
    Usa Gemini 2.0 Flash Lite para clasificar mensajes.
    """
    print(f"🧠 Gemini pensando... Analizando: '{mensaje_cliente}'")
    
    prompt = f"""
    Actúa como clasificador para Nebitel. Asigna prioridad 0-100.
    
    CRITERIOS:
    - 0-20: Saludos, irrelevante.
    - 21-50: Ventas, consultas.
    - 51-80: Reclamos técnicos leves.
    - 81-100: URGENCIAS, cortes totales, furia.

    MENSAJE: "{mensaje_cliente}"
    RESPONDÉ SOLO EL NÚMERO.
    """

    try:
        # AQUI ESTÁ EL CAMBIO: Usamos el modelo que VIMOS en tu lista
        response = client.models.generate_content(
            model="gemini-2.0-flash-lite", 
            contents=prompt
        )
        return int(response.text.strip())

    except Exception as e:
        print(f"❌ Error Gemini: {e}")
        # Si falla por cuota, devolvemos 50 para seguir probando
        return 50

# --- PRUEBA FINAL ---
if __name__ == "__main__":
    print(f"Test Tranquilo: {analizar_prioridad('Hola, precio?')}")
    print(f"Test Furia: {analizar_prioridad('CORTARON TODO, LOS VOY A DENUNCIAR!')}")