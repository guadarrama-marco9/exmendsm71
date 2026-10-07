import ollama
MODELO = "llama3.2"
print("=" * 50)
print("          TUTOR INTELIGENTE CON LLM")
print("=" * 50)
print("Modelo utilizado:", MODELO)
print()
print("Escribe 'salir' para terminar.")
print("Escribe 'resumen' para ver un resumen de la conversación.")
print()

while True:
    pregunta = input("Desarrollador: ")
    if pregunta.lower() == "salir":
        print()
        print("Sesión finalizada.")
        break
    if pregunta.lower() == "resumen":
        print()
        print("=" * 50)
        print("RESUMEN DE LA CONVERSACIÓN")
        print("=" * 50)
        print(f"Total de mensajes en el historial: {len(mensajes)}")
        print()
        for i, msg in enumerate(mensajes[1:], 1):  # Saltamos el mensaje del sistema
            rol = msg["role"].upper()
            contenido = msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"]
            print(f"{i}. [{rol}] {contenido}")
        print()
        print("-" * 50)
        continue
    mensajes.append(
        {
            "role": "user",
            "content": pregunta
        }
    )
    try:
          respuesta = ollama.chat(
            model=MODELO,
            messages=mensajes
        )

    except Exception as error:
        print()
        print("ERROR AL CONECTARSE CON EL LLM")
        print("--------------------------------")
        print(error)
        print()
        print("Verifica que Ollama esté ejecutándose.")
        mensajes.pop()
        continue
    contenido = respuesta["message"]["content"]
    mensajes.append(
        {
            "role": "assistant",
            "content": contenido
        }
    )
    print()
    print("TUTOR:")
    print()
    print(contenido)
    print()
    print("-" * 50)