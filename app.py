import streamlit as st
import pdfplumber
import hashlib
import json
import os
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import OpenAI
from prompts import (
    SYS_PROMPT_ESTRUCTURACION, SYS_PROMPT_EVALUACION,
    get_user_prompt_estructuracion, get_user_prompt_evaluacion
)

# ==========================================
# 1. CONFIGURACIÓN E INICIALIZACIÓN
# ==========================================
st.set_page_config(page_title="AI Resume Screener", page_icon="🚀", layout="wide")

@st.cache_resource
def init_connections():
    """Inicializa Supabase y el cliente LLM (GitHub Models) a prueba de fallos."""
    try:
        # Intento 1: Streamlit Cloud Secrets
        supa_url = st.secrets["SUPABASE_URL"]
        supa_key = st.secrets["SUPABASE_KEY"]
        github_token = st.secrets["GITHUB_TOKEN"]
    except (FileNotFoundError, KeyError):
        # Intento 2: Entorno local (.env)
        load_dotenv()
        
        supa_url = os.environ.get("SUPABASE_URL")
        supa_key = os.environ.get("SUPABASE_KEY")
        github_token = os.environ.get("GITHUB_TOKEN")
    
    if not supa_url or not supa_key or not github_token:
        st.error("🚨 Faltan credenciales. Verifica Supabase URL/KEY y GITHUB_TOKEN.")
        st.stop()
        
    # Cliente Supabase
    db_client = create_client(supa_url, supa_key)
    
    # Cliente LLM (Usando la librería de OpenAI apuntando a GitHub Models)
    llm_client = OpenAI(
        base_url="https://models.inference.ai.azure.com",
        api_key=github_token,
    )
    
    return db_client, llm_client

supabase, llm = init_connections()
MODELO_NUBE = "gpt-4.1"

# ==========================================
# 2. FUNCIONES CORE (NLP & LLM)
# ==========================================
def extraer_texto_en_memoria(archivo_pdf) -> tuple[str, int]:
    """Extrae texto y número de páginas del PDF desde memoria RAM."""
    texto = ""
    num_paginas = 0
    try:
        with pdfplumber.open(archivo_pdf) as pdf:
            num_paginas = len(pdf.pages)
            for pagina in pdf.pages:
                extraido = pagina.extract_text()
                if extraido:
                    texto += extraido + "\n"
        return texto.strip(), num_paginas
    except Exception as e:
        st.error(f"Error al leer el PDF: {e}")
        return "", 0

def interactuar_con_gpt(prompt: str, rol_sistema: str) -> dict:
    """Habla con GPT-4o vía GitHub y garantiza un JSON estructurado."""
    try:
        response = llm.chat.completions.create(
            messages=[
                {"role": "system", "content": rol_sistema},
                {"role": "user", "content": prompt}
            ],
            model=MODELO_NUBE,
            temperature=0, # Temperatura baja para que sea analítico, no creativo
            response_format={"type": "json_object"} # Forzamos la salida a JSON puro
        )
        # Extraemos y parseamos el JSON de la respuesta
        contenido = response.choices[0].message.content
        return json.loads(contenido)
    except Exception as e:
        st.error(f"Error en la inferencia con GPT-4o: {e}")
        return {}

# ==========================================
# 3. INTERFAZ DE USUARIO (FRONTEND)
# ==========================================
st.title("☁️ Sistema de Selección Automatizada")
st.markdown("Sube un CV, define el Job Spec y deja que la IA evalúe la compatibilidad con explicabilidad total.")

proceso_nombre = st.text_input(
    "Nombre del proceso de selección",
    placeholder="Ej: Data Engineer Q1 2026"
)

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Requerimientos del Puesto (Job Spec)")
    job_spec = st.text_area(
        "Ingresa las habilidades y requisitos:",
        height=200,
        placeholder="Ej: Buscamos un Data Scientist con 3 años de experiencia en Python..."
    )

with col2:
    st.subheader("2. Currículum del Candidato")
    archivo_subido = st.file_uploader("Sube el CV (PDF)", type=["pdf"])

