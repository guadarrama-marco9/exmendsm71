
import itertools
import json
import logging
import os
import re
import smtplib
import sys
import threading
import time
import unittest
from dataclasses import dataclass, field, asdict
from datetime import datetime
from email.message import EmailMessage
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

# Bibliotecas externas
try:
    import pymongo
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    print("ADVERTENCIA: pymongo no instalado. MongoDB funcionará en modo simulación.")

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    print("ADVERTENCIA: ollama no instalado. Las funciones LLM no estarán disponibles.")

try:
    import pydantic
    from pydantic import BaseModel, Field, validator
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    print("ADVERTENCIA: pydantic no instalado. La validación JSON será básica.")

# Tkinter para GUI
try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext, messagebox, filedialog
    from tkinter import simpledialog
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False
    print("ADVERTENCIA: tkinter no disponible. La GUI no se podrá ejecutar.")

# Configuración de logging
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("logismart")


# =============================================================================
# SECCIÓN 1: MONGODB MANAGER
# =============================================================================
class MongoDBManager:
    """Gestiona la conexión y operaciones con MongoDB. Patrón Singleton."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, uri: str = "mongodb://localhost:27017/", 
                 database_name: str = "logismart"):
        if hasattr(self, '_initialized'):
            return
        
        self.uri = uri
        self.database_name = database_name
        self.client = None
        self.db = None
        self.simulation_mode = False
        self._simulated_collections = {
            "camiones": [],
            "accesos": [],
            "incidentes": [],
            "riesgos_eticos": [],
            "evaluaciones_llm": []
        }
        self._initialized = True
        self._conectar()
    
    def _conectar(self) -> bool:
        if not MONGODB_AVAILABLE:
            log.warning("pymongo no disponible, activando modo simulación")
            self.simulation_mode = True
            return False
        
        try:
            self.client = MongoClient(self.uri, serverSelectionTimeoutMS=5000)
            self.client.admin.command('ping')
            self.db = self.client[self.database_name]
            log.info(f"Conectado a MongoDB: {self.database_name}")
            self.simulation_mode = False
            return True
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            log.warning(f"No se pudo conectar a MongoDB: {e}. Activando modo simulación.")
            self.simulation_mode = True
            self.client = None
            self.db = None
            return False
    
    def esta_conectado(self) -> bool:
        return not self.simulation_mode and self.client is not None
    
    def insertar(self, coleccion: str, documento: Dict[str, Any]) -> str:
        if self.simulation_mode:
            documento["_id"] = f"sim_{len(self._simulated_collections[coleccion])}_{int(time.time())}"
            documento["timestamp"] = datetime.now().isoformat()
            self._simulated_collections[coleccion].append(documento)
            log.info(f"[SIMULACIÓN] Insertado en {coleccion}: {documento['_id']}")
            return documento["_id"]
        else:
            if coleccion not in self.db.list_collection_names():
                self.db.create_collection(coleccion)
            resultado = self.db[coleccion].insert_one(documento)
            log.info(f"Insertado en {coleccion}: {resultado.inserted_id}")
            return str(resultado.inserted_id)
    
    def buscar(self, coleccion: str, filtro: Optional[Dict[str, Any]] = None,
               limite: Optional[int] = None) -> List[Dict[str, Any]]:
        if self.simulation_mode:
            resultados = self._simulated_collections[coleccion]
            if filtro:
                resultados = [doc for doc in resultados if self._coincide_filtro(doc, filtro)]
            if limite:
                resultados = resultados[:limite]
            log.info(f"[SIMULACIÓN] Buscados {len(resultados)} documentos en {coleccion}")
            return resultados
        else:
            cursor = self.db[coleccion].find(filtro or {})
            if limite:
                cursor = cursor.limit(limite)
            resultados = list(cursor)
            log.info(f"Buscados {len(resultados)} documentos en {coleccion}")
            return resultados
    
    def actualizar(self, coleccion: str, filtro: Dict[str, Any],
                   actualizacion: Dict[str, Any]) -> int:
        if self.simulation_mode:
            count = 0
            for doc in self._simulated_collections[coleccion]:
                if self._coincide_filtro(doc, filtro):
                    doc.update(actualizacion["$set"] if "$set" in actualizacion else actualizacion)
                    count += 1
            log.info(f"[SIMULACIÓN] Actualizados {count} documentos en {coleccion}")
            return count
        else:
            resultado = self.db[coleccion].update_many(filtro, actualizacion)
            log.info(f"Actualizados {resultado.modified_count} documentos en {coleccion}")
            return resultado.modified_count
    
    def eliminar(self, coleccion: str, filtro: Dict[str, Any]) -> int:
        if self.simulation_mode:
            original_len = len(self._simulated_collections[coleccion])
            self._simulated_collections[coleccion] = [
                doc for doc in self._simulated_collections[coleccion]
                if not self._coincide_filtro(doc, filtro)
            ]
            count = original_len - len(self._simulated_collections[coleccion])
            log.info(f"[SIMULACIÓN] Eliminados {count} documentos en {coleccion}")
            return count
        else:
            resultado = self.db[coleccion].delete_many(filtro)
            log.info(f"Eliminados {resultado.deleted_count} documentos en {coleccion}")
            return resultado.deleted_count
    
    def agregar(self, coleccion: str, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if self.simulation_mode:
            log.warning("[SIMULACIÓN] Agregaciones no soportadas en modo simulación")
            return []
        else:
            resultados = list(self.db[coleccion].aggregate(pipeline))
            log.info(f"Agregación ejecutada en {coleccion}: {len(resultados)} resultados")
            return resultados
    
    def contar(self, coleccion: str, filtro: Optional[Dict[str, Any]] = None) -> int:
        if self.simulation_mode:
            resultados = self._simulated_collections[coleccion]
            if filtro:
                resultados = [doc for doc in resultados if self._coincide_filtro(doc, filtro)]
            return len(resultados)
        else:
            return self.db[coleccion].count_documents(filtro or {})
    
    def _coincide_filtro(self, documento: Dict[str, Any], filtro: Dict[str, Any]) -> bool:
        for key, valor in filtro.items():
            if key not in documento:
                return False
            if isinstance(valor, dict):
                if "$eq" in valor and documento[key] != valor["$eq"]:
                    return False
                elif "$gt" in valor and documento[key] <= valor["$gt"]:
                    return False
                elif "$lt" in valor and documento[key] >= valor["$lt"]:
                    return False
            elif documento[key] != valor:
                return False
        return True
    
    def limpiar_simulacion(self):
        for coleccion in self._simulated_collections:
            self._simulated_collections[coleccion] = []
        log.info("Datos de simulación limpiados")
    
    def cerrar(self):
        if self.client:
            self.client.close()
            log.info("Conexión con MongoDB cerrada")


# =============================================================================
# SECCIÓN 2: MOTOR DE REGLAS LÓGICAS
# =============================================================================
class MotorReglas:
    """Motor de reglas lógicas proposicionales para LogiSmart."""
    
    def __init__(self):
        self.historial_evaluaciones = []
    
    def evaluar_camion(self, P: bool, Q: bool, R: bool, S: bool, 
                       V: bool = True, H: bool = False) -> Dict[str, Any]:
        for nombre, valor in (("P", P), ("Q", Q), ("R", R), ("S", S), ("V", V), ("H", H)):
            if not isinstance(valor, bool):
                raise TypeError(f"La premisa {nombre} debe ser bool, se recibió {type(valor).__name__}")
        
        explicaciones = []
        
        acceso_estandar = P and S and (not Q)
        if acceso_estandar:
            explicaciones.append("Autorización previa AND conductor certificado AND SIN exceso de peso: ACTIVO")
        else:
            if not P:
                explicaciones.append("Sin autorización previa: acceso estándar BLOQUEADO")
            if not S:
                explicaciones.append("Conductor sin certificación: acceso estándar BLOQUEADO")
            if Q:
                explicaciones.append("Exceso de peso: acceso estándar BLOQUEADO")
        
        inspeccion_especial = P and (R or Q)
        if inspeccion_especial:
            explicaciones.append("Autorizado y (carga peligrosa O exceso de peso): inspección especial ACTIVA")
        
        certificacion_vigente = S and V
        if certificacion_vigente:
            explicaciones.append("Conductor certificado y certificación vigente: VÁLIDA")
        elif not S:
            explicaciones.append("Conductor sin certificación: NO VÁLIDA")
        elif not V:
            explicaciones.append("Certificación expirada: NO VÁLIDA")
        
        horario_restringido_activo = R and H
        if horario_restringido_activo:
            explicaciones.append("Carga peligrosa en horario restringido: RESTRICCIÓN ACTIVA")
        
        resultado = {
            "acceso_estandar": acceso_estandar,
            "inspeccion_especial": inspeccion_especial,
            "certificacion_vigente": certificacion_vigente,
            "horario_restringido_activo": horario_restringido_activo,
            "explicaciones": explicaciones
        }
        
        self.historial_evaluaciones.append({
            "P": P, "Q": Q, "R": R, "S": S, "V": V, "H": H,
            "resultado": resultado,
            "timestamp": datetime.now().isoformat()
        })
        
        return resultado
    
    def generar_tabla_verdad(self) -> List[Dict[str, Any]]:
        filas = []
        for P, Q, R, S in itertools.product([True, False], repeat=4):
            resultado = self.evaluar_camion(P, Q, R, S)
            filas.append({
                "P": P, "Q": Q, "R": R, "S": S,
                "no_Q": not Q,
                "P_y_S": P and S,
                "R_o_Q": R or Q,
                "A": resultado["acceso_estandar"],
                "E": resultado["inspeccion_especial"],
                "C": resultado["certificacion_vigente"]
            })
        return filas
    
    def imprimir_tablas_verdad(self) -> None:
        v = lambda b: "V" if b else "F"
        tabla = self.generar_tabla_verdad()
        
        print("=" * 78)
        print("SECCIÓN 2 - TABLAS DE VERDAD")
        print("=" * 78)
        
        print("\nTabla 1: A = P ∧ S ∧ ¬Q")
        print(f"{'P':^3}{'Q':^3}{'S':^3} | {'¬Q':^4}{'P∧S':^6}{'A':^4}")
        print("-" * 28)
        vistos = set()
        for f in tabla:
            clave = (f["P"], f["Q"], f["S"])
            if clave in vistos:
                continue
            vistos.add(clave)
            print(f"{v(f['P']):^3}{v(f['Q']):^3}{v(f['S']):^3} | "
                  f"{v(f['no_Q']):^4}{v(f['P_y_S']):^6}{v(f['A']):^4}")
        
        print("\nTabla 2: E = P ∧ (R ∨ Q)")
        print(f"{'P':^3}{'Q':^3}{'R':^3} | {'R∨Q':^5}{'E':^4}")
        print("-" * 24)
        vistos = set()
        for f in tabla:
            clave = (f["P"], f["Q"], f["R"])
            if clave in vistos:
                continue
            vistos.add(clave)
            print(f"{v(f['P']):^3}{v(f['Q']):^3}{v(f['R']):^3} | "
                  f"{v(f['R_o_Q']):^5}{v(f['E']):^4}")
        
        print("\nTabla 3: tabla completa (16 combinaciones) con A, E y C")
        print(f"{'P':^3}{'Q':^3}{'R':^3}{'S':^3} | {'¬Q':^4}{'P∧S':^6}{'R∨Q':^6} | {'A':^3}{'E':^3}{'C':^3}")
        print("-" * 48)
        for f in tabla:
            print(f"{v(f['P']):^3}{v(f['Q']):^3}{v(f['R']):^3}{v(f['S']):^3} | "
                  f"{v(f['no_Q']):^4}{v(f['P_y_S']):^6}{v(f['R_o_Q']):^6} | "
                  f"{v(f['A']):^3}{v(f['E']):^3}{v(f['C']):^3}")
        
        n_A = sum(f["A"] for f in tabla)
        n_E = sum(f["E"] for f in tabla)
        n_C = sum(f["C"] for f in tabla)
        n_ambas = sum(f["A"] and f["E"] for f in tabla)
        print(f"\nA es verdadera en {n_A}/16 combinaciones; E en {n_E}/16; C en {n_C}/16.")
        print(f"Ambas A y E verdaderas simultáneamente en {n_ambas}/16 casos.")
        print("Observaciones: sin P (autorización previa) tanto A como E son siempre F;")
        print("si Q es V, A es siempre F (el exceso de peso bloquea el acceso estándar).\n")


# =============================================================================
# SECCIÓN 3: CLASIFICADOR HÍBRIDO (REGLAS + LLM)
# =============================================================================
class Prioridad(Enum):
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"
    CRITICA = "critica"
    
    @classmethod
    def from_string(cls, valor: str) -> 'Prioridad':
        mapa = {"baja": cls.BAJA, "media": cls.MEDIA, "alta": cls.ALTA, "critica": cls.CRITICA}
        return mapa.get(valor.lower(), cls.BAJA)
    
    def valor(self) -> int:
        return {self.BAJA: 1, self.MEDIA: 2, self.ALTA: 3, self.CRITICA: 4}[self]


class ClasificadorHibrido:
    """Clasificador híbrido que combina reglas y LLM."""
    
    CATEGORIAS: Dict[str, List[str]] = {
        "materiales_peligrosos": ["peligroso", "derrame", "fuga", "quimico", "inflamable", "toxico", "corrosivo"],
        "sobrepeso": ["sobrepeso", "excede", "bascula", "exceso de peso", "sobrecarga"],
        "acceso_no_autorizado": ["sin autorizacion", "no autorizado", "acceso denegado", "barrera", "intruso"],
        "falla_hardware": ["camara", "sensor", "lector", "rfid", "no enciende", "apagado", "danado", "falla electrica"],
        "falla_software": ["sistema", "error", "pantalla", "caido", "no carga", "lento", "software", "aplicacion"],
        "somnolencia_conductor": ["somnolencia", "dormido", "cansancio", "fatiga", "sueno"],
    }
    
    PALABRAS_URGENTES = ["urgente", "emergencia", "accidente", "incendio", "herido", "critico", "inmediato"]
    
    PRIORIDAD_BASE: Dict[str, str] = {
        "materiales_peligrosos": "critica",
        "somnolencia_conductor": "alta",
        "acceso_no_autorizado": "alta",
        "sobrepeso": "media",
        "falla_hardware": "media",
        "falla_software": "baja",
        "otro": "baja",
    }
    
    ORDEN_PRIORIDAD = ["baja", "media", "alta", "critica"]
    
    PROMPT_SISTEMA = """
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

