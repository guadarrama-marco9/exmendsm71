
import json
import logging
import os
import re
import sys
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict

# GUI
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog

# MongoDB
try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, PyMongoError
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    print("ADVERTENCIA: pymongo no instalado. Se usará modo simulación.")

# Ollama
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    print("ADVERTENCIA: ollama no instalado. Se usará modo simulación.")

# Configuración de logging
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("logismart")


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

@dataclass
class Config:
    """Configuración centralizada del sistema."""
    
    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017/"
    mongodb_database: str = "logismart"
    
    # Ollama
    ollama_model: str = "llama3.2"
    ollama_timeout: int = 30
    
    # Sistema
    modo_simulacion: bool = True
    
    @classmethod
    def from_env(cls) -> 'Config':
        """Carga configuración desde variables de entorno."""
        return cls(
            mongodb_uri=os.environ.get("MONGODB_URI", "mongodb://localhost:27017/"),
            mongodb_database=os.environ.get("MONGODB_DATABASE", "logismart"),
            ollama_model=os.environ.get("OLLAMA_MODEL", "llama3.2"),
            modo_simulacion=os.environ.get("MODO_SIMULACION", "true").lower() == "true"
        )


config = Config.from_env()


# =============================================================================
# MÓDULO 1: PERSISTENCIA EN MONGODB
# =============================================================================

class MongoDBManager:
    """Gestiona la conexión y operaciones con MongoDB."""
    
    def __init__(self, uri: str = None, database: str = None):
        self.uri = uri or config.mongodb_uri
        self.database_name = database or config.mongodb_database
        self.client = None
        self.db = None
        self.conectado = False
    
    def conectar(self) -> bool:
        """Establece conexión con MongoDB."""
        if not MONGODB_AVAILABLE:
            log.warning("MongoDB no disponible, usando modo simulación")
            return False
        
        try:
            self.client = MongoClient(self.uri, serverSelectionTimeoutMS=5000)
            self.client.admin.command('ping')
            self.db = self.client[self.database_name]
            self.conectado = True
            log.info(f"Conectado a MongoDB: {self.database_name}")
            return True
        except (ConnectionFailure, Exception) as e:
            log.error(f"Error conectando a MongoDB: {e}")
            self.conectado = False
            return False
    
    def desconectar(self):
        """Cierra la conexión con MongoDB."""
        if self.client:
            self.client.close()
            self.conectado = False
            log.info("Desconectado de MongoDB")
    
    def insertar(self, coleccion: str, documento: Dict) -> Optional[str]:
        """Inserta un documento en una colección."""
        if not self.conectado:
            return self._simular_insertar(coleccion, documento)
        
        try:
            resultado = self.db[coleccion].insert_one(documento)
            return str(resultado.inserted_id)
        except PyMongoError as e:
            log.error(f"Error insertando en {coleccion}: {e}")
            return None
    
    def buscar(self, coleccion: str, filtro: Dict = None) -> List[Dict]:
        """Busca documentos en una colección."""
        if not self.conectado:
            return self._simular_buscar(coleccion, filtro)
        
        try:
            return list(self.db[coleccion].find(filtro or {}))
        except PyMongoError as e:
            log.error(f"Error buscando en {coleccion}: {e}")
            return []
    
    def actualizar(self, coleccion: str, filtro: Dict, actualizacion: Dict) -> bool:
        """Actualiza documentos en una colección."""
        if not self.conectado:
            return True  # Simulación exitosa
        
        try:
            resultado = self.db[coleccion].update_many(filtro, actualizacion)
            return resultado.modified_count > 0
        except PyMongoError as e:
            log.error(f"Error actualizando {coleccion}: {e}")
            return False
    
    def eliminar(self, coleccion: str, filtro: Dict) -> bool:
        """Elimina documentos de una colección."""
        if not self.conectado:
            return True  # Simulación exitosa
        
        try:
            resultado = self.db[coleccion].delete_many(filtro)
            return resultado.deleted_count > 0
        except PyMongoError as e:
            log.error(f"Error eliminando de {coleccion}: {e}")
            return False
    
    def agregar(self, coleccion: str, pipeline: List) -> List[Dict]:
        """Ejecuta una operación de agregación."""
        if not self.conectado:
            return self._simular_agregar(coleccion, pipeline)
        
        try:
            return list(self.db[coleccion].aggregate(pipeline))
        except PyMongoError as e:
            log.error(f"Error en agregación {coleccion}: {e}")
            return []
    
    # Métodos de simulación para cuando MongoDB no está disponible
    def _simular_insertar(self, coleccion: str, documento: Dict) -> str:
        if not hasattr(self, '_simulacion_data'):
            self._simulacion_data = {}
        if coleccion not in self._simulacion_data:
            self._simulacion_data[coleccion] = []
        documento['_id'] = f"sim_{len(self._simulacion_data[coleccion])}"
        self._simulacion_data[coleccion].append(documento)
        return documento['_id']
    
    def _simular_buscar(self, coleccion: str, filtro: Dict = None) -> List[Dict]:
        if not hasattr(self, '_simulacion_data'):
            return []
        return self._simulacion_data.get(coleccion, [])
    
    def _simular_agregar(self, coleccion: str, pipeline: List) -> List[Dict]:
        # Simulación básica de agregación
        datos = self._simular_buscar(coleccion)
        return [{"count": len(datos)}]


