import pdfplumber
import hashlib
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

def extraer_texto_pdf(ruta_pdf: str) -> tuple[str, int]:
    """
    Fase de Molienda: Extrae el texto crudo y el número de páginas del CV.
    """
    texto_extraido = ""
    num_paginas = 0
    try:
        with pdfplumber.open(ruta_pdf) as pdf:
            num_paginas = len(pdf.pages)
            for pagina in pdf.pages:
                texto = pagina.extract_text()
                if texto:
                    texto_extraido += texto + "\n"
        print(f"[+] Texto extraído exitosamente de {ruta_pdf}")
        return texto_extraido.strip(), num_paginas
    except Exception as e:
        print(f"[-] Error al extraer texto: {e}")
        return "", 0

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
    if not resultado or "nombre_candidato" not in resultado:
        print("[-] Faltan campos requeridos en la respuesta de OpenAI.")
        return {
            "nombre_candidato": "Desconocido",
            "email": "",
            "experiencia_detalle": [],
            "skills_tecnicos": []
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

def procesar_candidato(ruta_pdf: str, job_spec: str, proceso_nombre: str = "Sin nombre"):
    # 1. Extracción
    texto_cv, num_paginas = extraer_texto_pdf(ruta_pdf)
    if not texto_cv:
        return

    # 2. Estructuración
    cv_estructurado = estructurar_cv(texto_cv)
    print(f"[+] CV Estructurado: {cv_estructurado.get('nombre_candidato', 'Desconocido')}")

    # 3. Evaluación
    evaluacion = evaluar_candidato(cv_estructurado, job_spec)
    print(f"[+] Score obtenido: {evaluacion.get('score_total')} - {evaluacion.get('recomendacion')}")
    print(f"[+] Justificación: {evaluacion.get('justificacion_general')}")

    # 4. Guardar en Supabase — Arquitectura Medallion
    try:
        # Bronze — PDF crudo
        with open(ruta_pdf, "rb") as f:
            pdf_bytes = f.read()
        file_hash = hashlib.sha256(pdf_bytes).hexdigest()

        resp_bronze = supabase.schema("bronze").table("raw_cvs").insert({
            "proceso_nombre": proceso_nombre,
            "filename":       os.path.basename(ruta_pdf),
            "file_hash":      file_hash,
            "texto_crudo":    texto_cv,
            "num_paginas":    num_paginas,
            "tamanio_bytes":  len(pdf_bytes),
        }).execute()
        raw_cv_id = resp_bronze.data[0]["id"]

        # Silver — CV estructurado
        resp_silver = supabase.schema("silver").table("cv_estructurados").insert({
            "raw_cv_id":             raw_cv_id,
            "nombre_candidato":      cv_estructurado.get("nombre_candidato"),
            "email":                 cv_estructurado.get("email"),
            "telefono":              cv_estructurado.get("telefono"),
            "ubicacion":             cv_estructurado.get("ubicacion"),
            "resumen_perfil":        cv_estructurado.get("resumen_perfil"),
            "experiencia_anios":     cv_estructurado.get("experiencia_anios"),
            "ultimo_cargo":          cv_estructurado.get("ultimo_cargo"),
            "ultima_empresa":        cv_estructurado.get("ultima_empresa"),
            "educacion_nivel":       cv_estructurado.get("educacion_nivel"),
            "educacion_carrera":     cv_estructurado.get("educacion_carrera"),
            "educacion_institucion": cv_estructurado.get("educacion_institucion"),
            "skills_tecnicos":       cv_estructurado.get("skills_tecnicos", []),
            "idiomas":               cv_estructurado.get("idiomas", []),
            "experiencia_detalle":   cv_estructurado.get("experiencia_detalle", []),
            "educacion_detalle":     cv_estructurado.get("educacion_detalle", []),
        }).execute()
        cv_estructurado_id = resp_silver.data[0]["id"]

        # Gold — Evaluación
        supabase.schema("gold").table("evaluaciones").insert({
            "cv_estructurado_id":    cv_estructurado_id,
            "score_total":           evaluacion.get("score_total", 0),
            "recomendacion":         evaluacion.get("recomendacion", "descartar"),
            "justificacion_general": evaluacion.get("justificacion_general"),
            "fortalezas":            evaluacion.get("fortalezas", []),
            "brechas":               evaluacion.get("brechas", []),
        }).execute()

        print("[+] Datos guardados exitosamente en Supabase (Bronze → Silver → Gold).")

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
    procesar_candidato("cv_prueba.pdf", job_requerimientos, proceso_nombre="Data Scientist Q1 2026")