IMPORTANTE: Devuelve SOLO el JSON, sin texto adicional.
"""
    
    MODELO_LLM = "llama3.2"
    
    def __init__(self, usar_llm: bool = True):
        self.usar_llm = usar_llm and OLLAMA_AVAILABLE
        self.historial_clasificaciones = []
    
    def _normalizar(self, texto: str) -> str:
        tabla = str.maketrans("áéíóúüñ", "aeiouun")
        return texto.lower().translate(tabla)
    
    def clasificar_por_reglas(self, asunto: str, cuerpo: str) -> Dict[str, Any]:
        texto = self._normalizar(f"{asunto} {cuerpo}")
        
        puntajes: Dict[str, List[str]] = {
            cat: [kw for kw in kws if kw in texto] for cat, kws in self.CATEGORIAS.items()
        }
        
        mejor_cat = max(puntajes, key=lambda c: len(puntajes[c]))
        if not puntajes[mejor_cat]:
            mejor_cat = "otro"
            coincidencias: List[str] = []
        else:
            coincidencias = puntajes[mejor_cat]
        
        prioridad = self.PRIORIDAD_BASE[mejor_cat]
        urgentes = [p for p in self.PALABRAS_URGENTES if p in texto]
        if urgentes:
            idx = min(self.ORDEN_PRIORIDAD.index(prioridad) + 1, len(self.ORDEN_PRIORIDAD) - 1)
            prioridad = self.ORDEN_PRIORIDAD[idx]
        
        return {
            "categoria": mejor_cat,
            "prioridad": prioridad,
            "palabras_clave": coincidencias + urgentes,
            "metodo": "reglas"
        }
    
    def clasificar_por_llm(self, asunto: str, cuerpo: str) -> Optional[Dict[str, Any]]:
        if not self.usar_llm:
            return None
        
        try:
            prompt = f"Asunto: {asunto}\nCuerpo: {cuerpo}"
            
            respuesta = ollama.chat(
                model=self.MODELO_LLM,
                messages=[
                    {"role": "system", "content": self.PROMPT_SISTEMA},
                    {"role": "user", "content": prompt}
                ]
            )
            
            contenido = respuesta["message"]["content"].strip()
            
            json_match = re.search(r'\{.*\}', contenido, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                resultado = json.loads(json_str)
                resultado["metodo"] = "llm"
                return resultado
            else:
                log.warning("LLM no devolvió JSON válido")
                return None
                
        except Exception as e:
            log.error(f"Error en clasificación LLM: {e}")
            return None
    
    def extraer_datos(self, asunto: str, cuerpo: str) -> Dict[str, Optional[Any]]:
        texto = f"{asunto}\n{cuerpo}"
        
        m_placa = re.search(r"\b[A-Z0-9]{2,3}-\d{2,3}-[A-Z0-9]{1,2}\b", texto.upper())
        m_camion = re.search(r"\bCAM-\d+\b", texto.upper())
        
        m_peso = re.search(r"(\d+(?:[.,]\d+)?)\s*(toneladas|tonelada|ton|t|kg)\b", texto.lower())
        peso_kg: Optional[float] = None
        if m_peso:
            valor = float(m_peso.group(1).replace(",", "."))
            peso_kg = valor if m_peso.group(2) == "kg" else valor * 1000
        
        m_ubic = re.search(r"\b(and[eé]n|puerta|muelle|caseta|dock)\s+([A-Za-z0-9]+)", texto, re.IGNORECASE)
        
        return {
            "placa": m_placa.group(0) if m_placa else None,
            "camion_id": m_camion.group(0) if m_camion else None,
            "peso_reportado_kg": peso_kg,
            "ubicacion": f"{m_ubic.group(1)} {m_ubic.group(2)}".lower() if m_ubic else None,
        }
    
    def clasificar(self, asunto: str, cuerpo: str) -> Dict[str, Any]:
        clasificacion_reglas = self.clasificar_por_reglas(asunto, cuerpo)
        clasificacion_llm = self.clasificar_por_llm(asunto, cuerpo)
        
        if clasificacion_llm is None:
            resultado = clasificacion_reglas
            resultado["requiere_revision_humana"] = False
            resultado["discrepancia"] = None
        else:
            prioridad_reglas = Prioridad.from_string(clasificacion_reglas["prioridad"])
            prioridad_llm = Prioridad.from_string(clasificacion_llm["prioridad"])
            
            if prioridad_llm.valor() >= prioridad_reglas.valor():
                resultado = clasificacion_llm
            else:
                resultado = clasificacion_reglas
            
            discrepancia = (
                clasificacion_reglas["categoria"] != clasificacion_llm["categoria"] or
                clasificacion_reglas["prioridad"] != clasificacion_llm["prioridad"]
            )
            resultado["requiere_revision_humana"] = discrepancia
            resultado["discrepancia"] = {
                "reglas": clasificacion_reglas,
                "llm": clasificacion_llm
            } if discrepancia else None
        
        datos_extraidos = self.extraer_datos(asunto, cuerpo)
        
        resultado_final = {
            "categoria": resultado["categoria"],
            "prioridad": resultado["prioridad"],
            "palabras_clave": resultado.get("palabras_clave", []),
            "metodo": resultado["metodo"],
            "requiere_revision_humana": resultado["requiere_revision_humana"],
            "discrepancia": resultado["discrepancia"],
            "datos_extraidos": datos_extraidos
        }
        
        self.historial_clasificaciones.append({
            "asunto": asunto,
            "resultado": resultado_final,
            "timestamp": datetime.now().isoformat()
        })
        
        return resultado_final
    
    def enviar_correo_soporte(self, remitente: str, destinatario: str, 
                              asunto: str, cuerpo: str,
                              simulacion: bool = True) -> Dict[str, Any]:
        msg = EmailMessage()
        msg["From"] = remitente
        msg["To"] = destinatario
        msg["Subject"] = asunto
        msg.set_content(cuerpo)
        
        if simulacion:
            log.info("Envío SIMULADO de correo a %s (asunto: %s)", destinatario, asunto)
            return {"enviado": True, "modo": "simulacion", "error": None}
        
        try:
            host = os.environ["SMTP_HOST"]
            puerto = int(os.environ.get("SMTP_PORT", "587"))
            usuario = os.environ["SMTP_USER"]
            clave = os.environ["SMTP_PASSWORD"]
            with smtplib.SMTP(host, puerto, timeout=15) as servidor:
                servidor.starttls()
                servidor.login(usuario, clave)
                servidor.send_message(msg)
            log.info("Correo enviado a %s", destinatario)
            return {"enviado": True, "modo": "smtp", "error": None}
        except (KeyError, OSError, smtplib.SMTPException) as exc:
            log.error("No se pudo enviar el correo: %s", exc)
            return {"enviado": False, "modo": "smtp", "error": f"{type(exc).__name__}: {exc}"}
    
    def procesar_incidente(self, remitente: str, asunto: str, cuerpo: str,
                          destinatario_soporte: str = "soporte@logismart.example",
                          simulacion: bool = True) -> str:
        clasificacion = self.clasificar(asunto, cuerpo)
        datos = clasificacion["datos_extraidos"]
        
        asunto_soporte = f"[{clasificacion['prioridad'].upper()}] {clasificacion['categoria']} - {asunto}"
        cuerpo_soporte = (
            f"Incidente reportado por: {remitente}\n"
            f"Categoría: {clasificacion['categoria']}\n"
            f"Prioridad: {clasificacion['prioridad']}\n"
            f"Método: {clasificacion['metodo']}\n"
            f"Requiere revisión humana: {clasificacion['requiere_revision_humana']}\n"
            f"Datos extraídos: {json.dumps(datos, ensure_ascii=False)}\n\n"
            f"Mensaje original:\n{cuerpo}"
        )
        
        envio = self.enviar_correo_soporte(remitente, destinatario_soporte, 
                                          asunto_soporte, cuerpo_soporte, 
                                          simulacion=simulacion)
        
        resultado = {
            "fecha_procesamiento": datetime.now().isoformat(timespec="seconds"),
            "remitente": remitente,
            "asunto_original": asunto,
            "clasificacion": {
                "categoria": clasificacion["categoria"],
                "prioridad": clasificacion["prioridad"],
                "palabras_clave": clasificacion["palabras_clave"],
                "metodo": clasificacion["metodo"],
                "requiere_revision_humana": clasificacion["requiere_revision_humana"],
                "discrepancia": clasificacion["discrepancia"]
            },
            "datos_extraidos": datos,
            "correo_soporte": {"destinatario": destinatario_soporte, **envio}
        }
        
        salida = json.dumps(resultado, ensure_ascii=False, indent=2)
        json.loads(salida)
        return salida


# =============================================================================
# SECCIÓN 4: ASISTENTE EXPLICATIVO (RAG)
# =============================================================================
class AsistenteExplicativo:
    """Asistente explicativo que usa RAG (Retrieval-Augmented Generation)."""
    
    PROMPT_SISTEMA = """
