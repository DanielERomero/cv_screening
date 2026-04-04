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

    db_client = create_client(supa_url, supa_key)
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
            temperature=0,
            response_format={"type": "json_object"}
        )
        contenido = response.choices[0].message.content
        return json.loads(contenido)
    except Exception as e:
        st.error(f"Error en la inferencia con GPT-4o: {e}")
        return {}

# ==========================================
# 3. INTERFAZ DE USUARIO
# ==========================================
st.title("☁️ Sistema de Selección Automatizada")
st.markdown("Sube un CV, define el Job Spec y deja que la IA evalúe la compatibilidad con explicabilidad total.")

# --- Session state defaults ---
if "proceso_nombre" not in st.session_state:
    st.session_state.proceso_nombre = ""
if "job_spec" not in st.session_state:
    st.session_state.job_spec = ""
if "ultimo_resultado" not in st.session_state:
    st.session_state.ultimo_resultado = None  # dict con cv_json + evaluacion

tab_config, tab_evaluar, tab_historial = st.tabs([
    "⚙️ Configuración del proceso",
    "📄 Evaluar CV",
    "📊 Historial",
])

# ==========================================
# TAB 1 — CONFIGURACIÓN DEL PROCESO
# ==========================================
with tab_config:
    st.subheader("Configuración del proceso de selección")
    st.markdown("Define el contexto del proceso. Estos datos se usarán en la pestaña **Evaluar CV** y quedan activos durante toda la sesión.")

    proceso_nombre_input = st.text_input(
        "Nombre del proceso de selección",
        value=st.session_state.proceso_nombre,
        placeholder="Ej: Data Engineer Q1 2026",
    )

    job_spec_input = st.text_area(
        "Requerimientos del Puesto (Job Spec)",
        value=st.session_state.job_spec,
        height=250,
        placeholder="Ej: Buscamos un Data Scientist con 3 años de experiencia en Python...",
    )

    if st.button("Guardar configuración", type="primary"):
        if not proceso_nombre_input or not job_spec_input:
            st.warning("⚠️ Completa el nombre del proceso y el Job Spec antes de guardar.")
        else:
            st.session_state.proceso_nombre = proceso_nombre_input
            st.session_state.job_spec = job_spec_input
            st.success("✅ Configuración guardada. Ya puedes evaluar CVs.")

# ==========================================
# TAB 2 — EVALUAR CV
# ==========================================
with tab_evaluar:
    st.subheader("Evaluación de candidato")

    if not st.session_state.proceso_nombre or not st.session_state.job_spec:
        st.info("ℹ️ Primero configura el proceso en la pestaña **⚙️ Configuración del proceso**.")
    else:
        st.markdown(
            f"**Proceso activo:** {st.session_state.proceso_nombre}  \n"
            f"**Job Spec:** {st.session_state.job_spec[:120]}{'...' if len(st.session_state.job_spec) > 120 else ''}"
        )
        st.divider()

        archivo_subido = st.file_uploader("Sube el CV del candidato (PDF)", type=["pdf"])

        if st.button("Ejecutar Motor de Evaluación", type="primary", use_container_width=True):
            if not archivo_subido:
                st.warning("⚠️ Sube un archivo PDF para continuar.")
            else:
                with st.status("Procesando CV...", expanded=True) as status:
                    st.write("📄 Extrayendo texto del PDF...")
                    texto_cv, num_paginas = extraer_texto_en_memoria(archivo_subido)

                    if not texto_cv:
                        status.update(label="Error en la extracción", state="error")
                        st.stop()

                    st.write("🧠 Estructurando CV con GPT-4.1...")
                    prompt_estructura = get_user_prompt_estructuracion(texto_cv)
                    cv_json = interactuar_con_gpt(prompt_estructura, SYS_PROMPT_ESTRUCTURACION)

                    st.write("⚖️ Evaluando compatibilidad con el Job Spec...")
                    prompt_evaluacion = get_user_prompt_evaluacion(json.dumps(cv_json), st.session_state.job_spec)
                    evaluacion = interactuar_con_gpt(prompt_evaluacion, SYS_PROMPT_EVALUACION)

                    st.write("💾 Guardando resultados en Supabase...")
                    archivo_subido.seek(0)
                    pdf_bytes = archivo_subido.read()
                    file_hash = hashlib.sha256(pdf_bytes).hexdigest()

                    resp_bronze = supabase.schema("bronze").table("raw_cvs").insert({
                        "proceso_nombre": st.session_state.proceso_nombre,
                        "filename":       archivo_subido.name,
                        "file_hash":      file_hash,
                        "texto_crudo":    texto_cv,
                        "num_paginas":    num_paginas,
                        "tamanio_bytes":  len(pdf_bytes),
                    }).execute()
                    raw_cv_id = resp_bronze.data[0]["id"]

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

                    supabase.schema("gold").table("evaluaciones").insert({
                        "cv_estructurado_id":    cv_estructurado_id,
                        "score_total":           evaluacion.get("score_total", 0),
                        "score_skills_tecnicos": evaluacion.get("score_skills_tecnicos"),
                        "score_experiencia":     evaluacion.get("score_experiencia"),
                        "score_educacion":       evaluacion.get("score_educacion"),
                        "score_idiomas":         evaluacion.get("score_idiomas"),
                        "score_fit_general":     evaluacion.get("score_fit_general"),
                        "recomendacion":         evaluacion.get("recomendacion", "descartar"),
                        "justificacion_general": evaluacion.get("justificacion_general"),
                        "fortalezas":            evaluacion.get("fortalezas", []),
                        "brechas":               evaluacion.get("brechas", []),
                    }).execute()

                    st.session_state.ultimo_resultado = {
                        "cv_json":   cv_json,
                        "evaluacion": evaluacion,
                    }
                    status.update(label="✅ Análisis completado", state="complete", expanded=False)

        # --- Mostrar último resultado ---
        if st.session_state.ultimo_resultado:
            resultado = st.session_state.ultimo_resultado
            cv_json   = resultado["cv_json"]
            evaluacion = resultado["evaluacion"]

            st.divider()
            nombre_candidato = cv_json.get("nombre_candidato", "Desconocido")
            st.subheader(f"Resultados para: {nombre_candidato}")

            # --- Score total + decisión ---
            score         = evaluacion.get("score_total", 0)
            recomendacion = evaluacion.get("recomendacion", "descartar")

            if recomendacion in ["prioridad", "entrevistar"]:
                color = "green"
            elif recomendacion == "considerar":
                color = "orange"
            else:
                color = "red"

            h_col1, h_col2 = st.columns(2)
            h_col1.metric("Score de Compatibilidad", f"{score}/100")
            h_col2.markdown(f"**Decisión:** :{color}[{recomendacion.capitalize()}]")

            # --- Desglose por dimensión ---
            st.markdown("### Desglose por dimensión")
            dimensiones = [
                ("🛠️ Skills técnicos",  evaluacion.get("score_skills_tecnicos")),
                ("💼 Experiencia",       evaluacion.get("score_experiencia")),
                ("🎓 Educación",         evaluacion.get("score_educacion")),
                ("🌐 Idiomas",           evaluacion.get("score_idiomas")),
                ("🎯 Fit general",       evaluacion.get("score_fit_general")),
            ]
            d_cols = st.columns(len(dimensiones))
            for col, (label, val) in zip(d_cols, dimensiones):
                if val is not None:
                    col.metric(label, f"{val:.0f}/100")
                else:
                    col.metric(label, "—")

            # --- XAI ---
            st.markdown("### Auditoría de Decisión (XAI)")
            fortalezas = evaluacion.get("fortalezas", [])
            brechas    = evaluacion.get("brechas", [])

            st.success("**🚀 Fortalezas:**\n\n" + "\n".join(f"• {f}" for f in fortalezas))
            st.warning("**⚠️ Brechas:**\n\n"    + "\n".join(f"• {b}" for b in brechas))
            st.info(f"**📊 Justificación:**\n\n{evaluacion.get('justificacion_general', 'No especificada.')}")

            with st.expander("Ver JSON estructurado del CV"):
                st.json(cv_json)