# =============================================================================
# MÓDULO 2: MOTOR DE REGLAS LÓGICAS
# =============================================================================

@dataclass
class ReglaLogica:
    """Representa una regla lógica del sistema."""
    nombre: str
    formula: str
    descripcion: str
    variables: List[str]
    
    def evaluar(self, **kwargs) -> bool:
        """Evalúa la regla con los valores dados."""
        try:
            # Mapeo de operadores lógicos
            contexto = {k: v for k, v in kwargs.items()}
            
            # Evaluación segura de la fórmula
            # Reemplazar operadores lógicos con Python
            formula_python = self.formula.replace('∧', ' and ').replace('∨', ' or ').replace('¬', ' not ')
            
            return eval(formula_python, {"__builtins__": {}}, contexto)
        except Exception as e:
            log.error(f"Error evaluando regla {self.nombre}: {e}")
            return False


class MotorReglas:
    """Motor de reglas lógicas para el sistema LogiSmart."""
    
    def __init__(self):
        self.reglas = self._inicializar_reglas()
    
    def _inicializar_reglas(self) -> Dict[str, ReglaLogica]:
        """Inicializa las reglas del sistema."""
        return {
            "acceso_estandar": ReglaLogica(
                nombre="Acceso Estándar",
                formula="P and S and not Q",
                descripcion="Autorización previa AND conductor certificado AND SIN exceso de peso",
                variables=["P", "Q", "S"]
            ),
            "inspeccion_especial": ReglaLogica(
                nombre="Inspección Especial",
                formula="P and (R or Q)",
                descripcion="Autorización previa AND (carga peligrosa OR exceso de peso)",
                variables=["P", "Q", "R"]
            ),
            "certificacion_vigente": ReglaLogica(
                nombre="Certificación Vigente",
                formula="S and V",
                descripcion="Conductor certificado AND certificación vigente (no expirada)",
                variables=["S", "V"]
            ),
            "horario_restringido": ReglaLogica(
                nombre="Horario Restringido",
                formula="R and H",
                descripcion="Carga peligrosa AND horario restringido (noche/fin de semana)",
                variables=["R", "H"]
            )
        }
    
    def evaluar_camion(self, P: bool, Q: bool, R: bool, S: bool, 
                       V: bool = True, H: bool = False) -> Dict[str, Any]:
        """
        Evalúa todas las reglas para un camión.
        
        Parámetros:
        P: Tiene autorización previa
        Q: El peso excede el límite
        R: Carga con materiales peligrosos
        S: Conductor con certificación vigente
        V: Certificación no expirada (nueva variable)
        H: Horario restringido (nueva variable)
        """
        # Validación de tipos
        for nombre, valor in [("P", P), ("Q", Q), ("R", R), ("S", S), ("V", V), ("H", H)]:
            if not isinstance(valor, bool):
                raise TypeError(f"La premisa {nombre} debe ser bool")
        
        resultados = {}
        explicaciones = []
        
        # Evaluar cada regla
        for nombre_regla, regla in self.reglas.items():
            try:
                # Obtener solo las variables que necesita la regla
                vars_regla = {v: locals()[v] for v in regla.variables}
                resultado = regla.evaluar(**vars_regla)
                resultados[nombre_regla] = resultado
                
                if resultado:
                    explicaciones.append(f"{regla.descripcion}: ACTIVO")
            except Exception as e:
                log.error(f"Error evaluando {nombre_regla}: {e}")
                resultados[nombre_regla] = False
        
        return {
            "resultados": resultados,
            "explicaciones": explicaciones,
            "permite_acceso": resultados.get("acceso_estandar", False),
            "requiere_inspeccion": resultados.get("inspeccion_especial", False),
            "certificacion_valida": resultados.get("certificacion_vigente", False),
            "horario_restringido_activo": resultados.get("horario_restringido", False)
        }
    
    def generar_tabla_verdad(self) -> List[Dict]:
        """Genera la tabla de verdad completa para las reglas principales."""
        import itertools
        
        filas = []
        # Para las reglas principales (P, Q, R, S)
        for P, Q, R, S in itertools.product([True, False], repeat=4):
            resultado = self.evaluar_camion(P, Q, R, S)
            filas.append({
                "P": P, "Q": Q, "R": R, "S": S,
                "acceso_estandar": resultado["permite_acceso"],
                "inspeccion_especial": resultado["requiere_inspeccion"]
            })
        return filas


# =============================================================================
# MÓDULO 3: CLASIFICADOR HÍBRIDO (REGLAS + LLM)
# =============================================================================

# Categorías y palabras clave
CATEGORIAS = {
    "materiales_peligrosos": ["peligroso", "derrame", "fuga", "quimico", "inflamable", "toxico", "corrosivo"],
    "sobrepeso": ["sobrepeso", "excede", "bascula", "exceso de peso", "sobrecarga"],
    "acceso_no_autorizado": ["sin autorizacion", "no autorizado", "acceso denegado", "barrera", "intruso"],
    "falla_hardware": ["camara", "sensor", "lector", "rfid", "no enciende", "apagado", "danado", "falla electrica"],
    "falla_software": ["sistema", "error", "pantalla", "caido", "no carga", "lento", "software", "aplicacion"],
    "somnolencia_conductor": ["somnolencia", "dormido", "cansancio", "fatiga", "sueno"],
}

