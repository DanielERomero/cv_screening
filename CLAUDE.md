# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

AI-powered CV screening system with Explainable AI (XAI). Accepts a PDF resume and a job specification, then runs a two-phase LLM pipeline to structure the CV and evaluate the candidate, storing results in Supabase.

## Running the application

```bash
# Activate virtual environment (Windows)
env_screening\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run Streamlit web app (primary interface)
streamlit run app.py

# Run CLI batch processing
python main.py

# Run tests (script-based, no framework)
python test_extraccion.py
python test_estructuracion.py
```

## Architecture

### Entry points

- **`app.py`** — Streamlit web UI: upload PDF + enter job spec → see evaluation. Handles its own PDF extraction inline.
- **`main.py`** — CLI/batch pipeline with the same logic but file-based I/O and slightly different model config.
- **`prompts.py`** — Single source of truth for all LLM system prompts and Pydantic schemas. Never define prompts or schemas elsewhere.

### Two-phase LLM pipeline

1. **Structuring** (`SYS_PROMPT_ESTRUCTURACION`): raw PDF text → `CVSchema` JSON. Strict extraction only — no inference.
2. **Evaluation** (`SYS_PROMPT_EVALUACION`): structured CV + job spec → `EvaluacionSchema` JSON. Scores on 5 dimensions: technical skills, experience, education, languages, general fit.

All LLM calls use `response_format={"type": "json_object"}` and `temperature=0`.

### Scoring thresholds (defined in `prompts.py`)

| Score | Decision |
|-------|----------|
| 0–40 | Descartar |
| 41–60 | Considerar |
| 61–80 | Entrevistar |
| 81–100 | Prioridad |

### Key Pydantic schemas (`prompts.py`)

- `CVSchema` — 12-field resume structure
- `EvaluacionSchema` — score, nivel, motivos_contratacion, habilidades_faltantes, justificacion
- `ExperienciaLaboral`, `Educacion` — nested models

### LLM backend

Uses the **OpenAI Python client** pointed at GitHub Models (Azure inference endpoint):
- Endpoint: `https://models.inference.ai.azure.com`
- Auth: `GITHUB_TOKEN`
- `app.py` uses `gpt-4.1`; `main.py` uses `gpt-4o` (minor inconsistency)

### Database

Supabase table `candidatos_evaluados` stores:
- `nombre_candidato`, `datos_cv` (JSONB), `score`, `decision`, `razonamiento`

### Secrets management

Cloud deployment (Streamlit Cloud): reads from `st.secrets`.
Local development: falls back to `.env` via `python-dotenv`.
Required vars: `SUPABASE_URL`, `SUPABASE_KEY`, `GITHUB_TOKEN`.
