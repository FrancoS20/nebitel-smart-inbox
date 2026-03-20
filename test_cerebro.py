import cerebro

print("==================================================")
print("🧠 LABORATORIO DEL CEREBRO NEBITEL (MODO TERMINAL)")
print("Escribí 'salir' para terminar la prueba.")
print("==================================================\n")

# Memoria de la sesión (Para que no tenga amnesia)
historial = []

while True:
    texto = input("👤 Cliente (Vos): ")
    
    if texto.lower() in ['salir', 'exit', 'quit']:
        print("👋 Cerrando laboratorio...")
        break
        
    # Llamamos a tu código pasándole el historial!
    resultado = cerebro.procesar_mensaje(texto, historial_previo=historial)
    
    print("\n🤖 Bot:", resultado['respuesta'])
    print("--------------------------------------------------")
    print(f"📊 Intención: {resultado.get('intencion')}")
    print(f"🔥 Prioridad: {resultado.get('prioridad')}")
    print(f"🛑 Handoff (Pasar a humano): {resultado.get('necesita_humano')}")
    print("==================================================\n")
    
    # Guardamos los mensajes en el historial para la próxima vuelta
    historial.append({"role": "user", "content": texto})
    historial.append({"role": "assistant", "content": resultado['respuesta']})