PALABRAS_URGENTES = ["urgente", "emergencia", "accidente", "incendio", "herido", "critico", "inmediato"]

PRIORIDAD_BASE = {
    "materiales_peligrosos": "critica",
    "somnolencia_conductor": "alta",
    "acceso_no_autorizado": "alta",
    "sobrepeso": "media",
    "falla_hardware": "media",
    "falla_software": "baja",
    "otro": "baja",
}

ORDEN_PRIORIDAD = ["baja", "media", "alta", "critica"]


class ClasificadorReglas:
    """Clasificador basado en reglas."""
    
    @staticmethod
    def _normalizar(texto: str) -> str:
        """Normaliza texto para comparación."""
        tabla = str.maketrans("áéíóúüñ", "aeiouun")
        return texto.lower().translate(tabla)
    
    def clasificar(self, asunto: str, cuerpo: str) -> Dict[str, Any]:
        """Clasifica un incidente usando reglas."""
        texto = self._normalizar(f"{asunto} {cuerpo}")
        
        # Puntuación por categoría
        puntajes = {
            cat: [kw for kw in kws if kw in texto]
            for cat, kws in CATEGORIAS.items()
        }
        
        mejor_cat = max(puntajes, key=lambda c: len(puntajes[c]))
        if not puntajes[mejor_cat]:
            mejor_cat = "otro"
            coincidencias = []
        else:
            coincidencias = puntajes[mejor_cat]
        
        # Prioridad
        prioridad = PRIORIDAD_BASE[mejor_cat]
        urgentes = [p for p in PALABRAS_URGENTES if p in texto]
        if urgentes:
            idx = min(ORDEN_PRIORIDAD.index(prioridad) + 1, len(ORDEN_PRIORIDAD) - 1)
            prioridad = ORDEN_PRIORIDAD[idx]
        
        return {
            "categoria": mejor_cat,
            "prioridad": prioridad,
            "palabras_clave": coincidencias + urgentes,
            "metodo": "reglas"
        }


class ClasificadorLLM:
    """Clasificador basado en LLM."""
    
    def __init__(self, modelo: str = config.ollama_model):
        self.modelo = modelo
        self.prompt_sistema = """
Eres un clasificador de incidentes de seguridad logística.
Analiza el correo y devuelve ÚNICAMENTE un JSON válido con esta estructura:
{
    "categoria": "materiales_peligrosos|sobrepeso|acceso_no_autorizado|falla_hardware|falla_software|somnolencia_conductor|otro",
    "prioridad": "baja|media|alta|critica",
    "entidades": {
        "placa": "string o null",
        "camion_id": "string o null",
        "ubicacion": "string o null"
    },
    "resumen": "breve resumen del incidente"
}

Categorías:
- materiales_peligrosos: derrames, fugas, químicos
- sobrepeso: exceso de peso en báscula
- acceso_no_autorizado: intrusiones, barreras
- falla_hardware: cámaras, sensores, lectores
- falla_software: errores de sistema
- somnolencia_conductor: conductor cansado
- otro: cualquier otra cosa

Prioridades:
- critica: peligro inmediato, materiales peligrosos
- alta: seguridad, accidentes
- media: operacional
- baja: consultas, dudas
"""
    
    def clasificar(self, asunto: str, cuerpo: str, max_reintentos: int = 3) -> Dict[str, Any]:
        """Clasifica usando LLM con validación JSON."""
        if not OLLAMA_AVAILABLE:
            return self._fallback(asunto, cuerpo)
        
        prompt = f"Asunto: {asunto}\nCuerpo: {cuerpo}\n\nClasifica este incidente:"
        
        for intento in range(max_reintentos):
            try:
                respuesta = ollama.chat(
                    model=self.modelo,
                    messages=[
                        {"role": "system", "content": self.prompt_sistema},
                        {"role": "user", "content": prompt}
                    ],
                    options={"temperature": 0.3}
                )
                
                contenido = respuesta["message"]["content"]
                
                # Extraer JSON de la respuesta
                json_match = re.search(r'\{.*\}', contenido, re.DOTALL)
                if json_match:
                    resultado = json.loads(json_match.group())
                    resultado["metodo"] = "llm"
                    resultado["reintentos"] = intento + 1
                    return resultado
                
            except (json.JSONDecodeError, Exception) as e:
                log.warning(f"Intento {intento + 1} falló: {e}")
                continue
        
        # Fallback a reglas si falla LLM
        return self._fallback(asunto, cuerpo)
    
    def _fallback(self, asunto: str, cuerpo: str) -> Dict[str, Any]:
        """Fallback al clasificador de reglas."""
        clasificador = ClasificadorReglas()
        resultado = clasificador.clasificar(asunto, cuerpo)
        resultado["metodo"] = "llm_fallback_reglas"
        return resultado


