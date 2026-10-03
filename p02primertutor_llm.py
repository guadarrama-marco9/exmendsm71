


import ollama


# ------------------------------------------------------------
# 2. CONFIGURACIÓN DEL MODELO
# ------------------------------------------------------------

MODELO = "llama3.2"


# ------------------------------------------------------------
# 3. CONFIGURACIÓN DEL SISTEMA
# ------------------------------------------------------------
#
# El mensaje "system" establece el comportamiento general
# que queremos que tenga nuestro asistente.
#
# ------------------------------------------------------------

mensaje_sistema = """
Eres un experto en desarrollo de software y arquitectura de sistemas.

Tu función es ayudar a desarrolladores junior y estudiantes de ingeniería.

Debes:

1. Explicar los conceptos de arquitectura de software de manera clara.
2. Utilizar ejemplos prácticos del mundo real.
3. Explicar los procedimientos paso a paso, incluyendo diagramas conceptuales.
4. Evitar respuestas excesivamente técnicas cuando
   el desarrollador sea principiante.
5. Cuando sea posible, proporcionar ejemplos en Python, JavaScript o Java.
6. Si el desarrollador comete un error, explicarle
   cómo corregirlo y por qué ocurrió.
7. No proporcionar únicamente la respuesta final.
8. Explicar el razonamiento y los conceptos necesarios
# para comprender el problema.
9. Sugerir mejores prácticas y patrones de diseño cuando sea apropiado.
10. Ayudar a entender patrones como MVC, Repository, Factory, etc.
"""


# ------------------------------------------------------------
# 4. CREAR HISTORIAL
# ------------------------------------------------------------
#
# El historial permitirá que posteriormente nuestro programa
# pueda mantener el contexto de la conversación.
#
# ------------------------------------------------------------

mensajes = [

    {
        "role": "system",
        "content": mensaje_sistema
    }

]


# ------------------------------------------------------------
# 5. ENCABEZADO DEL PROGRAMA
# ------------------------------------------------------------

print("=" * 50)
print("          TUTOR INTELIGENTE CON LLM")
print("=" * 50)

print("Modelo utilizado:", MODELO)
print()
print("Escribe 'salir' para terminar.")
print("Escribe 'resumen' para ver un resumen de la conversación.")
print()


# ------------------------------------------------------------
# 6. BUCLE PRINCIPAL
# ------------------------------------------------------------

while True:

    # --------------------------------------------------------
    # Solicitar pregunta
    # --------------------------------------------------------

    pregunta = input("Desarrollador: ")


    # --------------------------------------------------------
    # Comprobar si desea terminar
    # --------------------------------------------------------

    if pregunta.lower() == "salir":

        print()
        print("Sesión finalizada.")

        break


    # --------------------------------------------------------
    # Comprobar si desea resumen del historial
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # Agregar pregunta al historial
    # --------------------------------------------------------

    mensajes.append(
        {
            "role": "user",
            "content": pregunta
        }
    )


    # --------------------------------------------------------
    # ENVIAR INFORMACIÓN AL LLM
    # --------------------------------------------------------

    try:

        respuesta = ollama.chat(

            model=MODELO,

            messages=mensajes

        )


    # --------------------------------------------------------
    # MANEJO DE ERRORES
    # --------------------------------------------------------

    except Exception as error:

        print()
        print("ERROR AL CONECTARSE CON EL LLM")
        print("--------------------------------")

        print(error)

        print()

        print("Verifica que Ollama esté ejecutándose.")

        # Eliminamos la pregunta del historial porque
        # no pudo ser procesada.

        mensajes.pop()

        continue


    # --------------------------------------------------------
    # EXTRAER RESPUESTA
    # --------------------------------------------------------

    contenido = respuesta["message"]["content"]


    # --------------------------------------------------------
    # GUARDAR RESPUESTA EN EL HISTORIAL
    # --------------------------------------------------------

    mensajes.append(
        {
            "role": "assistant",
            "content": contenido
        }
    )


    # --------------------------------------------------------
    # MOSTRAR RESPUESTA
    # --------------------------------------------------------

    print()
    print("TUTOR:")
    print()

    print(contenido)

    print()
    print("-" * 50)


# python -m py_compile unidad2_fia/p02primer_llm.py (comprueba que la sintaxis de python es correcta)

        #       SYSTEM
        #         │
        #         ▼
        #    Comportamiento
        #         │
        #         ▼
# USER ────────► LLM
        #         │
        #         ▼
        #      ASSISTANT
