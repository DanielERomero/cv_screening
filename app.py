import streamlit as st
import pdfplumber
import hashlib
import json
import io
import csv
import os
import plotly.graph_objects as go
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
# 3. FUNCIONES DE VISUALIZACIÓN
# ==========================================

DIM_LABELS = ["Skills técnicos", "Experiencia", "Educación", "Idiomas", "Fit general"]
DIM_KEYS   = ["score_skills_tecnicos", "score_experiencia", "score_educacion", "score_idiomas", "score_fit_general"]

DECISION_COLOR_HEX = {
    "prioridad":   "#22c55e",
    "entrevistar": "#eab308",
    "considerar":  "#f97316",
    "descartar":   "#ef4444",
}

def radar_candidato(evaluacion: dict, nombre: str) -> go.Figure:
    valores = [evaluacion.get(k) or 0 for k in DIM_KEYS]
    valores_cerrados = valores + [valores[0]]
    labels_cerrados  = DIM_LABELS + [DIM_LABELS[0]]
    rec   = evaluacion.get("recomendacion", "descartar")
    color = DECISION_COLOR_HEX.get(rec, "#6b7280")

    fig = go.Figure(go.Scatterpolar(
        r=valores_cerrados,
        theta=labels_cerrados,
        fill="toself",
        fillcolor=color,
        line=dict(color=color),
        opacity=0.6,
        name=nombre,
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        showlegend=False,
        margin=dict(t=30, b=30, l=40, r=40),
        height=320,
    )
    return fig


def donut_decisiones(filas: list) -> go.Figure:
    conteo = {"Prioridad": 0, "Entrevistar": 0, "Considerar": 0, "Descartar": 0}
    for f in filas:
        decision = f.get("recomendacion", "descartar").capitalize()
        if decision in conteo:
            conteo[decision] += 1
    colores = [
        DECISION_COLOR_HEX["prioridad"],
        DECISION_COLOR_HEX["entrevistar"],
        DECISION_COLOR_HEX["considerar"],
        DECISION_COLOR_HEX["descartar"],
    ]
    fig = go.Figure(go.Pie(
        labels=list(conteo.keys()),
        values=list(conteo.values()),
        hole=0.55,
        marker_colors=colores,
        textinfo="label+percent",
    ))
    fig.update_layout(
        showlegend=False,
        margin=dict(t=20, b=20, l=20, r=20),
        height=300,
    )
    return fig


def histograma_scores(filas: list) -> go.Figure:
    scores = [f["score_total"] for f in filas if f.get("score_total") is not None]
    fig = go.Figure(go.Histogram(
        x=scores,
        xbins=dict(start=0, end=100, size=10),
        marker_color="#6366f1",
        opacity=0.8,
    ))
    fig.update_layout(
        xaxis=dict(title="Score total", range=[0, 100]),
        yaxis=dict(title="Candidatos"),
        bargap=0.1,
        margin=dict(t=20, b=40, l=40, r=20),
        height=300,
    )
    return fig


def radar_promedio(filas: list) -> go.Figure:
    promedios = []
    for key in DIM_KEYS:
        vals = [f[key] for f in filas if f.get(key) is not None]
        promedios.append(sum(vals) / len(vals) if vals else 0)

    valores_cerrados = promedios + [promedios[0]]
    labels_cerrados  = DIM_LABELS + [DIM_LABELS[0]]

    fig = go.Figure(go.Scatterpolar(
        r=valores_cerrados,
        theta=labels_cerrados,
        fill="toself",
        fillcolor="#6366f1",
        line=dict(color="#6366f1"),
        opacity=0.5,
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        showlegend=False,
        margin=dict(t=30, b=30, l=40, r=40),
        height=340,
    )
    return fig


def bar_ranking(resultados: list) -> go.Figure:
    nombres   = [r["cv_json"].get("nombre_candidato", "—") for r in resultados]
    scores    = [r["evaluacion"].get("score_total", 0) for r in resultados]
    decisiones = [r["evaluacion"].get("recomendacion", "descartar") for r in resultados]
    colores   = [DECISION_COLOR_HEX.get(d, "#6b7280") for d in decisiones]

    fig = go.Figure(go.Bar(
        x=scores,
        y=nombres,
        orientation="h",
        marker_color=colores,
        text=[f"{s}/100" for s in scores],
        textposition="outside",
    ))
    fig.update_layout(
        xaxis=dict(range=[0, 110], title="Score"),
        yaxis=dict(autorange="reversed"),
        margin=dict(t=20, b=20, l=10, r=60),
        height=max(200, len(resultados) * 55),
    )
    return fig


# ==========================================
# 4. INTERFAZ DE USUARIO
# ==========================================
st.title("☁️ Sistema de Selección Automatizada")
st.markdown("Sube un CV, define el Job Spec y deja que la IA evalúe la compatibilidad con explicabilidad total.")

# --- Session state defaults ---
if "proceso_nombre" not in st.session_state:
    st.session_state.proceso_nombre = ""
if "job_spec" not in st.session_state:
    st.session_state.job_spec = ""
if "resultados_sesion" not in st.session_state:
    st.session_state.resultados_sesion = []  # lista de {cv_json, evaluacion} por candidato

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

        archivos_subidos = st.file_uploader(
            "Sube los CVs de los candidatos (PDF)",
            type=["pdf"],
            accept_multiple_files=True,
        )

        col_btn, col_clear = st.columns([3, 1])
        ejecutar = col_btn.button("Ejecutar Motor de Evaluación", type="primary", use_container_width=True)
        if col_clear.button("Limpiar resultados", use_container_width=True):
            st.session_state.resultados_sesion = []
            st.rerun()

        if ejecutar:
            if not archivos_subidos:
                st.warning("⚠️ Sube al menos un archivo PDF para continuar.")
            else:
                nuevos_resultados = []
                total = len(archivos_subidos)

                for i, archivo in enumerate(archivos_subidos, start=1):
                    with st.status(f"Procesando {i}/{total}: {archivo.name}", expanded=True) as status:
                        st.write("📄 Extrayendo texto del PDF...")
                        texto_cv, num_paginas = extraer_texto_en_memoria(archivo)

                        if not texto_cv:
                            status.update(label=f"❌ Error extrayendo {archivo.name}", state="error")
                            continue

                        st.write("🧠 Estructurando CV con GPT-4.1...")
                        prompt_estructura = get_user_prompt_estructuracion(texto_cv)
                        cv_json = interactuar_con_gpt(prompt_estructura, SYS_PROMPT_ESTRUCTURACION)

                        st.write("⚖️ Evaluando compatibilidad con el Job Spec...")
                        prompt_evaluacion = get_user_prompt_evaluacion(json.dumps(cv_json), st.session_state.job_spec)
                        evaluacion = interactuar_con_gpt(prompt_evaluacion, SYS_PROMPT_EVALUACION)

                        st.write("💾 Guardando en Supabase...")
                        archivo.seek(0)
                        pdf_bytes = archivo.read()
                        file_hash = hashlib.sha256(pdf_bytes).hexdigest()

                        resp_bronze = supabase.schema("bronze").table("raw_cvs").insert({
                            "proceso_nombre": st.session_state.proceso_nombre,
                            "filename":       archivo.name,
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

                        nuevos_resultados.append({"cv_json": cv_json, "evaluacion": evaluacion})
                        status.update(label=f"✅ {archivo.name}", state="complete", expanded=False)

                st.session_state.resultados_sesion = nuevos_resultados
                st.success(f"✅ {len(nuevos_resultados)}/{total} CVs procesados y persistidos.")

        # --- Ranking + detalle por candidato ---
        if st.session_state.resultados_sesion:
            resultados = sorted(
                st.session_state.resultados_sesion,
                key=lambda r: r["evaluacion"].get("score_total", 0),
                reverse=True,
            )

            st.divider()
            st.markdown("## Ranking de candidatos")

            DECISION_COLOR = {
                "prioridad":   "🟢",
                "entrevistar": "🟡",
                "considerar":  "🟠",
                "descartar":   "🔴",
            }

            ranking_filas = []
            for pos, r in enumerate(resultados, start=1):
                ev  = r["evaluacion"]
                rec = ev.get("recomendacion", "descartar")
                ranking_filas.append({
                    "#":              pos,
                    "Candidato":      r["cv_json"].get("nombre_candidato", "—"),
                    "Score":          ev.get("score_total", 0),
                    "Skills":         ev.get("score_skills_tecnicos", "—"),
                    "Experiencia":    ev.get("score_experiencia", "—"),
                    "Educación":      ev.get("score_educacion", "—"),
                    "Idiomas":        ev.get("score_idiomas", "—"),
                    "Fit":            ev.get("score_fit_general", "—"),
                    "Decisión":       f"{DECISION_COLOR.get(rec, '')} {rec.capitalize()}",
                })
            st.dataframe(ranking_filas, use_container_width=True, hide_index=True)
            st.plotly_chart(bar_ranking(resultados), use_container_width=True)

            # --- Exportación CSV ---
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=ranking_filas[0].keys())
            writer.writeheader()
            writer.writerows(ranking_filas)
            nombre_proceso = st.session_state.proceso_nombre.replace(" ", "_")
            st.download_button(
                label="⬇️ Descargar ranking como CSV",
                data=buf.getvalue().encode("utf-8"),
                file_name=f"ranking_{nombre_proceso}.csv",
                mime="text/csv",
            )

            st.divider()
            st.markdown("## Detalle por candidato")
            for r in resultados:
                cv_json   = r["cv_json"]
                evaluacion = r["evaluacion"]
                nombre    = cv_json.get("nombre_candidato", "Desconocido")
                score     = evaluacion.get("score_total", 0)
                rec       = evaluacion.get("recomendacion", "descartar")

                with st.expander(f"{DECISION_COLOR.get(rec, '')} {nombre} — {score}/100"):
                    exp_col1, exp_col2 = st.columns([1, 1])

                    with exp_col1:
                        # Métricas de dimensión
                        dimensiones = [
                            ("🛠️ Skills",      evaluacion.get("score_skills_tecnicos")),
                            ("💼 Experiencia", evaluacion.get("score_experiencia")),
                            ("🎓 Educación",   evaluacion.get("score_educacion")),
                            ("🌐 Idiomas",     evaluacion.get("score_idiomas")),
                            ("🎯 Fit",         evaluacion.get("score_fit_general")),
                        ]
                        d_cols = st.columns(len(dimensiones))
                        for col, (label, val) in zip(d_cols, dimensiones):
                            col.metric(label, f"{val:.0f}/100" if val is not None else "—")

                        fortalezas = evaluacion.get("fortalezas", [])
                        brechas    = evaluacion.get("brechas", [])
                        st.success("**🚀 Fortalezas:**\n\n" + "\n".join(f"• {f}" for f in fortalezas))
                        st.warning("**⚠️ Brechas:**\n\n"    + "\n".join(f"• {b}" for b in brechas))
                        st.info(f"**📊 Justificación:**\n\n{evaluacion.get('justificacion_general', 'No especificada.')}")

                    with exp_col2:
                        st.plotly_chart(
                            radar_candidato(evaluacion, nombre),
                            use_container_width=True,
                        )

                    with st.expander("Ver JSON estructurado del CV"):
                        st.json(cv_json)

# ==========================================
# TAB 3 — HISTORIAL
# ==========================================
with tab_historial:
    st.subheader("Historial de evaluaciones")

    if "historial_data" not in st.session_state:
        st.session_state.historial_data = []

    if st.button("Cargar / Actualizar historial", type="secondary"):
        with st.spinner("Consultando base de datos..."):
            try:
                resp = (
                    supabase.schema("gold")
                    .table("evaluaciones")
                    .select(
                        "id, score_total, recomendacion, created_at, cv_estructurado_id,"
                        "score_skills_tecnicos, score_experiencia, score_educacion,"
                        "score_idiomas, score_fit_general"
                    )
                    .order("created_at", desc=True)
                    .limit(200)
                    .execute()
                )
                evaluaciones = resp.data

                if not evaluaciones:
                    st.info("No hay evaluaciones registradas aún.")
                else:
                    ids = [e["cv_estructurado_id"] for e in evaluaciones]
                    resp_silver = (
                        supabase.schema("silver")
                        .table("cv_estructurados")
                        .select("id, nombre_candidato, ultimo_cargo, ultima_empresa, raw_cv_id")
                        .in_("id", ids)
                        .execute()
                    )
                    silver_map = {r["id"]: r for r in resp_silver.data}

                    raw_ids = [silver_map[i]["raw_cv_id"] for i in ids if i in silver_map]
                    resp_bronze = (
                        supabase.schema("bronze")
                        .table("raw_cvs")
                        .select("id, proceso_nombre")
                        .in_("id", raw_ids)
                        .execute()
                    )
                    bronze_map = {r["id"]: r["proceso_nombre"] for r in resp_bronze.data}

                    filas = []
                    for e in evaluaciones:
                        silver = silver_map.get(e["cv_estructurado_id"], {})
                        raw_id = silver.get("raw_cv_id")
                        filas.append({
                            "proceso_nombre":       bronze_map.get(raw_id, "—"),
                            "nombre_candidato":     silver.get("nombre_candidato", "—"),
                            "ultimo_cargo":         silver.get("ultimo_cargo", "—"),
                            "ultima_empresa":       silver.get("ultima_empresa", "—"),
                            "score_total":          e.get("score_total"),
                            "recomendacion":        e.get("recomendacion", "descartar"),
                            "score_skills_tecnicos": e.get("score_skills_tecnicos"),
                            "score_experiencia":    e.get("score_experiencia"),
                            "score_educacion":      e.get("score_educacion"),
                            "score_idiomas":        e.get("score_idiomas"),
                            "score_fit_general":    e.get("score_fit_general"),
                            "fecha":                e["created_at"][:10] if e.get("created_at") else "—",
                        })

                    st.session_state.historial_data = filas

            except Exception as ex:
                st.error(f"Error al consultar Supabase: {ex}")

    if st.session_state.historial_data:
        filas = st.session_state.historial_data

        # --- Filtro por proceso ---
        procesos = sorted({f["proceso_nombre"] for f in filas if f["proceso_nombre"] != "—"})
        opciones = ["Todos los procesos"] + procesos
        filtro   = st.selectbox("Filtrar por proceso", opciones)
        filas_filtradas = filas if filtro == "Todos los procesos" else [
            f for f in filas if f["proceso_nombre"] == filtro
        ]

        st.caption(f"{len(filas_filtradas)} candidatos · {filtro}")

        # --- Dashboard: 3 gráficos ---
        st.markdown("### Dashboard")
        g_col1, g_col2 = st.columns(2)

        with g_col1:
            st.markdown("**Distribución de decisiones**")
            st.plotly_chart(donut_decisiones(filas_filtradas), use_container_width=True)

        with g_col2:
            st.markdown("**Distribución de scores**")
            st.plotly_chart(histograma_scores(filas_filtradas), use_container_width=True)

        st.markdown("**Perfil promedio del pool (radar de dimensiones)**")
        radar_col, _ = st.columns([1, 1])
        with radar_col:
            st.plotly_chart(radar_promedio(filas_filtradas), use_container_width=True)

        # --- Tabla ---
        st.divider()
        st.markdown("### Detalle de candidatos")
        tabla = [
            {
                "Proceso":    f["proceso_nombre"],
                "Candidato":  f["nombre_candidato"],
                "Cargo":      f["ultimo_cargo"],
                "Score":      f["score_total"],
                "Decisión":   f["recomendacion"].capitalize() if f["recomendacion"] else "—",
                "Fecha":      f["fecha"],
            }
            for f in filas_filtradas
        ]
        st.dataframe(tabla, use_container_width=True, hide_index=True)
        st.caption(f"Mostrando {len(tabla)} registros.")
