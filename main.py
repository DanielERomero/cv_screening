import pdfplumber
import requests
import json
import os
from supabase import create_client, Client
from dotenv import load_dotenv
from openai import OpenAI
from prompts import (
    SYS_PROMPT_ESTRUCTURACION, SYS_PROMPT_EVALUACION,
    get_user_prompt_estructuracion, get_user_prompt_evaluacion
)
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

# Configuración de OpenAI (GitHub Models)
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

if not GITHUB_TOKEN:
    raise ValueError("Falta la variable GITHUB_TOKEN en el entorno o .env")

llm_client = OpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key=GITHUB_TOKEN,
)
# Utilizamos el mismo modelo que en app.py
MODELO_NUBE = "gpt-4o" 

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

def interactuar_con_gpt(prompt: str, rol_sistema: str) -> dict:
    """
    Fase de Percolación: Función genérica para hablar con GPT-4o vía GitHub (igual que en app.py).
    """
    try:
        response = llm_client.chat.completions.create(
            messages=[
                {"role": "system", "content": rol_sistema},
                {"role": "user", "content": prompt}
            ],
            model=MODELO_NUBE,
            temperature=0.1, # Temperatura baja para que sea analítico, no creativo
            response_format={"type": "json_object"} # Forzamos la salida a JSON puro
        )
        contenido = response.choices[0].message.content
        return json.loads(contenido)
    except Exception as e:
        print(f"[-] Error en la comunicación con OpenAI: {e}")
        return {}

def estructurar_cv(texto_crudo: str) -> dict:
    """
    Transforma el texto desordenado en un JSON estructurado usando OpenAI.
    """
    print(f"[*] Estructurando CV con OpenAI ({MODELO_NUBE})...")
    
    prompt = get_user_prompt_estructuracion(texto_crudo)
    resultado = interactuar_con_gpt(prompt, SYS_PROMPT_ESTRUCTURACION)
    
    # Validación básica de campos requeridos
    if not resultado or "nombre_completo" not in resultado:
        print("[-] Faltan campos requeridos en la respuesta de OpenAI.")
        return {
            "nombre_completo": "Desconocido",
            "email": "",
            "experiencia_laboral": [],
            "habilidades_tecnicas": []
        }
    return resultado

def evaluar_candidato(cv_json: dict, job_spec: str) -> dict:
    """
    El núcleo de la IA: Compara el CV estructurado con los requerimientos del puesto.
    Aquí garantizamos la transparencia (el "porqué").
    """
    print(f"[*] Evaluando candidato frente al Job Spec con OpenAI ({MODELO_NUBE})...")
    
    prompt = get_user_prompt_evaluacion(json.dumps(cv_json), job_spec)
    resultado = interactuar_con_gpt(prompt, SYS_PROMPT_EVALUACION)
    
    # Validación básica de campos requeridos
    if not resultado or "nivel" not in resultado:
        print("[-] Faltan campos requeridos en la evaluación de OpenAI.")
        return {
            "score": 0,
            "nivel": "Error",
            "justificacion": "No se pudo obtener una evaluación válida."
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
    
    # 4. Guardar en Supabase (Simulando 2 tablas o un JSONB)
    try:
        # Unificamos los textos generados por tu prompt para insertarlo en tu esquema original "razonamiento"
        texto_razonamiento = (
            f"**Justificación:** {evaluacion.get('justificacion', '')}\n\n"
            f"**Motivos de contratación:** {evaluacion.get('motivos_contratacion', '')}\n\n"
            f"**Habilidades Faltantes:** {evaluacion.get('habilidades_faltantes', '')}"
        )
        data_insercion = {
            "nombre_candidato": cv_estructurado.get("nombre_completo", "Sin Nombre"),
            "datos_cv": cv_estructurado,
            "score": evaluacion.get("score", 0),
            "decision": evaluacion.get("nivel", "Error"),
            "razonamiento": texto_razonamiento
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