if st.button("Ejecutar Motor de Evaluación", type="primary", use_container_width=True):
    if not proceso_nombre or not job_spec or not archivo_subido:
        st.warning("⚠️ Completa el nombre del proceso, el Job Spec y sube un CV.")
    else:
        with st.spinner("⏳ Moliendo datos: Extrayendo texto..."):
            texto_cv, num_paginas = extraer_texto_en_memoria(archivo_subido)
            
        if texto_cv:
            with st.spinner("🧠 Percolación Semántica: Estructurando CV con GPT-4o..."):
                prompt_estructura = get_user_prompt_estructuracion(texto_cv)
                cv_json = interactuar_con_gpt(prompt_estructura, SYS_PROMPT_ESTRUCTURACION)
            
            with st.spinner("⚖️ Análisis Profundo: Evaluando compatibilidad..."):
                prompt_evaluacion = get_user_prompt_evaluacion(json.dumps(cv_json), job_spec)
                evaluacion = interactuar_con_gpt(prompt_evaluacion, SYS_PROMPT_EVALUACION)
            
            with st.spinner("💾 Guardando resultados en Supabase..."):
                # Bronze — PDF crudo
                archivo_subido.seek(0)
                pdf_bytes = archivo_subido.read()
                file_hash = hashlib.sha256(pdf_bytes).hexdigest()

                resp_bronze = supabase.schema("bronze").table("raw_cvs").insert({
                    "proceso_nombre": proceso_nombre,
                    "filename":       archivo_subido.name,
                    "file_hash":      file_hash,
                    "texto_crudo":    texto_cv,
                    "num_paginas":    num_paginas,
                    "tamanio_bytes":  len(pdf_bytes),
                }).execute()
                raw_cv_id = resp_bronze.data[0]["id"]

                # Silver — CV estructurado
                resp_silver = supabase.schema("silver").table("cv_estructurados").insert({
                    "raw_cv_id":             raw_cv_id,
                    "nombre_candidato":      cv_json.get("nombre_candidato"),
                    "email":                 cv_json.get("email"),
                    "telefono":              cv_json.get("telefono"),
                    "ubicacion":             cv_json.get("ubicacion"),
                    "resumen_perfil":        cv_json.get("resumen_perfil"),
                    "experiencia_anios":     cv_json.get("experiencia_anios"),
                    "ultimo_cargo":          cv_json.get("ultimo_cargo"),
                    "ultima_empresa":        cv_json.get("ultima_empresa"),
                    "educacion_nivel":       cv_json.get("educacion_nivel"),
                    "educacion_carrera":     cv_json.get("educacion_carrera"),
                    "educacion_institucion": cv_json.get("educacion_institucion"),
                    "skills_tecnicos":       cv_json.get("skills_tecnicos", []),
                    "idiomas":               cv_json.get("idiomas", []),
                    "experiencia_detalle":   cv_json.get("experiencia_detalle", []),
                    "educacion_detalle":     cv_json.get("educacion_detalle", []),
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

            # ==========================================
            # 4. RESULTADOS (XAI)
            # ==========================================
            st.success("✅ Análisis completado. Datos persistidos en la nube.")
            st.divider()

            nombre_candidato = cv_json.get("nombre_candidato", "Desconocido")
            st.subheader(f"Resultados para: {nombre_candidato}")
            m_col1, m_col2 = st.columns(2)

            score         = evaluacion.get("score_total", 0)
            recomendacion = evaluacion.get("recomendacion", "descartar")

            m_col1.metric("Score de Compatibilidad", f"{score}/100")

            if recomendacion in ["prioridad", "entrevistar"]:
                color = "green"
            elif recomendacion == "considerar":
                color = "orange"
            else:
                color = "red"

            m_col2.markdown(f"**Nivel (Decisión):** :{color}[{recomendacion.capitalize()}]")

            st.markdown("### Auditoría de Decisión (XAI)")

            fortalezas = evaluacion.get("fortalezas", [])
            brechas    = evaluacion.get("brechas", [])

            st.success("**🚀 Fortalezas:**\n\n" + "\n".join(f"• {f}" for f in fortalezas))
            st.warning("**⚠️ Brechas:**\n\n"    + "\n".join(f"• {b}" for b in brechas))
            st.info(f"**📊 Justificación del Score:**\n\n{evaluacion.get('justificacion_general', 'No especificada.')}")

            with st.expander("Ver JSON estructurado del CV"):
                st.json(cv_json)