class ClasificadorHibrido:
    """Clasificador que combina reglas y LLM."""
    
    def __init__(self):
        self.clasificador_reglas = ClasificadorReglas()
        self.clasificador_llm = ClasificadorLLM()
    
    def clasificar(self, asunto: str, cuerpo: str) -> Dict[str, Any]:
        """Clasifica usando ambos métodos y fusiona resultados."""
        # Clasificación por reglas
        resultado_reglas = self.clasificador_reglas.clasificar(asunto, cuerpo)
        
        # Clasificación por LLM
        resultado_llm = self.clasificador_llm.clasificar(asunto, cuerpo)
        
        # Fusión: prevalece la prioridad más alta
        prioridad_reglas = ORDEN_PRIORIDAD.index(resultado_reglas["prioridad"])
        prioridad_llm = ORDEN_PRIORIDAD.index(resultado_llm["prioridad"])
        
        if prioridad_reglas != prioridad_llm:
            # Discrepancia: usar prioridad más alta
            if prioridad_reglas > prioridad_llm:
                resultado_final = resultado_reglas
            else:
                resultado_final = resultado_llm
            resultado_final["requiere_revision_humana"] = True
        else:
            resultado_final = resultado_llm
            resultado_final["requiere_revision_humana"] = False
        
        resultado_final["fusion"] = {
            "reglas": resultado_reglas,
            "llm": resultado_llm
        }
        
        return resultado_final


# =============================================================================
# MÓDULO 4: ASISTENTE LLM EXPLICATIVO (RAG)
# =============================================================================

class AsistenteExplicativo:
    """Asistente LLM que explica decisiones basándose en datos de MongoDB."""
    
    def __init__(self, db_manager: MongoDBManager):
        self.db_manager = db_manager
        self.modelo = config.ollama_model
        self.prompt_sistema = """
Eres un asistente que explica decisiones del sistema LogiSmart.
Responde SOLO con la información proporcionada en el contexto.
Si no tienes información, responde "No tengo información sobre eso en los registros."
No inventes datos ni hagas suposiciones.
Sé conciso y claro.
"""
    
    def consultar(self, pregunta: str) -> Dict[str, Any]:
        """Consulta el sistema y genera una explicación."""
        if not OLLAMA_AVAILABLE:
            return {
                "respuesta": "LLM no disponible. Use el modo simulación.",
                "fuentes": []
            }
        
        # Extraer entidades de la pregunta (placa, camion_id, etc.)
        contexto = self._recuperar_contexto(pregunta)
        
        if not contexto:
            return {
                "respuesta": "No tengo información sobre eso en los registros.",
                "fuentes": []
            }
        
        # Construir prompt con contexto
        prompt_contexto = f"Contexto de registros:\n{json.dumps(contexto, ensure_ascii=False, indent=2)}\n\nPregunta: {pregunta}"
        
        try:
            respuesta = ollama.chat(
                model=self.modelo,
                messages=[
                    {"role": "system", "content": self.prompt_sistema},
                    {"role": "user", "content": prompt_contexto}
                ]
            )
            
            return {
                "respuesta": respuesta["message"]["content"],
                "fuentes": [doc.get("_id", "unknown") for doc in contexto],
                "contexto_usado": len(contexto)
            }
        except Exception as e:
            log.error(f"Error en asistente: {e}")
            return {
                "respuesta": f"Error al procesar la consulta: {e}",
                "fuentes": []
            }
    
    def _recuperar_contexto(self, pregunta: str) -> List[Dict]:
        """Recupera documentos relevantes de MongoDB."""
        contexto = []
        
        # Buscar placa
        placa_match = re.search(r'[A-Z0-9]{2,3}-\d{2,3}-[A-Z0-9]{1,2}', pregunta.upper())
        if placa_match:
            placa = placa_match.group(0)
            contexto.extend(self.db_manager.buscar("accesos", {"placa": placa}))
            contexto.extend(self.db_manager.buscar("incidentes", {"placa": placa}))
        
        # Buscar camion_id
        camion_match = re.search(r'CAM-\d+', pregunta.upper())
        if camion_match:
            camion_id = camion_match.group(0)
            contexto.extend(self.db_manager.buscar("accesos", {"camion_id": camion_id}))
        
        return contexto[:5]  # Limitar a 5 documentos más relevantes


# =============================================================================
# MÓDULO 5: MATRIZ DE RIESGOS ÉTICOS
# =============================================================================

@dataclass
class RiesgoEtico:
    """Riesgo ético del sistema."""
    descripcion: str
    categoria: str
    probabilidad: int  # 1-5
    impacto: int  # 1-5
    mitigacion: str = ""
    
    @property
    def puntaje(self) -> int:
        return self.probabilidad * self.impacto
    
    @property
    def nivel(self) -> str:
        p = self.puntaje
        if p >= 17:
            return "crítico"
        if p >= 10:
            return "alto"
        if p >= 5:
            return "medio"
        return "bajo"


