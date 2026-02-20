import pdfplumber
import requests
import json
import os
from supabase import create_client, Client
from dotenv import load_dotenv
# ==========================================
# 1. CONFIGURACIÓN DEL ENTORNO
# ==========================================
# Credenciales de Supabase 
load_dotenv()  # Carga las variables de entorno desde el archivo .env
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Faltan las variables SUPABASE_URL o SUPABASE_KEY en el entorno o .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Configuración de Ollama
OLLAMA_API_URL = "http://localhost:11434/api/generate"
MODELO = "gpt-oss:120b-cloud" 

# ==========================================
# 2. FUNCIONES CORE
# ==========================================

def extraer_texto_pdf(ruta_pdf: str) -> str:
    """
    Fase de Molienda: Extrae el texto crudo del CV usando pdfplumber.
    """
    texto_extraido = ""
    try:
        with pdfplumber.open(ruta_pdf) as pdf:
            for pagina in pdf.pages:
                texto = pagina.extract_text()
                if texto:
                    texto_extraido += texto + "\n"
        print(f"[+] Texto extraído exitosamente de {ruta_pdf}")
        return texto_extraido.strip()
    except Exception as e:
        print(f"[-] Error al extraer texto: {e}")
        return ""

def interactuar_con_ollama(prompt: str, forzar_json: bool = True) -> dict:
    """
    Fase de Percolación: Función genérica para hablar con Ollama sin intermediarios (Langchain).
    """
    payload = {
        "model": MODELO,
        "prompt": prompt,
        "stream": False,
        "format": "json" if forzar_json else ""
    }
    
    try:
        response = requests.post(OLLAMA_API_URL, json=payload)
        response.raise_for_status()
        data = response.json()
        if 'response' not in data:
            print("[-] Respuesta inesperada de Ollama:", data)
            return {}
        try:
            return json.loads(data['response'])
        except Exception as e:
            print(f"[-] Error al parsear JSON de Ollama: {e}")
            return {}
    except Exception as e:
        print(f"[-] Error en la comunicación con Ollama: {e}")
        return {}

def estructurar_cv(texto_crudo: str) -> dict:
    """
    Transforma el texto desordenado en un JSON estructurado.
    """
    prompt = f"""
    Extrae la siguiente información del currículum proporcionado y devuélvela ESTRICTAMENTE en formato JSON.
    Campos requeridos: "nombre", "email", "habilidades" (lista), "experiencia_años" (entero).
    
    Currículum:
    {texto_crudo}
    """
    print("[*] Estructurando CV con Ollama...")
    resultado = interactuar_con_ollama(prompt)
    # Validación básica de campos requeridos
    if not resultado or not all(k in resultado for k in ["nombre", "email", "habilidades", "experiencia_años"]):
        print("[-] Faltan campos requeridos en la respuesta de Ollama.")
        return {
            "nombre": "Desconocido",
            "email": "",
            "habilidades": [],
            "experiencia_años": 0
        }
    return resultado

def evaluar_candidato(cv_json: dict, job_spec: str) -> dict:
    """
    El núcleo de la IA: Compara el CV estructurado con los requerimientos del puesto.
    Aquí garantizamos la transparencia (el "porqué").
    """
    prompt = f"""
    Eres un evaluador técnico imparcial. Compara el perfil del candidato con los requerimientos del puesto.
    Candidato (JSON): {json.dumps(cv_json)}
    Requerimientos del Puesto: {job_spec}
    
    Evalúa y responde ESTRICTAMENTE en formato JSON con la siguiente estructura:
    - "score": un número entero de 0 a 100 indicando la compatibilidad.
    - "decision": "Apto" o "No Apto" (Apto si el score es >= 75).
    - "razonamiento": Una explicación breve y técnica de por qué se asignó ese score, destacando qué hace match y qué falta. Evita cualquier sesgo discriminatorio.
    """
    print("[*] Evaluando candidato frente al Job Spec...")
    resultado = interactuar_con_ollama(prompt)
    # Validación básica de campos requeridos
    if not resultado or not all(k in resultado for k in ["score", "decision", "razonamiento"]):
        print("[-] Faltan campos requeridos en la evaluación de Ollama.")
        return {
            "score": 0,
            "decision": "Error",
            "razonamiento": "No se pudo obtener una evaluación válida."
        }
    return resultado

# ==========================================
# 3. PIPELINE PRINCIPAL (Tu script de ejecución)
# ==========================================

def procesar_candidato(ruta_pdf: str, job_spec: str):
    # 1. Extracción
    texto_cv = extraer_texto_pdf(ruta_pdf)
    if not texto_cv:
        return
    
    # 2. Estructuración
    cv_estructurado = estructurar_cv(texto_cv)
    print(f"[+] CV Estructurado: {cv_estructurado.get('nombre', 'Desconocido')}")
    
    # 3. Evaluación
    evaluacion = evaluar_candidato(cv_estructurado, job_spec)
    print(f"[+] Score obtenido: {evaluacion.get('score')} - {evaluacion.get('decision')}")
    print(f"[+] Razón: {evaluacion.get('razonamiento')}")
    
    # 4. Guardado en Supabase (Simulando 2 tablas o un JSONB)
    try:
        data_insercion = {
            "nombre_candidato": cv_estructurado.get("nombre", "Sin Nombre"),
            "datos_cv": cv_estructurado,
            "score": evaluacion.get("score", 0),
            "decision": evaluacion.get("decision", "Error"),
            "razonamiento": evaluacion.get("razonamiento", "Sin razón")
        }
        
        # Asumiendo que tienes una tabla llamada 'candidatos_evaluados'
        respuesta_db = supabase.table("candidatos_evaluados").insert(data_insercion).execute()
        if hasattr(respuesta_db, "status_code") and respuesta_db.status_code != 201:
            print(f"[-] Error al guardar en base de datos: {respuesta_db}")
        else:
            print("[+] Datos guardados exitosamente en Supabase.")
        
    except Exception as e:
        print(f"[-] Error al guardar en base de datos: {e}")

# ==========================================
# PRUEBA LOCAL
# ==========================================
if __name__ == "__main__":
    # Simulación de un requerimiento de trabajo
    job_requerimientos = """
    Buscamos un Data Scientist Junior/Semi-Senior.
    Experiencia: Al menos 2 años.
    Habilidades clave: Python, SQL, Machine Learning, NLP básico, control de versiones (Git).
    Deseable: Experiencia con bases de datos vectoriales.
    """
    
    # Ejecuta el pipeline (Asegúrate de tener un cv_prueba.pdf en la misma carpeta)
    procesar_candidato("cv_prueba.pdf", job_requerimientos)