Eres un asistente que explica decisiones del sistema LogiSmart.
Responde SOLO con la información proporcionada en el contexto.
Si no tienes información, responde "No tengo información sobre eso en los registros."
No inventes datos ni hagas suposiciones.
Sé conciso y claro.
"""
    
    MODELO_LLM = "llama3.2"
    
    def __init__(self, mongodb_manager: MongoDBManager):
        self.mongodb = mongodb_manager
        self.historial_consultas = []
    
    def _extraer_entidades(self, pregunta: str) -> Dict[str, Optional[str]]:
        placa = None
        camion_id = None
        
        m_placa = re.search(r"\b[A-Z0-9]{2,3}-\d{2,3}-[A-Z0-9]{1,2}\b", pregunta.upper())
        if m_placa:
            placa = m_placa.group(0)
        
        m_camion = re.search(r"\bCAM-\d+\b", pregunta.upper())
        if m_camion:
            camion_id = m_camion.group(0)
        
        return {"placa": placa, "camion_id": camion_id}
    
    def _recuperar_contexto(self, entidades: Dict[str, Optional[str]]) -> str:
        contexto = []
        
        if entidades["placa"]:
            camiones = self.mongodb.buscar("camiones", {"placa": entidades["placa"]})
            if camiones:
                contexto.append(f"Camión encontrado: {json.dumps(camiones[0], ensure_ascii=False)}")
        
        if entidades["camion_id"]:
            camiones = self.mongodb.buscar("camiones", {"camion_id": entidades["camion_id"]})
            if camiones:
                contexto.append(f"Camión encontrado: {json.dumps(camiones[0], ensure_ascii=False)}")
        
        if entidades["placa"] or entidades["camion_id"]:
            filtro = {}
            if entidades["placa"]:
                filtro["placa"] = entidades["placa"]
            if entidades["camion_id"]:
                filtro["camion_id"] = entidades["camion_id"]
            accesos = self.mongodb.buscar("accesos", filtro, limite=5)
            if accesos:
                contexto.append(f"Accesos recientes: {json.dumps(accesos, ensure_ascii=False)}")
        
        if entidades["placa"] or entidades["camion_id"]:
            incidentes = self.mongodb.buscar("incidentes", filtro, limite=5)
            if incidentes:
                contexto.append(f"Incidentes: {json.dumps(incidentes, ensure_ascii=False)}")
        
        return "\n\n".join(contexto) if contexto else "No se encontró información en los registros."
    
    def explicar(self, pregunta: str) -> str:
        if not OLLAMA_AVAILABLE:
            return "Lo siento, Ollama no está disponible. No puedo generar explicaciones."
        
        entidades = self._extraer_entidades(pregunta)
        contexto = self._recuperar_contexto(entidades)
        
        try:
            prompt = f"Contexto:\n{contexto}\n\nPregunta: {pregunta}"
            
            respuesta = ollama.chat(
                model=self.MODELO_LLM,
                messages=[
                    {"role": "system", "content": self.PROMPT_SISTEMA},
                    {"role": "user", "content": prompt}
                ]
            )
            
            contenido = respuesta["message"]["content"]
            
            self.historial_consultas.append({
                "pregunta": pregunta,
                "entidades": entidades,
                "contexto": contexto,
                "respuesta": contenido,
                "timestamp": datetime.now().isoformat()
            })
            
            return contenido
            
        except Exception as e:
            log.error(f"Error en asistente explicativo: {e}")
            return f"Error al generar explicación: {e}"


# =============================================================================
# SECCIÓN 5: GESTOR DE RIESGOS ÉTICOS
# =============================================================================
class NivelRiesgo(Enum):
    BAJO = "bajo"
    MEDIO = "medio"
    ALTO = "alto"
    CRITICO = "critico"
    
    @classmethod
    def from_puntaje(cls, puntaje: int) -> 'NivelRiesgo':
        if puntaje >= 17:
            return cls.CRITICO
        elif puntaje >= 10:
            return cls.ALTO
        elif puntaje >= 5:
            return cls.MEDIO
        else:
            return cls.BAJO


@dataclass
class RiesgoEtico:
    """Un riesgo ético asociado a un módulo del sistema."""
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
        return NivelRiesgo.from_puntaje(self.puntaje).value
    
    @property
    def puntaje_residual(self) -> int:
        """Calcula el puntaje residual después de la mitigación."""
        if self.mitigacion:
            # Asumimos que la mitigación reduce la probabilidad en 1 nivel (mínimo 1)
            probabilidad_residual = max(1, self.probabilidad - 1)
            return probabilidad_residual * self.impacto
        return self.puntaje
    
    @property
    def nivel_residual(self) -> str:
        return NivelRiesgo.from_puntaje(self.puntaje_residual).value


@dataclass
class ModuloIA:
    """Módulo del sistema que se evalúa."""
    nombre: str
    descripcion: str = ""
    riesgos: List[RiesgoEtico] = field(default_factory=list)


class GestorRiesgos:
    """Gestor de matriz de riesgos éticos."""
    
    CATEGORIAS_VALIDAS = {"sesgo", "privacidad", "transparencia", "seguridad", "responsabilidad", "otro"}
    
    def __init__(self, nombre_sistema: str):
        self.nombre_sistema = nombre_sistema
        self._modulos: Dict[str, ModuloIA] = {}
    
    def registrar_modulo(self, nombre: str, descripcion: str = "") -> ModuloIA:
        if not nombre or not nombre.strip():
            raise ValueError("El nombre del módulo no puede estar vacío")
        if nombre in self._modulos:
            raise ValueError(f"El módulo '{nombre}' ya está registrado")
        modulo = ModuloIA(nombre=nombre.strip(), descripcion=descripcion)
        self._modulos[nombre] = modulo
        return modulo
    
    def registrar_riesgo(self, modulo: str, descripcion: str, categoria: str,
                         probabilidad: int, impacto: int, mitigacion: str = "") -> RiesgoEtico:
        if modulo not in self._modulos:
            raise KeyError(f"El módulo '{modulo}' no existe; regístralo primero")
        if categoria not in self.CATEGORIAS_VALIDAS:
            raise ValueError(f"Categoría inválida '{categoria}'. Usa una de {sorted(self.CATEGORIAS_VALIDAS)}")
        for nombre, valor in (("probabilidad", probabilidad), ("impacto", impacto)):
            if not isinstance(valor, int) or isinstance(valor, bool) or not 1 <= valor <= 5:
                raise ValueError(f"{nombre} debe ser un entero entre 1 y 5")
        riesgo = RiesgoEtico(descripcion, categoria, probabilidad, impacto, mitigacion)
        self._modulos[modulo].riesgos.append(riesgo)
        return riesgo
    
    def todos_los_riesgos(self) -> List[Tuple[str, RiesgoEtico]]:
        plano = [(m.nombre, r) for m in self._modulos.values() for r in m.riesgos]
        return sorted(plano, key=lambda par: par[1].puntaje, reverse=True)
    
    def resumen(self) -> Dict[str, Any]:
        riesgos = self.todos_los_riesgos()
        por_nivel = {"critico": 0, "alto": 0, "medio": 0, "bajo": 0}
        por_categoria: Dict[str, int] = {}
        for _, r in riesgos:
            por_nivel[r.nivel] += 1
            por_categoria[r.categoria] = por_categoria.get(r.categoria, 0) + 1
        puntajes = [r.puntaje for _, r in riesgos]
        return {
            "sistema": self.nombre_sistema,
            "total_modulos": len(self._modulos),
            "total_riesgos": len(riesgos),
            "riesgos_por_nivel": por_nivel,
            "riesgos_por_categoria": por_categoria,
            "puntaje_promedio": round(sum(puntajes) / len(puntajes), 2) if puntajes else 0,
            "modulos_sin_evaluar": [m.nombre for m in self._modulos.values() if not m.riesgos],
        }
    
    def reporte_texto(self) -> str:
        r = self.resumen()
        L = []
        L.append("=" * 78)
        L.append(f"REPORTE DE RIESGOS ÉTICOS DE IA - {r['sistema']}")
        L.append(f"Generado: {datetime.now():%Y-%m-%d %H:%M}")
        L.append("=" * 78)
        L.append(f"Módulos: {r['total_modulos']} | Riesgos: {r['total_riesgos']} | "
                 f"Puntaje promedio: {r['puntaje_promedio']}")
        L.append("Por nivel: " + ", ".join(f"{k}={v}" for k, v in r["riesgos_por_nivel"].items()))
        L.append("Por categoría: " + (", ".join(f"{k}={v}" for k, v in r["riesgos_por_categoria"].items()) or "-"))
        if r["modulos_sin_evaluar"]:
            L.append("ATENCIÓN - Módulos sin riesgos evaluados: " + ", ".join(r["modulos_sin_evaluar"]))
        L.append("\nMATRIZ (ordenada de mayor a menor riesgo):")
        L.append(f"{'Módulo':<32}{'Riesgo':<34}{'P':>2}{'I':>3}{'Pts':>5}{'Res':>5}  Nivel")
        L.append("-" * 78)
        for modulo, riesgo in self.todos_los_riesgos():
            L.append(f"{modulo[:31]:<32}{riesgo.descripcion[:33]:<34}"
                     f"{riesgo.probabilidad:>2}{riesgo.impacto:>3}{riesgo.puntaje:>5}{riesgo.puntaje_residual:>5}  {riesgo.nivel}")
        L.append("\nMITIGACIONES PROPUESTAS:")
        for modulo, riesgo in self.todos_los_riesgos():
            if riesgo.mitigacion:
                L.append(f"  - [{riesgo.nivel.upper()}] {modulo}: {riesgo.mitigacion}")
        return "\n".join(L)
    
    def exportar_json(self, ruta: Optional[str] = None) -> str:
        datos = {
            "resumen": self.resumen(),
            "modulos": [
                {"nombre": m.nombre, "descripcion": m.descripcion,
                 "riesgos": [{**asdict(r), "puntaje": r.puntaje, "nivel": r.nivel,
                             "puntaje_residual": r.puntaje_residual, "nivel_residual": r.nivel_residual}
                            for r in m.riesgos]}
                for m in self._modulos.values()
            ],
        }
        texto = json.dumps(datos, ensure_ascii=False, indent=2)
        if ruta:
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(texto)
        return texto
    
    def exportar_texto(self, ruta: str) -> None:
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(self.reporte_texto())


# =============================================================================
# SECCIÓN 6: GUI COMPLETA CON 7 MÓDULOS
# =============================================================================
class LogiSmartGUI:
    """Interfaz gráfica completa con 7 módulos."""
    
    def __init__(self, root):
        if not TKINTER_AVAILABLE:
            raise RuntimeError("Tkinter no está disponible. No se puede ejecutar la GUI.")
        
        self.root = root
        self.root.title("LogiSmart - Sistema de Control Inteligente")
        self.root.geometry("1200x800")
        
        # Inicializar componentes
        self.mongodb = MongoDBManager()
        self.motor_reglas = MotorReglas()
        self.clasificador = ClasificadorHibrido(usar_llm=True)
        self.asistente = AsistenteExplicativo(self.mongodb)
        self.gestor_riesgos = GestorRiesgos("LogiSmart GUI")
        
        # Configurar estilos
        self.configurar_estilos()
        
        # Crear interfaz
        self.crear_interfaz()
        
        # Cargar datos de ejemplo
        self.cargar_datos_ejemplo()
    
    def configurar_estilos(self):
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Colores modernos con sombras
        bg_color = '#ecf0f1'
        header_bg = '#3498db'
        header_fg = '#ffffff'
        accent_color = '#2980b9'
        text_color = '#2c3e50'
        success_color = '#27ae60'
        warning_color = '#f39c12'
        danger_color = '#e74c3c'
        shadow_color = '#bdc3c7'
        
        self.root.configure(bg=bg_color)
        
        self.style.configure('TFrame', background=bg_color)
        self.style.configure('TLabel', background=bg_color, font=('Segoe UI', 10), foreground=text_color)
        self.style.configure('TButton', font=('Segoe UI', 10, 'bold'), background=accent_color, foreground='white', 
                            relief='raised', borderwidth=2)
        self.style.map('TButton', background=[('active', '#1f6391'), ('pressed', '#1a5276')])
        self.style.configure('Header.TLabel', font=('Segoe UI', 14, 'bold'), background=header_bg, foreground=header_fg, 
                            relief='raised', borderwidth=3)
        self.style.configure('Info.TLabel', font=('Segoe UI', 9), background=bg_color, foreground='#7f8c8d')
        self.style.configure('Module.TLabel', font=('Segoe UI', 11, 'bold'), background=accent_color, foreground='white',
                            relief='raised', borderwidth=2)
        self.style.configure('TLabelframe', background=bg_color, foreground=text_color, relief='raised', borderwidth=2)
        self.style.configure('TLabelframe.Label', background=bg_color, foreground=text_color, font=('Segoe UI', 10, 'bold'))
        self.style.configure('TNotebook', background=bg_color, relief='raised', borderwidth=2)
        self.style.configure('TNotebook.Tab', background='#bdc3c7', foreground=text_color, padding=[12, 8], relief='raised')
        self.style.map('TNotebook.Tab', background=[('selected', header_bg)], foreground=[('selected', 'white')])
        
        self.style.configure('TScrolledtext', background='white', relief='raised', borderwidth=2)
    
    def crear_interfaz(self):
        self.status_var = tk.StringVar(value="Sistema listo")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.crear_panel_control()
        self.crear_modulo_acceso()
        self.crear_modulo_incidentes()
        self.crear_modulo_asistente()
        self.crear_modulo_riesgos()
        self.crear_modulo_reportes()
        self.crear_modulo_config()
    
    def crear_panel_control(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Panel de Control")
        
        header = tk.Frame(frame, bg='#3498db', height=80)
        header.pack(fill=tk.X, padx=10, pady=10)
        header.pack_propagate(False)
        
        tk.Label(header, text="PANEL DE CONTROL", bg='#3498db', fg='white',
                font=('Segoe UI', 18, 'bold')).pack(pady=(15, 5))
        tk.Label(header, text="Sistema de Control Inteligente LogiSmart", bg='#3498db', fg='#ecf0f1',
                font=('Segoe UI', 10)).pack(pady=(0, 15))
        
        info_frame = ttk.LabelFrame(frame, text="Estado del Sistema", padding=15)
        info_frame.pack(fill=tk.X, padx=15, pady=10)
        
        mongo_status = "Conectado" if self.mongodb.esta_conectado() else "Modo Simulación"
        ollama_status = "Disponible" if OLLAMA_AVAILABLE else "No disponible"
        
        status_container = tk.Frame(info_frame, bg='#ecf0f1')
        status_container.pack(fill=tk.X, pady=5)
        
        tk.Label(status_container, text="MongoDB:", bg='#ecf0f1', font=('Segoe UI', 10, 'bold')).grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        tk.Label(status_container, text=mongo_status, bg='#ecf0f1', font=('Segoe UI', 10)).grid(row=0, column=1, sticky=tk.W, padx=10, pady=5)
        
        tk.Label(status_container, text="Ollama:", bg='#ecf0f1', font=('Segoe UI', 10, 'bold')).grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        tk.Label(status_container, text=ollama_status, bg='#ecf0f1', font=('Segoe UI', 10)).grid(row=1, column=1, sticky=tk.W, padx=10, pady=5)
        
        tk.Label(status_container, text="Modelo:", bg='#ecf0f1', font=('Segoe UI', 10, 'bold')).grid(row=2, column=0, sticky=tk.W, padx=10, pady=5)
        tk.Label(status_container, text="llama3.2", bg='#ecf0f1', font=('Segoe UI', 10)).grid(row=2, column=1, sticky=tk.W, padx=10, pady=5)
        
        stats_frame = ttk.LabelFrame(frame, text="Estadísticas en Tiempo Real", padding=15)
        stats_frame.pack(fill=tk.X, padx=15, pady=10)
        
        stats_container = tk.Frame(stats_frame, bg='#ecf0f1')
        stats_container.pack(fill=tk.X, pady=5)
        
        self.stats_labels = {}
        stats_info = [
            ("camiones", "Camiones", "#3498db"),
            ("accesos", "Accesos", "#27ae60"),
            ("incidentes", "Incidentes", "#e74c3c"),
            ("riesgos", "Riesgos", "#f39c12")
        ]
        
        for i, (key, label, color) in enumerate(stats_info):
            card = tk.Frame(stats_container, bg=color, relief='raised', borderwidth=2)
            card.grid(row=i//2, column=i%2, padx=10, pady=10, sticky='nsew')
            
            tk.Label(card, text=label, bg=color, fg='white', font=('Segoe UI', 12, 'bold')).pack(pady=(10, 5))
            self.stats_labels[key] = tk.Label(card, text="0", bg=color, fg='white', font=('Segoe UI', 24, 'bold'))
            self.stats_labels[key].pack(pady=(0, 10))
        
        stats_container.columnconfigure(0, weight=1)
        stats_container.columnconfigure(1, weight=1)
        
        btn_frame = tk.Frame(stats_frame, bg='#ecf0f1')
        btn_frame.pack(fill=tk.X, pady=15)
        
        ttk.Button(btn_frame, text="Actualizar Estadísticas", command=self.actualizar_estadisticas).pack(pady=5)
        
        self.actualizar_estadisticas()
    
    def crear_modulo_acceso(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Acceso")
        
        header = tk.Frame(frame, bg='#2980b9', height=70)
        header.pack(fill=tk.X, padx=10, pady=10)
        header.pack_propagate(False)
        
        tk.Label(header, text="MÓDULO DE ACCESO", bg='#2980b9', fg='white',
                font=('Segoe UI', 16, 'bold')).pack(pady=(15, 5))
        tk.Label(header, text="Evaluación de Camiones con Motor de Reglas", bg='#2980b9', fg='#ecf0f1',
                font=('Segoe UI', 10)).pack(pady=(0, 15))
        
        form_frame = ttk.LabelFrame(frame, text="Evaluar Camión", padding=20)
        form_frame.pack(fill=tk.X, padx=15, pady=10)
        
        self.acceso_vars = {
            "P": tk.BooleanVar(value=True),
            "Q": tk.BooleanVar(value=False),
            "R": tk.BooleanVar(value=False),
            "S": tk.BooleanVar(value=True),
            "V": tk.BooleanVar(value=True),
            "H": tk.BooleanVar(value=False)
        }
        
        labels = [("P", "Autorización previa"), ("Q", "Exceso de peso"), ("R", "Materiales peligrosos"),
                  ("S", "Conductor certificado"), ("V", "Certificación vigente"), ("H", "Horario restringido")]
        
        checkbox_container = tk.Frame(form_frame, bg='#ecf0f1')
        checkbox_container.pack(fill=tk.X, pady=10)
        
        for i, (key, label) in enumerate(labels):
            chk_frame = tk.Frame(checkbox_container, bg='#ecf0f1')
            chk_frame.grid(row=i//2, column=i%2, sticky=tk.W, padx=15, pady=8)
            
            tk.Checkbutton(chk_frame, text=label, variable=self.acceso_vars[key],
                         bg='#ecf0f1', font=('Segoe UI', 10), activebackground='#ecf0f1',
                         selectcolor='#3498db').pack(anchor=tk.W)
        
        btn_frame = tk.Frame(form_frame, bg='#ecf0f1')
        btn_frame.pack(fill=tk.X, pady=15)
        
        ttk.Button(btn_frame, text="Evaluar Camión", command=self.evaluar_acceso).pack(pady=5)
        
        result_frame = ttk.LabelFrame(frame, text="Resultados de Evaluación", padding=20)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        
        self.acceso_resultado = scrolledtext.ScrolledText(result_frame, height=12, font=('Consolas', 10),
                                                          bg='white', relief='raised', borderwidth=2)
        self.acceso_resultado.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    def crear_modulo_incidentes(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Incidentes")
        
        header = tk.Frame(frame, bg='#e74c3c', height=70)
        header.pack(fill=tk.X, padx=10, pady=10)
        header.pack_propagate(False)
        
        tk.Label(header, text="MÓDULO DE INCIDENTES", bg='#e74c3c', fg='white',
                font=('Segoe UI', 16, 'bold')).pack(pady=(15, 5))
        tk.Label(header, text="Clasificación Híbrida (Reglas + LLM)", bg='#e74c3c', fg='#ecf0f1',
                font=('Segoe UI', 10)).pack(pady=(0, 15))
        
        form_frame = ttk.LabelFrame(frame, text="Reportar Incidente", padding=20)
        form_frame.pack(fill=tk.X, padx=15, pady=10)
        
        input_container = tk.Frame(form_frame, bg='#ecf0f1')
        input_container.pack(fill=tk.X, pady=10)
        
        tk.Label(input_container, text="Remitente:", bg='#ecf0f1', font=('Segoe UI', 10, 'bold')).grid(row=0, column=0, sticky=tk.W, padx=10, pady=8)
        self.incidente_remitente = ttk.Entry(input_container, width=50, font=('Segoe UI', 10))
        self.incidente_remitente.grid(row=0, column=1, sticky=tk.W, padx=10, pady=8)
        
        tk.Label(input_container, text="Asunto:", bg='#ecf0f1', font=('Segoe UI', 10, 'bold')).grid(row=1, column=0, sticky=tk.W, padx=10, pady=8)
        self.incidente_asunto = ttk.Entry(input_container, width=50, font=('Segoe UI', 10))
        self.incidente_asunto.grid(row=1, column=1, sticky=tk.W, padx=10, pady=8)
        
        tk.Label(input_container, text="Cuerpo:", bg='#ecf0f1', font=('Segoe UI', 10, 'bold')).grid(row=2, column=0, sticky=tk.NW, padx=10, pady=8)
        self.incidente_cuerpo = scrolledtext.ScrolledText(input_container, height=6, width=50, font=('Segoe UI', 10),
                                                         bg='white', relief='raised', borderwidth=2)
        self.incidente_cuerpo.grid(row=2, column=1, sticky=tk.W, padx=10, pady=8)
        
        btn_frame = tk.Frame(form_frame, bg='#ecf0f1')
        btn_frame.pack(fill=tk.X, pady=15)
        
        ttk.Button(btn_frame, text="Clasificar Incidente", command=self.clasificar_incidente).pack(pady=5)
        
        result_frame = ttk.LabelFrame(frame, text="Resultado JSON", padding=20)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        
        self.incidente_resultado = scrolledtext.ScrolledText(result_frame, height=15, font=('Consolas', 9),
                                                            bg='white', relief='raised', borderwidth=2)
        self.incidente_resultado.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    def crear_modulo_asistente(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Asistente")
        
        header = tk.Frame(frame, bg='#9b59b6', height=70)
        header.pack(fill=tk.X, padx=10, pady=10)
        header.pack_propagate(False)
        
        tk.Label(header, text="ASISTENTE EXPLICATIVO", bg='#9b59b6', fg='white',
                font=('Segoe UI', 16, 'bold')).pack(pady=(15, 5))
        tk.Label(header, text="Retrieval-Augmented Generation (RAG)", bg='#9b59b6', fg='#ecf0f1',
                font=('Segoe UI', 10)).pack(pady=(0, 15))
        
        chat_frame = ttk.LabelFrame(frame, text="Conversación", padding=20)
        chat_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        
        self.asistente_chat = scrolledtext.ScrolledText(chat_frame, height=15, font=('Segoe UI', 10),
                                                        bg='white', relief='raised', borderwidth=2)
        self.asistente_chat.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.asistente_chat.tag_config('user', foreground='#2980b9', font=('Segoe UI', 10, 'bold'))
        self.asistente_chat.tag_config('assistant', foreground='#27ae60', font=('Segoe UI', 10))
        
        input_frame = ttk.LabelFrame(frame, text="Pregunta", padding=15)
        input_frame.pack(fill=tk.X, padx=15, pady=10)
        
        input_container = tk.Frame(input_frame, bg='#ecf0f1')
        input_container.pack(fill=tk.X, pady=5)
        
        tk.Label(input_container, text="Escribe tu pregunta:", bg='#ecf0f1', font=('Segoe UI', 10, 'bold')).pack(side=tk.LEFT, padx=10)
        self.asistente_pregunta = ttk.Entry(input_container, width=60, font=('Segoe UI', 10))
        self.asistente_pregunta.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        self.asistente_pregunta.bind('<Return>', lambda e: self.enviar_pregunta_asistente())
        
        ttk.Button(input_container, text="Enviar", command=self.enviar_pregunta_asistente).pack(side=tk.LEFT, padx=10)
        
        self.asistente_chat.insert(tk.END, "Sistema: Escribe una pregunta sobre un camión (ej: '¿Por qué se denegó el acceso al camión ABC-123-D?')\n\n", 'assistant')
    
    def crear_modulo_riesgos(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Riesgos")
        
        header = tk.Frame(frame, bg='#f39c12', height=70)
        header.pack(fill=tk.X, padx=10, pady=10)
        header.pack_propagate(False)
        
        tk.Label(header, text="MATRIZ DE RIESGOS ÉTICOS", bg='#f39c12', fg='white',
                font=('Segoe UI', 16, 'bold')).pack(pady=(15, 5))
        tk.Label(header, text="Gestión y Análisis de Riesgos de IA", bg='#f39c12', fg='#ecf0f1',
                font=('Segoe UI', 10)).pack(pady=(0, 15))
        
        form_frame = ttk.LabelFrame(frame, text="Registrar Riesgo", padding=20)
        form_frame.pack(fill=tk.X, padx=15, pady=10)
        
        input_container = tk.Frame(form_frame, bg='#ecf0f1')
        input_container.pack(fill=tk.X, pady=10)
        
        tk.Label(input_container, text="Módulo:", bg='#ecf0f1', font=('Segoe UI', 10, 'bold')).grid(row=0, column=0, sticky=tk.W, padx=10, pady=8)
        self.riesgo_modulo = ttk.Entry(input_container, width=30, font=('Segoe UI', 10))
        self.riesgo_modulo.grid(row=0, column=1, sticky=tk.W, padx=10, pady=8)
        
        tk.Label(input_container, text="Descripción:", bg='#ecf0f1', font=('Segoe UI', 10, 'bold')).grid(row=1, column=0, sticky=tk.W, padx=10, pady=8)
        self.riesgo_descripcion = ttk.Entry(input_container, width=30, font=('Segoe UI', 10))
        self.riesgo_descripcion.grid(row=1, column=1, sticky=tk.W, padx=10, pady=8)
        
        tk.Label(input_container, text="Categoría:", bg='#ecf0f1', font=('Segoe UI', 10, 'bold')).grid(row=2, column=0, sticky=tk.W, padx=10, pady=8)
        self.riesgo_categoria = ttk.Combobox(input_container, values=list(GestorRiesgos.CATEGORIAS_VALIDAS), width=27, font=('Segoe UI', 10))
        self.riesgo_categoria.grid(row=2, column=1, sticky=tk.W, padx=10, pady=8)
        
        tk.Label(input_container, text="Probabilidad (1-5):", bg='#ecf0f1', font=('Segoe UI', 10, 'bold')).grid(row=3, column=0, sticky=tk.W, padx=10, pady=8)
        self.riesgo_probabilidad = ttk.Spinbox(input_container, from_=1, to=5, width=10, font=('Segoe UI', 10))
        self.riesgo_probabilidad.grid(row=3, column=1, sticky=tk.W, padx=10, pady=8)
        
        tk.Label(input_container, text="Impacto (1-5):", bg='#ecf0f1', font=('Segoe UI', 10, 'bold')).grid(row=4, column=0, sticky=tk.W, padx=10, pady=8)
        self.riesgo_impacto = ttk.Spinbox(input_container, from_=1, to=5, width=10, font=('Segoe UI', 10))
        self.riesgo_impacto.grid(row=4, column=1, sticky=tk.W, padx=10, pady=8)
        
        tk.Label(input_container, text="Mitigación:", bg='#ecf0f1', font=('Segoe UI', 10, 'bold')).grid(row=5, column=0, sticky=tk.W, padx=10, pady=8)
        self.riesgo_mitigacion = ttk.Entry(input_container, width=30, font=('Segoe UI', 10))
        self.riesgo_mitigacion.grid(row=5, column=1, sticky=tk.W, padx=10, pady=8)
        
        btn_frame = tk.Frame(form_frame, bg='#ecf0f1')
        btn_frame.pack(fill=tk.X, pady=15)
        
        ttk.Button(btn_frame, text="Registrar Riesgo", command=self.registrar_riesgo).pack(pady=5)
        
        report_frame = ttk.LabelFrame(frame, text="Reporte de Riesgos", padding=20)
        report_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        
        self.riesgo_reporte = scrolledtext.ScrolledText(report_frame, height=15, font=('Consolas', 9),
                                                       bg='white', relief='raised', borderwidth=2)
        self.riesgo_reporte.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        ttk.Button(report_frame, text="Actualizar Reporte", command=self.actualizar_reporte_riesgos).pack(pady=10)
        
        self.cargar_riesgos_documento()
        self.actualizar_reporte_riesgos()
    
    def crear_modulo_reportes(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Reportes")
        
        header = tk.Frame(frame, bg='#1abc9c', height=70)
        header.pack(fill=tk.X, padx=10, pady=10)
        header.pack_propagate(False)
        
        tk.Label(header, text="REPORTES Y EXPORTACIÓN", bg='#1abc9c', fg='white',
                font=('Segoe UI', 16, 'bold')).pack(pady=(15, 5))
        tk.Label(header, text="Generación y Exportación de Datos", bg='#1abc9c', fg='#ecf0f1',
                font=('Segoe UI', 10)).pack(pady=(0, 15))
        
        export_frame = ttk.LabelFrame(frame, text="Exportar Datos", padding=20)
        export_frame.pack(fill=tk.X, padx=15, pady=10)
        
        btn_container = tk.Frame(export_frame, bg='#ecf0f1')
        btn_container.pack(fill=tk.X, pady=10)
        
        ttk.Button(btn_container, text="Exportar Tablas de Verdad", command=self.exportar_tablas_verdad).pack(fill=tk.X, pady=8, padx=10)
        ttk.Button(btn_container, text="Exportar Riesgos (JSON)", command=self.exportar_riesgos_json).pack(fill=tk.X, pady=8, padx=10)
        ttk.Button(btn_container, text="Exportar Riesgos (TXT)", command=self.exportar_riesgos_txt).pack(fill=tk.X, pady=8, padx=10)
        
        preview_frame = ttk.LabelFrame(frame, text="Vista Previa", padding=20)
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        
        self.reporte_preview = scrolledtext.ScrolledText(preview_frame, height=15, font=('Consolas', 9),
                                                        bg='white', relief='raised', borderwidth=2)
        self.reporte_preview.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    def crear_modulo_config(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="⚙️ Config")
        
        header = tk.Frame(frame, bg='#34495e', height=70)
        header.pack(fill=tk.X, padx=10, pady=10)
        header.pack_propagate(False)
        
        tk.Label(header, text="CONFIGURACIÓN DEL SISTEMA", bg='#34495e', fg='white',
                font=('Segoe UI', 16, 'bold')).pack(pady=(15, 5))
        tk.Label(header, text="Ajustes de MongoDB y LLM", bg='#34495e', fg='#ecf0f1',
                font=('Segoe UI', 10)).pack(pady=(0, 15))
        
        # Configuración MongoDB con mejor diseño
        mongo_frame = ttk.LabelFrame(frame, text="MongoDB", padding=20)
        mongo_frame.pack(fill=tk.X, padx=15, pady=10)
        
        mongo_container = tk.Frame(mongo_frame, bg='#ecf0f1')
        mongo_container.pack(fill=tk.X, pady=10)
        
        tk.Label(mongo_container, text="🔗 URI:", bg='#ecf0f1', font=('Segoe UI', 10, 'bold')).grid(row=0, column=0, sticky=tk.W, padx=10, pady=8)
        self.mongo_uri = ttk.Entry(mongo_container, width=50, font=('Segoe UI', 10))
        self.mongo_uri.insert(0, "mongodb://localhost:27017/")
        self.mongo_uri.grid(row=0, column=1, sticky=tk.W, padx=10, pady=8)
        
        tk.Label(mongo_container, text="🗄️ Base de datos:", bg='#ecf0f1', font=('Segoe UI', 10, 'bold')).grid(row=1, column=0, sticky=tk.W, padx=10, pady=8)
        self.mongo_db = ttk.Entry(mongo_container, width=50, font=('Segoe UI', 10))
        self.mongo_db.insert(0, "logismart")
        self.mongo_db.grid(row=1, column=1, sticky=tk.W, padx=10, pady=8)
        
        # Botón reconectar con mejor diseño
        btn_mongo = tk.Frame(mongo_frame, bg='#ecf0f1')
        btn_mongo.pack(fill=tk.X, pady=15)
        
        ttk.Button(btn_mongo, text="🔄 Reconectar MongoDB", command=self.reconectar_mongodb).pack(pady=5)
        
        # Configuración LLM con mejor diseño
        llm_frame = ttk.LabelFrame(frame, text="LLM (Ollama)", padding=20)
        llm_frame.pack(fill=tk.X, padx=15, pady=10)
        
        llm_container = tk.Frame(llm_frame, bg='#ecf0f1')
        llm_container.pack(fill=tk.X, pady=10)
        
        tk.Label(llm_container, text="🧠 Modelo:", bg='#ecf0f1', font=('Segoe UI', 10, 'bold')).grid(row=0, column=0, sticky=tk.W, padx=10, pady=8)
        self.llm_modelo = ttk.Entry(llm_container, width=50, font=('Segoe UI', 10))
        self.llm_modelo.insert(0, "llama3.2")
        self.llm_modelo.grid(row=0, column=1, sticky=tk.W, padx=10, pady=8)
        
        self.llm_usar = tk.BooleanVar(value=True)
        tk.Checkbutton(llm_container, text="✅ Usar LLM para clasificación", variable=self.llm_usar,
                      bg='#ecf0f1', font=('Segoe UI', 10), activebackground='#ecf0f1',
                      selectcolor='#3498db').grid(row=1, column=0, columnspan=2, sticky=tk.W, padx=10, pady=8)
        
        # Botón aplicar con mejor diseño
        btn_llm = tk.Frame(llm_frame, bg='#ecf0f1')
        btn_llm.pack(fill=tk.X, pady=15)
        
        ttk.Button(btn_llm, text="💾 Aplicar Configuración", command=self.aplicar_config_llm).pack(pady=5)
    
    def cargar_datos_ejemplo(self):
        """Carga datos de ejemplo en MongoDB (modo simulación)."""
        # Camión de ejemplo
        self.mongodb.insertar("camiones", {
            "placa": "ABC-123-D",
            "camion_id": "CAM-102",
            "empresa": "Transportes S.A.",
            "autorizacion": True,
            "certificacion_conductor": True,
            "fecha_registro": datetime.now().isoformat()
        })
        
        # Acceso de ejemplo
        self.mongodb.insertar("accesos", {
            "P": True, "Q": False, "R": False, "S": True,
            "resultado": {
                "acceso_estandar": True,
                "inspeccion_especial": False,
                "certificacion_vigente": True,
                "horario_restringido_activo": False
            },
            "explicaciones": ["Autorización previa AND conductor certificado AND SIN exceso de peso: ACTIVO"],
            "timestamp": datetime.now().isoformat(),
            "operador": "juan.perez"
        })
    
    def cargar_riesgos_documento(self):
        """Carga los riesgos del documento INFORME_TECNICO.md."""
        riesgos_documento = [
            ("Clasificador Híbrido", "Alucinaciones del LLM en clasificación", "seguridad", 3, 4, "Validación JSON + fallback a reglas"),
            ("Clasificador Híbrido", "Sesgo en correos informales", "sesgo", 4, 3, "Normalización de texto"),
            ("Cámara de Somnolencia", "Privacidad de datos conductor", "privacidad", 4, 5, "Procesamiento en borde"),
            ("Sistema", "Dependencia excesiva de automatización", "responsabilidad", 3, 4, "Revisión humana en críticos"),
            ("Cámara de Somnolencia", "Falsos positivos somnolencia", "sesgo", 3, 3, "Umbral ajustable"),
            ("MongoDB", "Fuga de datos MongoDB", "privacidad", 2, 5, "Cifrado de datos"),
        ]
        
        for modulo, desc, cat, prob, imp, mitig in riesgos_documento:
            try:
                if modulo not in self.gestor_riesgos._modulos:
                    self.gestor_riesgos.registrar_modulo(modulo)
                self.gestor_riesgos.registrar_riesgo(modulo, desc, cat, prob, imp, mitig)
            except:
                pass
    
    def actualizar_estadisticas(self):
        self.stats_labels["camiones"].config(text=str(self.mongodb.contar("camiones")))
        self.stats_labels["accesos"].config(text=str(self.mongodb.contar("accesos")))
        self.stats_labels["incidentes"].config(text=str(self.mongodb.contar("incidentes")))
        self.stats_labels["riesgos"].config(text=str(len(self.gestor_riesgos.todos_los_riesgos())))
        self.status_var.set("Estadísticas actualizadas")
    
    def evaluar_acceso(self):
        P = self.acceso_vars["P"].get()
        Q = self.acceso_vars["Q"].get()
        R = self.acceso_vars["R"].get()
        S = self.acceso_vars["S"].get()
        V = self.acceso_vars["V"].get()
        H = self.acceso_vars["H"].get()
        
        resultado = self.motor_reglas.evaluar_camion(P, Q, R, S, V, H)
        
        self.acceso_resultado.delete(1.0, tk.END)
        self.acceso_resultado.insert(tk.END, json.dumps(resultado, ensure_ascii=False, indent=2))
        
        # Guardar en MongoDB
        self.mongodb.insertar("accesos", {
            "P": P, "Q": Q, "R": R, "S": S,
            "resultado": resultado,
            "timestamp": datetime.now().isoformat(),
            "operador": "gui_user"
        })
        
        self.status_var.set("Evaluación de acceso completada")
        self.actualizar_estadisticas()
    
    def clasificar_incidente(self):
        remitente = self.incidente_remitente.get()
        asunto = self.incidente_asunto.get()
        cuerpo = self.incidente_cuerpo.get(1.0, tk.END)
        
        resultado = self.clasificador.procesar_incidente(remitente, asunto, cuerpo, simulacion=True)
        
        self.incidente_resultado.delete(1.0, tk.END)
        self.incidente_resultado.insert(tk.END, resultado)
        
        # Guardar en MongoDB
        datos = json.loads(resultado)
        self.mongodb.insertar("incidentes", datos)
        
        self.status_var.set("Incidente clasificado")
        self.actualizar_estadisticas()
    
    def enviar_pregunta_asistente(self):
        pregunta = self.asistente_pregunta.get().strip()
        if not pregunta:
            return
        
        self.asistente_pregunta.delete(0, tk.END)
        
        self.asistente_chat.insert(tk.END, f"Tú: {pregunta}\n\n", 'user')
        
        respuesta = self.asistente.explicar(pregunta)
        
        self.asistente_chat.insert(tk.END, f"Asistente: {respuesta}\n\n", 'assistant')
        self.asistente_chat.see(tk.END)
        
        self.status_var.set("Pregunta procesada")
    
    def registrar_riesgo(self):
        modulo = self.riesgo_modulo.get()
        descripcion = self.riesgo_descripcion.get()
        categoria = self.riesgo_categoria.get()
        probabilidad = int(self.riesgo_probabilidad.get())
        impacto = int(self.riesgo_impacto.get())
        mitigacion = self.riesgo_mitigacion.get()
        
        try:
            if modulo not in self.gestor_riesgos._modulos:
                self.gestor_riesgos.registrar_modulo(modulo)
            self.gestor_riesgos.registrar_riesgo(modulo, descripcion, categoria, probabilidad, impacto, mitigacion)
            self.actualizar_reporte_riesgos()
            self.status_var.set("Riesgo registrado")
            self.actualizar_estadisticas()
        except Exception as e:
            messagebox.showerror("Error", str(e))
    
    def actualizar_reporte_riesgos(self):
        reporte = self.gestor_riesgos.reporte_texto()
        self.riesgo_reporte.delete(1.0, tk.END)
        self.riesgo_reporte.insert(tk.END, reporte)
    
    def exportar_tablas_verdad(self):
        archivo = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")])
        if archivo:
            self.motor_reglas.imprimir_tablas_verdad()
            with open(archivo, "w", encoding="utf-8") as f:
                from io import StringIO
                import sys
                old_stdout = sys.stdout
                sys.stdout = StringIO()
                self.motor_reglas.imprimir_tablas_verdad()
                output = sys.stdout.getvalue()
                sys.stdout = old_stdout
                f.write(output)
            messagebox.showinfo("Exportación", "Tablas de verdad exportadas")
    
    def exportar_riesgos_json(self):
        archivo = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if archivo:
            self.gestor_riesgos.exportar_json(archivo)
            messagebox.showinfo("Exportación", "Riesgos exportados en JSON")
    
    def exportar_riesgos_txt(self):
        archivo = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")])
        if archivo:
            self.gestor_riesgos.exportar_texto(archivo)
            messagebox.showinfo("Exportación", "Riesgos exportados en TXT")
    
    def reconectar_mongodb(self):
        uri = self.mongo_uri.get()
        db = self.mongo_db.get()
        self.mongodb = MongoDBManager(uri, db)
        self.asistente.mongodb = self.mongodb
        self.mongodb.limpiar_simulacion()
        self.cargar_datos_ejemplo()
        self.actualizar_estadisticas()
        messagebox.showinfo("MongoDB", f"Estado: {'Conectado' if self.mongodb.esta_conectado() else 'Modo Simulación'}")
    
    def aplicar_config_llm(self):
        modelo = self.llm_modelo.get()
        usar = self.llm_usar.get()
        self.clasificador = ClasificadorHibrido(usar_llm=usar)
        self.clasificador.MODELO_LLM = modelo
        messagebox.showinfo("Configuración", "Configuración LLM aplicada")


# =============================================================================
# PRUEBAS UNITARIAS
# =============================================================================
class TestMotorReglas(unittest.TestCase):
    """Pruebas para el Motor de Reglas."""
    
    def setUp(self):
        self.motor = MotorReglas()
    
    def test_evaluar_camion_basico(self):
        resultado = self.motor.evaluar_camion(True, False, False, True)
        self.assertTrue(resultado["acceso_estandar"])
        self.assertFalse(resultado["inspeccion_especial"])
        self.assertTrue(resultado["certificacion_vigente"])
    
    def test_sin_autorizacion(self):
        resultado = self.motor.evaluar_camion(False, False, False, True)
        self.assertFalse(resultado["acceso_estandar"])
        self.assertFalse(resultado["inspeccion_especial"])
    
    def test_exceso_peso_bloquea_acceso(self):
        resultado = self.motor.evaluar_camion(True, True, False, True)
        self.assertFalse(resultado["acceso_estandar"])
        self.assertTrue(resultado["inspeccion_especial"])
    
    def test_tipo_invalido(self):
        with self.assertRaises(TypeError):
            self.motor.evaluar_camion(1, False, False, True)
    
    def test_tabla_verdad_16_filas(self):
        tabla = self.motor.generar_tabla_verdad()
        self.assertEqual(len(tabla), 16)


class TestClasificadorHibrido(unittest.TestCase):
    """Pruebas para el Clasificador Híbrido."""
    
    def setUp(self):
        self.clasificador = ClasificadorHibrido(usar_llm=False)  # Solo reglas para pruebas
    
    def test_clasificar_por_reglas(self):
        resultado = self.clasificador.clasificar_por_reglas(
            "URGENTE: derrame",
            "Hay fuga de químico inflamable en andén 3"
        )
        self.assertEqual(resultado["categoria"], "materiales_peligrosos")
        self.assertEqual(resultado["prioridad"], "critica")
    
    def test_extraer_datos(self):
        datos = self.clasificador.extraer_datos(
            "Incidente ABC-123-D",
            "Camión CAM-102 en andén 3, 48.5 toneladas"
        )
        self.assertEqual(datos["placa"], "ABC-123-D")
        self.assertEqual(datos["camion_id"], "CAM-102")
        self.assertEqual(datos["peso_reportado_kg"], 48500.0)
        self.assertEqual(datos["ubicacion"], "andén 3")
    
    def test_procesar_incidente_json_valido(self):
        salida = self.clasificador.procesar_incidente(
            "test@example.com",
            "Falla de cámara",
            "La cámara no enciende",
            simulacion=True
        )
        datos = json.loads(salida)
        self.assertIn("clasificacion", datos)
        self.assertIn("datos_extraidos", datos)


class TestGestorRiesgos(unittest.TestCase):
    """Pruebas para el Gestor de Riesgos."""
    
    def setUp(self):
        self.gestor = GestorRiesgos("Test Sistema")
    
    def test_registrar_modulo(self):
        modulo = self.gestor.registrar_modulo("Test Modulo", "Descripción")
        self.assertEqual(modulo.nombre, "Test Modulo")
    
    def test_registrar_riesgo(self):
        self.gestor.registrar_modulo("Test Modulo")
        riesgo = self.gestor.registrar_riesgo("Test Modulo", "Test riesgo", "seguridad", 3, 4)
        self.assertEqual(riesgo.puntaje, 12)
        self.assertEqual(riesgo.nivel, "alto")
    
    def test_validacion_probabilidad_impacto(self):
        self.gestor.registrar_modulo("Test Modulo")
        with self.assertRaises(ValueError):
            self.gestor.registrar_riesgo("Test Modulo", "Test", "seguridad", 6, 4)  # Probabilidad > 5
    
    def test_puntaje_residual(self):
        self.gestor.registrar_modulo("Test Modulo")
        riesgo = self.gestor.registrar_riesgo("Test Modulo", "Test", "seguridad", 4, 5, "Mitigación")
        self.assertLess(riesgo.puntaje_residual, riesgo.puntaje)
    
    def test_exportar_json_valido(self):
        self.gestor.registrar_modulo("Test Modulo")
        self.gestor.registrar_riesgo("Test Modulo", "Test", "seguridad", 3, 3)
        json_str = self.gestor.exportar_json()
        datos = json.loads(json_str)
        self.assertIn("resumen", datos)
        self.assertIn("modulos", datos)


# =============================================================================
# DEMOSTRACIÓN COMPLETA
# =============================================================================
def demo():
    """Ejecuta una demostración completa de todas las secciones."""
    print("=" * 78)
    print("LOGISMART PYTHON SUITE - DEMOSTRACIÓN COMPLETA")
    print("=" * 78)
    print()
    
    # Inicializar componentes
    mongodb = MongoDBManager()
    motor = MotorReglas()
    clasificador = ClasificadorHibrido(usar_llm=True)
    asistente = AsistenteExplicativo(mongodb)
    gestor = GestorRiesgos("LogiSmart Demo")
    
    # ---- Sección 1: MongoDB ----
    print("SECCIÓN 1: MONGODB MANAGER")
    print("-" * 78)
    print(f"Estado MongoDB: {'Conectado' if mongodb.esta_conectado() else 'Modo Simulación'}")
    print()
    
    # Insertar datos de ejemplo
    mongodb.insertar("camiones", {
        "placa": "ABC-123-D",
        "camion_id": "CAM-102",
        "empresa": "Transportes S.A.",
        "autorizacion": True,
        "certificacion_conductor": True
    })
    print("Camión de ejemplo insertado en MongoDB")
    print()
    
    # ---- Sección 2: Motor de Reglas ----
    print("SECCIÓN 2: MOTOR DE REGLAS")
    print("-" * 78)
    motor.imprimir_tablas_verdad()
    
    print("Ejemplos de evaluación:")
    casos = [
        ("Autorizado, certificado, peso OK", (True, False, False, True)),
        ("Autorizado, exceso de peso", (True, True, False, True)),
        ("Sin autorización", (False, False, False, True)),
    ]
    for desc, (P, Q, R, S) in casos:
        res = motor.evaluar_camion(P, Q, R, S)
        print(f"  {desc} => A={res['acceso_estandar']}, E={res['inspeccion_especial']}")
    print()
    
    # ---- Sección 3: Clasificador Híbrido ----
    print("SECCIÓN 3: CLASIFICADOR HÍBRIDO")
    print("-" * 78)
    salida_json = clasificador.procesar_incidente(
        remitente="operador@logismart.example",
        asunto="URGENTE: derrame en andén 3",
        cuerpo="El camión CAM-102 con placas ABC-123-D presenta fuga de químico inflamable.",
        simulacion=True
    )
    print(salida_json)
    print()
    
    # ---- Sección 4: Asistente Explicativo ----
    print("SECCIÓN 4: ASISTENTE EXPLICATIVO (RAG)")
    print("-" * 78)
    if OLLAMA_AVAILABLE:
        pregunta = "¿Por qué se denegó el acceso al camión ABC-123-D?"
        respuesta = asistente.explicar(pregunta)
        print(f"Pregunta: {pregunta}")
        print(f"Respuesta: {respuesta}")
    else:
        print("Ollama no disponible, asistente no ejecutado.")
    print()
    
    # ---- Sección 5: Gestor de Riesgos ----
    print("SECCIÓN 5: GESTOR DE RIESGOS ÉTICOS")
    print("-" * 78)
    
    # Cargar riesgos del documento
    riesgos_documento = [
        ("Clasificador", "Alucinaciones del LLM", "seguridad", 3, 4, "Validación JSON"),
        ("Cámara", "Privacidad conductor", "privacidad", 4, 5, "Procesamiento en borde"),
        ("Sistema", "Dependencia automatización", "responsabilidad", 3, 4, "Revisión humana"),
    ]
    
    for modulo, desc, cat, prob, imp, mitig in riesgos_documento:
        if modulo not in gestor._modulos:
            gestor.registrar_modulo(modulo)
        gestor.registrar_riesgo(modulo, desc, cat, prob, imp, mitig)
    
    print(gestor.reporte_texto())
    
    # Exportar
    gestor.exportar_json("reporte_riesgos_demo.json")
    gestor.exportar_texto("reporte_riesgos_demo.txt")
    print("\nArchivos generados: reporte_riesgos_demo.json y reporte_riesgos_demo.txt")
    print()
    
    print("=" * 78)
    print("DEMOSTRACIÓN COMPLETADA")
    print("=" * 78)


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================
if __name__ == "__main__":
    if "--tests" in sys.argv:
        # Ejecutar pruebas unitarias
        sys.argv.remove("--tests")
        unittest.main(argv=[sys.argv[0], "-v"])
    elif "--gui" in sys.argv:
        # Ejecutar GUI
        if TKINTER_AVAILABLE:
            root = tk.Tk()
            app = LogiSmartGUI(root)
            root.mainloop()
        else:
            print("ERROR: Tkinter no está disponible. No se puede ejecutar la GUI.")
    else:
        # Ejecutar demostración
        demo()
        
        # Ejecutar pruebas después de la demo
        print("\n" + "=" * 78)
        print("PRUEBAS UNITARIAS")
        print("=" * 78)
        suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
        unittest.TextTestRunner(verbosity=2).run(suite)
