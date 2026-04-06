# CV Screening — Sistema de Selección Automatizada con IA

Sistema de evaluación de candidatos impulsado por IA. Permite subir CVs en PDF, definir el perfil del puesto y obtener una evaluación detallada con puntuaciones, justificaciones y recomendaciones de contratación.

---

## Características principales

- **Evaluación automática** de CVs contra un perfil de puesto (Job Spec) usando GPT-4.1
- **Puntuación en 5 dimensiones:** skills técnicos, experiencia, educación, idiomas y encaje general
- **Explainability (XAI):** justificación en lenguaje natural de cada decisión
- **Procesamiento múltiple:** evalúa varios CVs en una sola sesión y genera un ranking comparativo
- **Persistencia en Supabase** con arquitectura Medallion (Bronze → Silver → Gold)
- **Seguimiento de costos** de IA por proceso y por mes
- **Exportación** a CSV, Excel con colores y HTML imprimible para reuniones
- **Copia rápida** de justificaciones para pegar directamente en correos

---

## Arquitectura

### Pipeline de dos fases

```
PDF  →  [Extracción de texto]  →  [Fase 1: Estructuración]  →  [Fase 2: Evaluación]  →  Supabase
```

1. **Estructuración** — El texto crudo del CV se convierte en un JSON estructurado (`CVSchema`) mediante GPT-4.1. Solo extrae, nunca infiere.
2. **Evaluación** — El CV estructurado y el Job Spec se evalúan en 5 dimensiones. El resultado es un JSON (`EvaluacionSchema`) con scores, recomendación y justificación.

### Arquitectura Medallion en Supabase

| Capa | Tabla | Contenido |
|---|---|---|
| **Bronze** | `raw_cvs` | PDF original: texto crudo, hash, tamaño, número de páginas |
| **Silver** | `cv_estructurados` | Datos normalizados del candidato (nombre, cargo, skills, educación…) |
| **Gold** | `evaluaciones` | Scores por dimensión, recomendación, justificación, tokens consumidos y costo |

### Umbrales de decisión

| Puntuación | Decisión |
|---|---|
| 0 – 40 | Descartar |
| 41 – 60 | Considerar |
| 61 – 80 | Entrevistar |
| 81 – 100 | Priorizar |

---

## Estructura del proyecto

```
cv_screening/
├── app.py               # Aplicación Streamlit (interfaz principal)
├── main.py              # Pipeline CLI / procesamiento por lotes
├── prompts.py           # Prompts del sistema y esquemas Pydantic (fuente única de verdad)
├── requirements.txt     # Dependencias
├── test_extraccion.py   # Test de extracción de texto PDF
├── test_estructuracion.py # Test de la fase de estructuración
└── .env                 # Variables de entorno locales (no incluido en el repositorio)
```

---

## Instalación y ejecución

### Requisitos previos

- Python 3.11+
- Cuenta en [Supabase](https://supabase.com)
- Token de [GitHub Models](https://github.com/marketplace/models) con acceso a GPT-4.1

### Pasos

```bash
# 1. Clonar el repositorio
git clone https://github.com/DanielERomero/cv_screening.git
cd cv_screening

# 2. Crear y activar entorno virtual (Windows)
python -m venv env_screening
env_screening\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
#    Crea un archivo .env con:
#    SUPABASE_URL=...
#    SUPABASE_KEY=...
#    GITHUB_TOKEN=...

# 5. Ejecutar la aplicación web
streamlit run app.py
```

### Despliegue en Streamlit Cloud

Las credenciales se configuran en **Settings → Secrets** del proyecto en Streamlit Cloud:

```toml
SUPABASE_URL = "..."
SUPABASE_KEY = "..."
GITHUB_TOKEN = "..."
```

---

## Uso de la aplicación

La app tiene tres pestañas:

### ⚙️ Configuración del proceso
Define el nombre del proceso de selección y el perfil del puesto (Job Spec). Esta configuración queda activa durante toda la sesión.

### 📄 Evaluar CV
Sube uno o varios CVs en PDF. La IA los procesa en secuencia y genera:
- Ranking comparativo de candidatos con puntuaciones por dimensión
- Gráfico de barras del ranking
- Detalle por candidato: puntos fuertes, aspectos a mejorar, justificación y radar de dimensiones
- Copia rápida de la justificación para pegar en un correo
- Exportación a **CSV**, **Excel** (con colores por decisión) y **HTML imprimible** (para reuniones)

### 📊 Historial
Consulta todas las evaluaciones guardadas en Supabase. Incluye:
- Filtro por proceso de selección
- Dashboard con distribución de decisiones, distribución de puntuaciones y perfil promedio del pool
- **Panel de costos:** gasto total por proceso o por mes, con tabla y gráfico
- Exportación a CSV y Excel completo con justificaciones

---

## Modelo LLM y costos

- **Modelo:** `gpt-4.1` vía GitHub Models 
- **Endpoint:** `https://models.inference.ai.azure.com`
- **Tarifas de referencia usadas para el cálculo:**

| Tipo de token | Precio |
|---|---|
| Entrada (input) | $ 2.50 / 1M tokens |
| Entrada en caché | $ 1.25 / 1M tokens |
| Salida (output) | $ 10.00 / 1M tokens |

El costo se calcula y almacena automáticamente en `gold.evaluaciones` por cada CV procesado.

---

## Esquemas de datos (`prompts.py`)

### CVSchema (Silver)
`nombre_candidato`, `email`, `telefono`, `ubicacion`, `resumen_perfil`, `experiencia_anios`, `ultimo_cargo`, `ultima_empresa`, `educacion_nivel`, `educacion_carrera`, `educacion_institucion`, `skills_tecnicos`, `idiomas`, `experiencia_detalle`, `educacion_detalle`

### EvaluacionSchema (Gold)
`score_total`, `score_skills_tecnicos`, `score_experiencia`, `score_educacion`, `score_idiomas`, `score_fit_general`, `recomendacion`, `justificacion_general`, `fortalezas`, `brechas`

---

## Tests

```bash
python test_extraccion.py      # Verifica la extracción de texto de PDFs
python test_estructuracion.py  # Verifica la fase de estructuración con GPT
```

---

## Tecnologías

| Tecnología | Uso |
|---|---|
| [Streamlit](https://streamlit.io) | Interfaz web |
| [OpenAI Python SDK](https://github.com/openai/openai-python) | Cliente LLM (apuntado a GitHub Models) |
| [Supabase](https://supabase.com) | Base de datos (PostgreSQL) |
| [pdfplumber](https://github.com/jsvine/pdfplumber) | Extracción de texto de PDFs |
| [Pydantic](https://docs.pydantic.dev) | Validación de esquemas JSON |
| [Plotly](https://plotly.com/python/) | Visualizaciones interactivas |
| [openpyxl](https://openpyxl.readthedocs.io) | Generación de archivos Excel |