# ==========================================
# TAB 3 — HISTORIAL
# ==========================================
with tab_historial:
    st.subheader("Historial de evaluaciones")

    if st.button("Cargar historial", type="secondary"):
        with st.spinner("Consultando base de datos..."):
            try:
                resp = (
                    supabase.schema("gold")
                    .table("evaluaciones")
                    .select("id, score_total, recomendacion, justificacion_general, created_at, cv_estructurado_id")
                    .order("created_at", desc=True)
                    .limit(50)
                    .execute()
                )
                evaluaciones = resp.data

                if not evaluaciones:
                    st.info("No hay evaluaciones registradas aún.")
                else:
                    # Obtener nombres de candidatos (silver) en una sola consulta
                    ids = [e["cv_estructurado_id"] for e in evaluaciones]
                    resp_silver = (
                        supabase.schema("silver")
                        .table("cv_estructurados")
                        .select("id, nombre_candidato, ultimo_cargo, ultima_empresa, raw_cv_id")
                        .in_("id", ids)
                        .execute()
                    )
                    silver_map = {r["id"]: r for r in resp_silver.data}

                    # Obtener proceso_nombre desde bronze
                    raw_ids = [silver_map[i]["raw_cv_id"] for i in ids if i in silver_map]
                    resp_bronze = (
                        supabase.schema("bronze")
                        .table("raw_cvs")
                        .select("id, proceso_nombre")
                        .in_("id", raw_ids)
                        .execute()
                    )
                    bronze_map = {r["id"]: r["proceso_nombre"] for r in resp_bronze.data}

                    # Construir filas
                    filas = []
                    for e in evaluaciones:
                        silver = silver_map.get(e["cv_estructurado_id"], {})
                        raw_id = silver.get("raw_cv_id")
                        filas.append({
                            "Proceso":   bronze_map.get(raw_id, "—"),
                            "Candidato": silver.get("nombre_candidato", "—"),
                            "Cargo":     silver.get("ultimo_cargo", "—"),
                            "Empresa":   silver.get("ultima_empresa", "—"),
                            "Score":     e["score_total"],
                            "Decisión":  e["recomendacion"].capitalize() if e["recomendacion"] else "—",
                            "Fecha":     e["created_at"][:10] if e.get("created_at") else "—",
                        })

                    st.dataframe(filas, use_container_width=True)
                    st.caption(f"Mostrando los últimos {len(filas)} registros.")

            except Exception as ex:
                st.error(f"Error al consultar Supabase: {ex}")
