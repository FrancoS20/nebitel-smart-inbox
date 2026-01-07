# cerebro.py

def procesar_mensaje(texto_usuario):
    """
    Recibe el texto del usuario y decide qué responder.
    Retorna el texto de la respuesta.
    """
    mensaje = texto_usuario.lower().strip()
    
    # --- TEXTOS PREDEFINIDOS ---
    texto_menu = (
        "👋 ¡Hola! Bienvenido a NEBITEL Tecnología.\n\n"
        "¿Qué estás buscando hoy?\n"
        "1️⃣ *Productos* (iPhone, Gaming, Accesorios)\n"
        "2️⃣ *Servicio Técnico* (Reparaciones)\n"
        "3️⃣ *Ubicación y Horarios*\n\n"
        "👉 Escribí tu consulta o el número de opción."
    )

    texto_ventas = (
        "🛒 *Zona de Ventas:*\n\n"
        "Tenemos lo último en:\n"
        "📱 *Apple:* iPhones, Apple Watch, AirPods.\n"
        "🎮 *Gaming:* Consolas, Joysticks, Teclados.\n"
        "🎧 *Audio y Accesorios:* Parlantes, Fundas, Cargadores.\n\n"
        "📌 Mirá el catálogo completo y precios en:\n"
        "👉 www.nebitel.com.ar\n\n"
        "Si buscás algo puntual (ej: 'Precio iPhone 13'), escribilo acá."
    )

    texto_tecnico = (
        "🛠️ *Servicio Técnico Especializado:*\n\n"
        "Reparamos iPhone, iPad, Apple Watch y más.\n"
        "Realizamos cambios de módulo, batería, pin de carga, etc.\n\n"
        "📍 Para un presupuesto estimado, decime:\n"
        "¿Qué equipo es y qué falla tiene?\n"
        "*(Ej: iPhone 11 no carga)*"
    )

    texto_info = (
        "📍 *Ubicación y Horarios:*\n\n"
        "🏠 Estamos en [TU DIRECCION REAL].\n"
        "⏰ Horarios: Lunes a Sábados de [HORA] a [HORA].\n\n"
        "¡Te esperamos en el local!"
    )
    
    # --- PALABRAS CLAVE ---
    keywords_tecnico = [
        "reparar", "arreglo", "arreglar", "cambio", "cambiar", "modulo", "pantalla", 
        "bateria", "pin", "carga", "roto", "servicio", "tecnico", "no anda", "falla", "mojado"
    ]
    
    keywords_ventas = [
        "precio", "comprar", "valor", "costo", "info", "modelo", "stock",
        "iphone", "samsung", "celular", "movil",
        "play", "ps4", "ps5", "xbox", "nintendo", "consola", "joystick", "gamer", "teclado", "mouse",
        "reloj", "watch", "smartwatch", "airpods", "auricular", "parlante", "funda", "cargador", "cable"
    ]

    keywords_info = ["donde", "ubicacion", "direccion", "calle", "horario", "abierto", "cerrado", "local"]
    keywords_humano = ["humano", "asesor", "vendedor", "persona", "atame", "hablar"]

    # --- LÓGICA DE DECISIÓN ---
    
    # 1. Técnico
    if any(x in mensaje for x in keywords_tecnico):
        return texto_tecnico

    # 2. Ventas
    elif any(x in mensaje for x in keywords_ventas):
        return texto_ventas

    # 3. Info
    elif any(x in mensaje for x in keywords_info):
        return texto_info

    # 4. Humano
    elif any(x in mensaje for x in keywords_humano):
        return "👤 ¡Dale! Ya le aviso a un vendedor para que siga tu consulta. Aguardá unos minutos..."

    # 5. Default
    else:
        return texto_menu