class GestorRiesgos:
    """Gestiona la matriz de riesgos éticos."""
    
    CATEGORIAS_VALIDAS = {"sesgo", "privacidad", "transparencia", "seguridad", "responsabilidad", "otro"}
    
    def __init__(self, db_manager: MongoDBManager):
        self.db_manager = db_manager
        self.riesgos = self._cargar_riesgos_iniciales()
    
    def _cargar_riesgos_iniciales(self) -> List[RiesgoEtico]:
        """Carga riesgos iniciales del sistema."""
        return [
            RiesgoEtico(
                "Alucinaciones del LLM en clasificación de incidentes",
                "seguridad", 3, 4,
                "Validación JSON + fallback a reglas + revisión humana en discrepancias"
            ),
            RiesgoEtico(
                "Sesgo en correos con ortografía informal o dialectos regionales",
                "sesgo", 4, 3,
                "Entrenar LLM con datos diversos + normalización de texto"
            ),
            RiesgoEtico(
                "Privacidad de datos del conductor (video continuo, historial)",
                "privacidad", 4, 5,
                "Procesamiento en borde, retención limitada, cifrado, consentimiento"
            ),
            RiesgoEtico(
                "Dependencia excesiva de automatización sin supervisión humana",
                "responsabilidad", 3, 4,
                "Revisión humana de decisiones críticas + canal de apelación"
            ),
            RiesgoEtico(
                "Falsos positivos en detección de somnolencia por tono de piel",
                "sesgo", 3, 3,
                "Auditar datos de entrenamiento + umbral ajustable"
            ),
            RiesgoEtico(
                "Fuga de datos de placas y accesos desde MongoDB",
                "privacidad", 2, 5,
                "Cifrado en reposo, autenticación fuerte, auditoría de accesos"
            )
        ]
    
    def agregar_riesgo(self, riesgo: RiesgoEtico) -> bool:
        """Agrega un nuevo riesgo."""
        if riesgo.categoria not in self.CATEGORIAS_VALIDAS:
            raise ValueError(f"Categoría inválida: {riesgo.categoria}")
        self.riesgos.append(riesgo)
        return True
    
    def eliminar_riesgo(self, indice: int) -> bool:
        """Elimina un riesgo por índice."""
        if 0 <= indice < len(self.riesgos):
            self.riesgos.pop(indice)
            return True
        return False
    
    def calcular_riesgo_residual(self, indice: int, nueva_probabilidad:int = None, 
                                  nuevo_impacto: int = None) -> Dict[str, Any]:
        """Calcula el riesgo residual después de mitigación."""
        riesgo = self.riesgos[indice]
        puntaje_original = riesgo.puntaje
        
        prob = nueva_probabilidad if nueva_probabilidad is not None else riesgo.probabilidad
        imp = nuevo_impacto if nuevo_impacto is not None else riesgo.impacto
        puntaje_residual = prob * imp
        
        return {
            "original": puntaje_original,
            "residual": puntaje_residual,
            "reduccion": puntaje_original - puntaje_residual,
            "porcentaje_reduccion": round((puntaje_original - puntaje_residual) / puntaje_original * 100, 1)
        }
    
    def obtener_resumen(self) -> Dict[str, Any]:
        """Obtiene resumen de riesgos."""
        por_nivel = {"crítico": 0, "alto": 0, "medio": 0, "bajo": 0}
        por_categoria = {}
        
        for riesgo in self.riesgos:
            por_nivel[riesgo.nivel] += 1
            por_categoria[riesgo.categoria] = por_categoria.get(riesgo.categoria, 0) + 1
        
        puntajes = [r.puntaje for r in self.riesgos]
        
        return {
            "total": len(self.riesgos),
            "por_nivel": por_nivel,
            "por_categoria": por_categoria,
            "puntaje_promedio": round(sum(puntajes) / len(puntajes), 2) if puntajes else 0,
            "riesgos_ordenados": sorted(self.riesgos, key=lambda r: r.puntaje, reverse=True)
        }


# =============================================================================
# INTERFAZ GRÁFICA PRINCIPAL
# =============================================================================

