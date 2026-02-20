import streamlit as st
import pdfplumber
import json
import os
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import OpenAI

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
def extraer_texto_en_memoria(archivo_pdf) -> str:
    """Extrae texto del PDF directo desde la memoria RAM."""
    texto = ""
    try:
        with pdfplumber.open(archivo_pdf) as pdf:
            for pagina in pdf.pages:
                extraido = pagina.extract_text()
                if extraido:
                    texto += extraido + "\n"
        return texto.strip()
    except Exception as e:
        st.error(f"Error al leer el PDF: {e}")
        return ""

def interactuar_con_gpt(prompt: str, rol_sistema: str) -> dict:
    """Habla con GPT-4o vía GitHub y garantiza un JSON estructurado."""
    try:
        response = llm.chat.completions.create(
            messages=[
                {"role": "system", "content": rol_sistema},
                {"role": "user", "content": prompt}
            ],
            model=MODELO_NUBE,
            temperature=0.1, # Temperatura baja para que sea analítico, no creativo
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
st.title("☁️ Sistema de Selección Automatizada (GPT-4o & Supabase)")
st.markdown("Sube un CV, define el Job Spec y deja que la IA evalúe la compatibilidad con explicabilidad total.")

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
    if not job_spec or not archivo_subido:
        st.warning("⚠️ Ingresa el Job Spec y sube un CV.")
    else:
        with st.spinner("⏳ Moliendo datos: Extrayendo texto..."):
            texto_cv = extraer_texto_en_memoria(archivo_subido)
            
        if texto_cv:
            with st.spinner("🧠 Percolación Semántica: Estructurando CV con GPT-4o..."):
                sys_prompt_estructura = "Eres un asistente experto en RRHH. Debes extraer información de currículums y responder ÚNICAMENTE en formato JSON con las claves: 'nombre', 'email', 'habilidades' (array), 'experiencia_años' (número)."
                prompt_estructura = f"Extrae los datos de este CV:\n{texto_cv}"
                
                cv_json = interactuar_con_gpt(prompt_estructura, sys_prompt_estructura)
            
            with st.spinner("⚖️ Análisis Profundo: Evaluando compatibilidad..."):
                sys_prompt_eval = "Eres un evaluador técnico imparcial. Responde ÚNICAMENTE en JSON con las claves: 'score' (0-100), 'decision' ('Apto' o 'No Apto'), y 'razonamiento' (explicación técnica y neutral para evitar sesgos, justificando qué hace match y qué falta)."
                prompt_evaluacion = f"Compara este candidato con los requerimientos.\nCandidato: {json.dumps(cv_json)}\nJob Spec: {job_spec}"
                
                evaluacion = interactuar_con_gpt(prompt_evaluacion, sys_prompt_eval)
            
            with st.spinner("💾 Guardando resultados en Supabase..."):
                data_insercion = {
                    "nombre_candidato": cv_json.get("nombre", "Desconocido"),
                    "datos_cv": cv_json,
                    "score": evaluacion.get("score", 0),
                    "decision": evaluacion.get("decision", "Error"),
                    "razonamiento": evaluacion.get("razonamiento", "Sin razón")
                }
                supabase.table("candidatos_evaluados").insert(data_insercion).execute()
            
            # ==========================================
            # 4. RESULTADOS (XAI)
            # ==========================================
            st.success("✅ Análisis completado. Datos persistidos en la nube.")
            st.divider()
            
            st.subheader(f"Resultados para: {data_insercion['nombre_candidato']}")
            m_col1, m_col2 = st.columns(2)
            m_col1.metric("Score de Compatibilidad", f"{data_insercion['score']}/100")
            
            color = "green" if data_insercion['decision'].lower() == 'apto' else "red"
            m_col2.markdown(f"**Decisión:** :{color}[{data_insercion['decision']}]")
            
            st.info(f"**Auditoría de Decisión (XAI):**\n\n{data_insercion['razonamiento']}")
            
            with st.expander("Ver JSON estructurado del CV"):
                st.json(cv_json)