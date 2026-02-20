import streamlit as st
from supabase import create_client, Client
import os
from dotenv import load_dotenv

# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA
# ==========================================
st.set_page_config(
    page_title="AI Resume Screener",
    page_icon="🤖",
    layout="wide"
)

st.title("📊 Panel de Selección Automática (XAI-Powered)")
st.markdown("""
*Motor de evaluación impulsado por LLM local (Privacy-First). Evalúa candidatos con explicabilidad total.*
""")

# ==========================================
# 2. CONEXIÓN A SUPABASE (Local y Cloud)
# ==========================================
@st.cache_resource
def init_connection():
    """
    Inicializa la conexión. Busca primero en los secretos de Streamlit (Cloud)
    y si falla (por cualquier razón), usa el .env local. Ingeniería a prueba de fallos.
    """
    url = None
    key = None
    
    try:
        # Intento 1: Streamlit Cloud Secrets
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    except (FileNotFoundError, KeyError):
        # Intento 2: Entorno local (.env)
        load_dotenv()
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
    
    if not url or not key:
        st.error("🚨 Faltan las credenciales de Supabase. Configúralas en Streamlit Secrets o en tu .env local.")
        st.stop()
        
    return create_client(url, key)

supabase = init_connection()

# ==========================================
# 3. EXTRACCIÓN Y VISUALIZACIÓN DE DATOS
# ==========================================
def load_data():
    # Traemos los candidatos ordenados por el mejor score
    respuesta = supabase.table("candidatos_evaluados").select("*").order("score", desc=True).execute()
    return respuesta.data

candidatos = load_data()

if not candidatos:
    st.info("No hay candidatos evaluados en la base de datos. Pasa un CV por el motor de procesamiento primero.")
else:
    # Métricas rápidas estilo ejecutivo
    total_cands = len(candidatos)
    aptos = sum(1 for c in candidatos if c.get('decision', '').lower() == 'apto')
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total de Candidatos", total_cands)
    col2.metric("Candidatos Aptos", aptos)
    col3.metric("Tasa de Aprobación", f"{(aptos/total_cands)*100:.1f}%")
    
    st.divider()

    # Listado de candidatos con foco en el "Porqué" (Explainable AI)
    st.subheader("📋 Resultados del Screening")
    
    for cand in candidatos:
        score = cand.get('score', 0)
        decision = cand.get('decision', 'Desconocido')
        nombre = cand.get('nombre_candidato', 'Sin Nombre')
        
        # Color coding simple
        color = "🟢" if decision.lower() == 'apto' else "🔴"
        
        with st.expander(f"{color} {nombre} - Score: {score}/100"):
            st.markdown(f"**Decisión de la IA:** `{decision}`")
            
            # Aquí está el corazón de tu tesis: La transparencia
            st.info(f"**Justificación Técnica:**\n\n{cand.get('razonamiento', 'No hay justificación.')}")
            
            # Mostrar los datos estructurados en formato crudo para auditoría
            with st.popover("Ver JSON del CV extraído"):
                st.json(cand.get('datos_cv', {}))