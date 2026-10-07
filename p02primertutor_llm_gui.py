

import ollama
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime
from threading import Thread
MODELO = "llama3.2"


class TutorInteligenteGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Tutor Inteligente con LLM")
        self.root.geometry("900x700")
        
        self.mensajes = [
            {"role": "system", "content": mensaje_sistema}
        ]
        
        self.configurar_estilos()
        
        self.crear_interfaz()
    
    def configurar_estilos(self):
        """Configura los estilos de la interfaz."""
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Configurar colores
        self.style.configure('TFrame', background='#f0f0f0')
        self.style.configure('TLabel', background='#f0f0f0', font=('Arial', 10))
        self.style.configure('TButton', font=('Arial', 10, 'bold'))
        self.style.configure('Header.TLabel', font=('Arial', 14, 'bold'), background='#2c3e50', foreground='white')
        self.style.configure('Info.TLabel', font=('Arial', 9), background='#f0f0f0', foreground='#555')
    
    def crear_interfaz(self):
        """Crea todos los componentes de la interfaz gráfica."""
        
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        header_label = ttk.Label(
            header_frame, 
            text="TUTOR INTELIGENTE CON LLM",
            style='Header.TLabel'
        )
        header_label.pack(fill=tk.X, ipady=10)
        
        info_frame = ttk.Frame(main_frame)
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        modelo_label = ttk.Label(
            info_frame,
            text=f"Modelo: {MODELO} | Estado: Conectado",
            style='Info.TLabel'
        )
        modelo_label.pack(side=tk.LEFT)
        
        chat_frame = ttk.LabelFrame(main_frame, text="Conversación", padding=10)
        chat_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.chat_area = scrolledtext.ScrolledText(
            chat_frame,
            wrap=tk.WORD,
            font=('Arial', 10),
            bg='white',
            padx=10,
            pady=10
        )
        self.chat_area.pack(fill=tk.BOTH, expand=True)
        
        # Configurar tags para colorear mensajes
        self.chat_area.tag_config('user', foreground='#1e3a8a', font=('Arial', 10, 'bold'))
        self.chat_area.tag_config('assistant', foreground='#27ae60', font=('Arial', 10))
        self.chat_area.tag_config('system', foreground='#7f8c8d', font=('Arial', 9, 'italic'))
        
        input_frame = ttk.Frame(main_frame)
        input_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(input_frame, text="Tu pregunta:").pack(anchor=tk.W)
        
        self.input_text = ttk.Entry(input_frame, font=('Arial', 11))
        self.input_text.pack(fill=tk.X, pady=(5, 10))
        self.input_text.bind('<Return>', lambda e: self.enviar_mensaje())
        
        button_frame = ttk.Frame(input_frame)
        button_frame.pack(fill=tk.X)
        
        self.enviar_btn = ttk.Button(
            button_frame,
            text="Enviar",
            command=self.enviar_mensaje
        )
        self.enviar_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.resumen_btn = ttk.Button(
            button_frame,
            text="Ver Resumen",
            command=self.mostrar_resumen
        )
        self.resumen_btn.pack(side=tk.LEFT, padx=5)
        
        self.limpiar_btn = ttk.Button(
            button_frame,
            text=" Limpiar Chat",
            command=self.limpiar_chat
        )
        self.limpiar_btn.pack(side=tk.LEFT, padx=5)
        
        self.salir_btn = ttk.Button(
            button_frame,
            text="Salir",
            command=self.root.quit
        )
        self.salir_btn.pack(side=tk.RIGHT)
        
        self.status_var = tk.StringVar(value="Listo para ayudar")
        status_bar = ttk.Label(
            main_frame,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        status_bar.pack(fill=tk.X, pady=(10, 0))
        
        self.agregar_mensaje_chat(
            "system",
            "Soy tu tutor de arquitectura de software. Escribe tu pregunta y presiona Enter o clic en Enviar."
        )
    
    def agregar_mensaje_chat(self, rol, contenido):
        """Agrega un mensaje al área de chat con formato."""
        self.chat_area.insert(tk.END, f"\n{rol.upper()}: ", rol)
        self.chat_area.insert(tk.END, contenido + "\n")
        self.chat_area.see(tk.END)
    
    def enviar_mensaje(self):
        """Envía el mensaje del usuario al LLM."""
        pregunta = self.input_text.get().strip()
        
        if not pregunta:
            messagebox.showwarning("Advertencia", "Por favor escribe una pregunta.")
            return
        
        self.input_text.delete(0, tk.END)
        
        self.agregar_mensaje_chat("user", pregunta)
        
        self.mensajes.append({
            "role": "user",
            "content": pregunta
        })
        
        self.enviar_btn.config(state=tk.DISABLED)
        self.status_var.set("Procesando respuesta...")
        
        thread = Thread(target=self.procesar_respuesta_llm)
        thread.daemon = True
        thread.start()
    
    def procesar_respuesta_llm(self):
        """Procesa la respuesta del LLM en un hilo separado."""
        try:
            respuesta = ollama.chat(
                model=MODELO,
                messages=self.mensajes
            )
            
            contenido = respuesta["message"]["content"]
            
            self.mensajes.append({
                "role": "assistant",
                "content": contenido
            })
            
            self.root.after(0, lambda: self.mostrar_respuesta(contenido))
            
        except Exception as error:
            self.mensajes.pop()
            error_msg = f"Error al conectar con el LLM: {error}\nVerifica que Ollama esté ejecutándose."
            self.root.after(0, lambda: self.mostrar_error(error_msg))
    
    def mostrar_respuesta(self, contenido):
        """Muestra la respuesta del LLM en la GUI."""
        self.agregar_mensaje_chat("assistant", contenido)
        self.enviar_btn.config(state=tk.NORMAL)
        self.status_var.set("Respuesta recibida")
    
    def mostrar_error(self, mensaje):
        """Muestra un mensaje de error."""
        self.agregar_mensaje_chat("system", mensaje)
        self.enviar_btn.config(state=tk.NORMAL)
        self.status_var.set("Error en la conexión")
    
    def mostrar_resumen(self):
        """Muestra una ventana con el resumen de la conversación."""
        ventana_resumen = tk.Toplevel(self.root)
        ventana_resumen.title("Resumen de la Conversación")
        ventana_resumen.geometry("600x500")
        
        frame = ttk.Frame(ventana_resumen, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(
            frame,
            text="RESUMEN DE LA CONVERSACIÓN",
            font=('Arial', 12, 'bold')
        ).pack(pady=(0, 10))
        
        info_text = f"Total de mensajes: {len(self.mensajes)}\n"
        info_text += f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        ttk.Label(frame, text=info_text, font=('Arial', 10)).pack(anchor=tk.W, pady=(0, 10))
        
        resumen_area = scrolledtext.ScrolledText(
            frame,
            wrap=tk.WORD,
            font=('Arial', 9),
            bg='white',
            padx=10,
            pady=10
        )
        resumen_area.pack(fill=tk.BOTH, expand=True)
        
        for i, msg in enumerate(self.mensajes[1:], 1):
            rol = msg["role"].upper()
            contenido = msg["content"]
            
            if len(contenido) > 150:
                contenido = contenido[:150] + "..."
            
            resumen_area.insert(tk.END, f"{i}. [{rol}]\n")
            resumen_area.insert(tk.END, f"   {contenido}\n\n")
        
        resumen_area.config(state=tk.DISABLED)
        
        ttk.Button(
            frame,
            text="Cerrar",
            command=ventana_resumen.destroy
        ).pack(pady=(10, 0))
    
    def limpiar_chat(self):
        """Limpia el área de chat pero mantiene el historial."""
        if messagebox.askyesno("Confirmar", "¿Deseas limpiar el chat? El historial se mantendrá."):
            self.chat_area.delete(1.0, tk.END)
            self.agregar_mensaje_chat(
                "system",
                "Chat limpiado. El historial de la conversación se ha mantenido."
            )
            self.status_var.set("Chat limpiado")



if __name__ == "__main__":
    root = tk.Tk()
    app = TutorInteligenteGUI(root)
    root.mainloop()