class LogiSmartGUI:
    """Interfaz gráfica principal del sistema LogiSmart."""
    
    def __init__(self, root):
        self.root = root
        self.root.title("LogiSmart - Sistema de Control Inteligente")
        self.root.geometry("1200x800")
        
        # Inicializar componentes
        self.db_manager = MongoDBManager()
        self.motor_reglas = MotorReglas()
        self.clasificador_hibrido = ClasificadorHibrido()
        self.asistente = AsistenteExplicativo(self.db_manager)
        self.gestor_riesgos = GestorRiesgos(self.db_manager)
        
        # Conectar a MongoDB
        self.db_manager.conectar()
        
        # Configurar interfaz
        self.configurar_estilos()
        self.crear_interfaz()
        
        # Cargar datos de demostración
        self.cargar_datos_demo()
    
    def configurar_estilos(self):
        """Configura estilos de la interfaz."""
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Colores
        self.bg_color = '#f5f5f5'
        self.primary_color = '#2c3e50'
        self.accent_color = '#3498db'
        self.success_color = '#27ae60'
        self.warning_color = '#f39c12'
        self.danger_color = '#e74c3c'
        
        self.root.configure(bg=self.bg_color)
    
    def crear_interfaz(self):
        """Crea la interfaz principal."""
        # Notebook para pestañas
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Crear pestañas
        self.crear_pestana_control()
        self.crear_pestana_acceso()
        self.crear_pestana_tablas_verdad()
        self.crear_pestana_incidentes()
        self.crear_pestana_asistente()
        self.crear_pestana_riesgos()
        self.crear_pestana_reportes()
    
    def crear_pestana_control(self):
        """Pestaña de panel de control."""
        frame = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(frame, text="📊 Panel de Control")
        
        # Título
        ttk.Label(frame, text="Panel de Control", font=('Arial', 16, 'bold')).pack(pady=(0, 20))
        
        # Indicadores
        indicadores_frame = ttk.Frame(frame)
        indicadores_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.crear_indicador(indicadores_frame, "Camiones Atendidos", "156", self.success_color)
        self.crear_indicador(indicadores_frame, "Incidentes Abiertos", "3", self.warning_color)
        self.crear_indicador(indicadores_frame, "Riesgos Críticos", "2", self.danger_color)
        
        # Estado del sistema
        estado_frame = ttk.LabelFrame(frame, text="Estado del Sistema", padding=15)
        estado_frame.pack(fill=tk.X, pady=(0, 20))
        
        estado_db = "✅ Conectado" if self.db_manager.conectado else "⚠️ Simulación"
        estado_llm = "✅ Disponible" if OLLAMA_AVAILABLE else "⚠️ No disponible"
        
        ttk.Label(estado_frame, text=f"MongoDB: {estado_db}").pack(anchor=tk.W)
        ttk.Label(estado_frame, text=f"Ollama: {estado_llm}").pack(anchor=tk.W)
        ttk.Label(estado_frame, text=f"Modelo: {config.ollama_model}").pack(anchor=tk.W)
    
    def crear_indicador(self, parent, titulo, valor, color):
        """Crea un indicador visual."""
        frame = ttk.Frame(parent)
        frame.pack(side=tk.LEFT, expand=True, padx=10)
        
        canvas = tk.Canvas(frame, width=150, height=100, bg=color, highlightthickness=0)
        canvas.pack()
        
        canvas.create_text(75, 30, text=titulo, fill="white", font=('Arial', 10, 'bold'))
        canvas.create_text(75, 70, text=valor, fill="white", font=('Arial', 24, 'bold'))
    
    def crear_pestana_acceso(self):
        """Pestaña de control de acceso."""
        frame = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(frame, text="🚛 Control de Acceso")
        
        ttk.Label(frame, text="Control de Acceso", font=('Arial', 16, 'bold')).pack(pady=(0, 20))
        
        # Formulario de evaluación
        form_frame = ttk.LabelFrame(frame, text="Evaluar Camión", padding=15)
        form_frame.pack(fill=tk.X, pady=(0, 20))
        
        # Variables
        self.var_P = tk.BooleanVar(value=True)
        self.var_Q = tk.BooleanVar(value=False)
        self.var_R = tk.BooleanVar(value=False)
        self.var_S = tk.BooleanVar(value=True)
        
        # Checkboxes
        ttk.Checkbutton(form_frame, text="P: Autorización previa", variable=self.var_P).pack(anchor=tk.W, pady=5)
        ttk.Checkbutton(form_frame, text="Q: Exceso de peso", variable=self.var_Q).pack(anchor=tk.W, pady=5)
        ttk.Checkbutton(form_frame, text="R: Materiales peligrosos", variable=self.var_R).pack(anchor=tk.W, pady=5)
        ttk.Checkbutton(form_frame, text="S: Conductor certificado", variable=self.var_S).pack(anchor=tk.W, pady=5)
        
        # Botón evaluar
        ttk.Button(form_frame, text="Evaluar", command=self.evaluar_acceso).pack(pady=10)
        
        # Resultado
        resultado_frame = ttk.LabelFrame(frame, text="Resultado", padding=15)
        resultado_frame.pack(fill=tk.BOTH, expand=True)
        
        self.resultado_text = scrolledtext.ScrolledText(resultado_frame, height=10, font=('Arial', 10))
        self.resultado_text.pack(fill=tk.BOTH, expand=True)
    
    def crear_pestana_tablas_verdad(self):
        """Pestaña de simulador de tablas de verdad."""
        frame = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(frame, text="📐 Tablas de Verdad")
        
        ttk.Label(frame, text="Simulador de Tablas de Verdad", font=('Arial', 16, 'bold')).pack(pady=(0, 20))
        
        # Interruptores
        switches_frame = ttk.LabelFrame(frame, text="Variables", padding=15)
        switches_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.tv_P = tk.BooleanVar(value=False)
        self.tv_Q = tk.BooleanVar(value=False)
        self.tv_R = tk.BooleanVar(value=False)
        self.tv_S = tk.BooleanVar(value=False)
        
        for var, nombre in [(self.tv_P, "P"), (self.tv_Q, "Q"), (self.tv_R, "R"), (self.tv_S, "S")]:
            chk = ttk.Checkbutton(switches_frame, text=nombre, variable=var, command=self.actualizar_tabla_verdad)
            chk.pack(side=tk.LEFT, padx=20)
        
        # Resultado en vivo
        self.tabla_resultado = ttk.Label(frame, text="A: F | E: F", font=('Arial', 20, 'bold'))
        self.tabla_resultado.pack(pady=20)
    
    def crear_pestana_incidentes(self):
        """Pestaña de bandeja de incidentes."""
        frame = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(frame, text="📧 Bandeja de Incidentes")
        
        ttk.Label(frame, text="Bandeja de Incidentes", font=('Arial', 16, 'bold')).pack(pady=(0, 20))
        
        # Formulario de correo
        correo_frame = ttk.LabelFrame(frame, text="Nuevo Incidente", padding=15)
        correo_frame.pack(fill=tk.X, pady=(0, 20))
        
        ttk.Label(correo_frame, text="Asunto:").pack(anchor=tk.W)
        self.incidente_asunto = ttk.Entry(correo_frame, font=('Arial', 10))
        self.incidente_asunto.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(correo_frame, text="Cuerpo:").pack(anchor=tk.W)
        self.incidente_cuerpo = scrolledtext.ScrolledText(correo_frame, height=5, font=('Arial', 10))
        self.incidente_cuerpo.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(correo_frame, text="Clasificar Incidente", command=self.clasificar_incidente).pack()
        
        # Resultado de clasificación
        self.clasificacion_resultado = scrolledtext.ScrolledText(frame, height=15, font=('Arial', 10))
        self.clasificacion_resultado.pack(fill=tk.BOTH, expand=True, pady=(20, 0))
    
    def crear_pestana_asistente(self):
        """Pestaña de asistente LLM."""
        frame = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(frame, text="🤖 Asistente LLM")
        
        ttk.Label(frame, text="Asistente Explicativo", font=('Arial', 16, 'bold')).pack(pady=(0, 20))
        
        # Área de chat
        chat_frame = ttk.LabelFrame(frame, text="Chat", padding=15)
        chat_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.chat_area = scrolledtext.ScrolledText(chat_frame, height=15, font=('Arial', 10))
        self.chat_area.pack(fill=tk.BOTH, expand=True)
        
        # Entrada
        input_frame = ttk.Frame(frame)
        input_frame.pack(fill=tk.X)
        
        self.chat_input = ttk.Entry(input_frame, font=('Arial', 11))
        self.chat_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.chat_input.bind('<Return>', lambda e: self.enviar_pregunta_asistente())
        
        ttk.Button(input_frame, text="Preguntar", command=self.enviar_pregunta_asistente).pack(side=tk.RIGHT)
    
    def crear_pestana_riesgos(self):
        """Pestaña de riesgos éticos."""
        frame = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(frame, text="⚠️ Riesgos Éticos")
        
        ttk.Label(frame, text="Matriz de Riesgos Éticos", font=('Arial', 16, 'bold')).pack(pady=(0, 20))
        
        # Resumen
        resumen = self.gestor_riesgos.obtener_resumen()
        
        resumen_frame = ttk.LabelFrame(frame, text="Resumen", padding=15)
        resumen_frame.pack(fill=tk.X, pady=(0, 20))
        
        ttk.Label(resumen_frame, text=f"Total de riesgos: {resumen['total']}").pack(anchor=tk.W)
        ttk.Label(resumen_frame, text=f"Puntaje promedio: {resumen['puntaje_promedio']}").pack(anchor=tk.W)
        
        # Tabla de riesgos
        riesgos_frame = ttk.LabelFrame(frame, text="Riesgos Registrados", padding=15)
        riesgos_frame.pack(fill=tk.BOTH, expand=True)
        
        # Treeview
        columns = ("Descripción", "Categoría", "Probabilidad", "Impacto", "Puntaje", "Nivel")
        self.riesgos_tree = ttk.Treeview(riesgos_frame, columns=columns, show="headings")
        
        for col in columns:
            self.riesgos_tree.heading(col, text=col)
            self.riesgos_tree.column(col, width=150)
        
        self.riesgos_tree.pack(fill=tk.BOTH, expand=True)
        
        # Llenar treeview
        for riesgo in resumen['riesgos_ordenados']:
            self.riesgos_tree.insert("", tk.END, values=(
                riesgo.descripcion[:40],
                riesgo.categoria,
                riesgo.probabilidad,
                riesgo.impacto,
                riesgo.puntaje,
                riesgo.nivel
            ))
    
    def crear_pestana_reportes(self):
        """Pestaña de reportes."""
        frame = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(frame, text="📄 Reportes")
        
        ttk.Label(frame, text="Reportes", font=('Arial', 16, 'bold')).pack(pady=(0, 20))
        
        # Botones de exportación
        ttk.Button(frame, text="Exportar a JSON", command=self.exportar_json).pack(fill=tk.X, pady=5)
        ttk.Button(frame, text="Exportar a CSV", command=self.exportar_csv).pack(fill=tk.X, pady=5)
        ttk.Button(frame, text="Exportar a PDF", command=self.exportar_pdf).pack(fill=tk.X, pady=5)
    
    # -------------------------------------------------------------------------
    # MÉTODOS DE ACCIÓN
    # -------------------------------------------------------------------------
    
    def evaluar_acceso(self):
        """Evalúa el acceso de un camión."""
        P = self.var_P.get()
        Q = self.var_Q.get()
        R = self.var_R.get()
        S = self.var_S.get()
        
        resultado = self.motor_reglas.evaluar_camion(P, Q, R, S)
        
        # Mostrar resultado
        self.resultado_text.delete(1.0, tk.END)
        
        self.resultado_text.insert(tk.END, "RESULTADO DE EVALUACIÓN\n")
        self.resultado_text.insert(tk.END, "=" * 40 + "\n\n")
        
        self.resultado_text.insert(tk.END, f"Acceso Estándar: {'✅ PERMITIDO' if resultado['permite_acceso'] else '❌ DENEGADO'}\n")
        self.resultado_text.insert(tk.END, f"Inspección Especial: {'⚠️ REQUERIDA' if resultado['requiere_inspeccion'] else '✅ NO REQUERIDA'}\n\n")
        
        self.resultado_text.insert(tk.END, "EXPLICACIÓN:\n")
        for exp in resultado['explicaciones']:
            self.resultado_text.insert(tk.END, f"• {exp}\n")
        
        # Guardar en MongoDB
        self.db_manager.insertar("accesos", {
            "P": P, "Q": Q, "R": R, "S": S,
            "resultado": resultado,
            "timestamp": datetime.now().isoformat(),
            "operador": "sistema"
        })
    
    def actualizar_tabla_verdad(self):
        """Actualiza la tabla de verdad en tiempo real."""
        P = self.tv_P.get()
        Q = self.tv_Q.get()
        R = self.tv_R.get()
        S = self.tv_S.get()
        
        resultado = self.motor_reglas.evaluar_camion(P, Q, R, S)
        
        A = "V" if resultado['permite_acceso'] else "F"
        E = "V" if resultado['requiere_inspeccion'] else "F"
        
        color_A = self.success_color if resultado['permite_acceso'] else self.danger_color
        color_E = self.warning_color if resultado['requiere_inspeccion'] else self.success_color
        
        self.tabla_resultado.config(text=f"A: {A} | E: {E}")
    
    def clasificar_incidente(self):
        """Clasifica un incidente."""
        asunto = self.incidente_asunto.get()
        cuerpo = self.incidente_cuerpo.get(1.0, tk.END).strip()
        
        if not asunto or not cuerpo:
            messagebox.showwarning("Advertencia", "Por favor complete asunto y cuerpo.")
            return
        
        # Clasificar
        resultado = self.clasificador_hibrido.clasificar(asunto, cuerpo)
        
        # Mostrar resultado
        self.clasificacion_resultado.delete(1.0, tk.END)
        self.clasificacion_resultado.insert(tk.END, json.dumps(resultado, ensure_ascii=False, indent=2))
        
        # Guardar en MongoDB
        self.db_manager.insertar("incidentes", {
            "asunto": asunto,
            "cuerpo": cuerpo,
            "clasificacion": resultado,
            "estado": "nuevo",
            "timestamp": datetime.now().isoformat()
        })
    
    def enviar_pregunta_asistente(self):
        """Envía una pregunta al asistente LLM."""
        pregunta = self.chat_input.get().strip()
        
        if not pregunta:
            return
        
        self.chat_input.delete(0, tk.END)
        self.chat_area.insert(tk.END, f"\nTú: {pregunta}\n")
        
        # Consultar en hilo separado
        thread = threading.Thread(target=self._procesar_pregunta_asistente, args=(pregunta,))
        thread.daemon = True
        thread.start()
    
    def _procesar_pregunta_asistente(self, pregunta):
        """Procesa la pregunta del asistente en un hilo."""
        respuesta = self.asistente.consultar(pregunta)
        
        self.root.after(0, lambda: self._mostrar_respuesta_asistente(respuesta))
    
    def _mostrar_respuesta_asistente(self, respuesta):
        """Muestra la respuesta del asistente."""
        self.chat_area.insert(tk.END, f"\nAsistente: {respuesta['respuesta']}\n")
        if respuesta['fuentes']:
            self.chat_area.insert(tk.END, f"\nFuentes: {', '.join(respuesta['fuentes'])}\n")
        self.chat_area.see(tk.END)
    
    def exportar_json(self):
        """Exporta datos a JSON."""
        archivo = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if archivo:
            datos = {
                "accesos": self.db_manager.buscar("accesos"),
                "incidentes": self.db_manager.buscar("incidentes"),
                "riesgos": [asdict(r) for r in self.gestor_riesgos.riesgos]
            }
            with open(archivo, 'w', encoding='utf-8') as f:
                json.dump(datos, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("Éxito", "Datos exportados a JSON")
    
    def exportar_csv(self):
        """Exporta datos a CSV."""
        messagebox.showinfo("Info", "Exportación CSV no implementada en esta versión")
    
    def exportar_pdf(self):
        """Exporta datos a PDF."""
        messagebox.showinfo("Info", "Exportación PDF no implementada en esta versión")
    
    def cargar_datos_demo(self):
        """Carga datos de demostración."""
        # Datos de demostración para accesos
        demo_accesos = [
            {"P": True, "Q": False, "R": False, "S": True, "resultado": {"permite_acceso": True, "requiere_inspeccion": False}, "timestamp": datetime.now().isoformat(), "operador": "demo"},
            {"P": True, "Q": True, "R": False, "S": True, "resultado": {"permite_acceso": False, "requiere_inspeccion": True}, "timestamp": datetime.now().isoformat(), "operador": "demo"},
        ]
        
        for acceso in demo_accesos:
            self.db_manager.insertar("accesos", acceso)


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================

if __name__ == "__main__":
    root = tk.Tk()
    app = LogiSmartGUI(root)
    root.mainloop()
