import json
from pydantic import BaseModel, Field
from typing import List, Optional


# =============================================================
# 0. ESQUEMAS DE DATOS — alineados con Medallion (Silver + Gold)
# =============================================================

class ExperienciaDetalle(BaseModel):
    empresa:     str
    cargo:       str
    inicio:      Optional[str] = None   # texto libre: "2021", "Mar 2022", etc.
    fin:         Optional[str] = None   # idem, o "Actualidad"
    descripcion: str

class EducacionDetalle(BaseModel):
    institucion: str
    carrera:     str
    inicio:      Optional[str] = None
    fin:         Optional[str] = None

class Idioma(BaseModel):
    idioma: str
    nivel:  str   # "Nativo" | "Avanzado" | "Intermedio" | "Básico"

# Silver — cv_estructurados
class CVSchema(BaseModel):
    nombre_candidato:      Optional[str]   = Field(None, description="Nombre y apellidos completos")
    email:                 Optional[str]   = None
    telefono:              Optional[str]   = None
    ubicacion:             Optional[str]   = None
    resumen_perfil:        Optional[str]   = None
    experiencia_anios:     Optional[float] = Field(None, description="Total de años de experiencia laboral estimados")
    ultimo_cargo:          Optional[str]   = Field(None, description="Cargo más reciente")
    ultima_empresa:        Optional[str]   = Field(None, description="Empresa más reciente")
    educacion_nivel:       Optional[str]   = Field(None, description="Nivel más alto: Secundaria | Técnico | Bachiller | Licenciatura | Maestría | Doctorado")
    educacion_carrera:     Optional[str]   = Field(None, description="Carrera del título más alto")
    educacion_institucion: Optional[str]   = Field(None, description="Institución del título más alto")
    skills_tecnicos:       List[str]              = Field(default_factory=list)
    idiomas:               List[Idioma]           = Field(default_factory=list)
    experiencia_detalle:   List[ExperienciaDetalle] = Field(default_factory=list)
    educacion_detalle:     List[EducacionDetalle]   = Field(default_factory=list)

# Gold — evaluaciones
class EvaluacionSchema(BaseModel):
    score_total:           float     = Field(description="Puntuación global 0–100, promedio ponderado de las 5 dimensiones")
    score_skills_tecnicos: float     = Field(description="Score 0–100: cobertura de skills técnicos requeridos")
    score_experiencia:     float     = Field(description="Score 0–100: años y tipo de experiencia vs. requisitos")
    score_educacion:       float     = Field(description="Score 0–100: nivel y carrera de formación vs. requisitos")
    score_idiomas:         float     = Field(description="Score 0–100: cumplimiento de requisitos de idiomas")
    score_fit_general:     float     = Field(description="Score 0–100: coherencia de trayectoria y nivel del candidato")
    recomendacion:         str       = Field(description="Exactamente uno de: descartar | considerar | entrevistar | prioridad")
    justificacion_general: str       = Field(description="Justificación holística del score en 3-4 oraciones")
    fortalezas:            List[str] = Field(description="Hasta 3 fortalezas concretas del candidato para este puesto")
    brechas:               List[str] = Field(description="Hasta 3 brechas o carencias críticas para este puesto")


# Schemas JSON para inyectar en los prompts
json_schema_cv         = json.dumps(CVSchema.model_json_schema(),         ensure_ascii=False, indent=2)
json_schema_evaluacion = json.dumps(EvaluacionSchema.model_json_schema(), ensure_ascii=False, indent=2)


# =============================================================
# 1. PROMPTS DEL SISTEMA (System Prompts)
# =============================================================

SYS_PROMPT_ESTRUCTURACION = f"""
Eres un extractor especializado de información de CVs.
Tu única función es extraer datos y devolverlos en el formato indicado.
No evalúes, no opines, no inferas más allá de lo explícitamente escrito.

CONTEXTO:
Se te proporciona el texto completo de un CV profesional.

TAREA:
Extrae la información del CV y devuélvela en formato JSON válido.
Si un campo no está presente, devuelve null. No inventes información ausente.

CAMPOS QUE REQUIEREN CRITERIO:
- experiencia_anios: suma los períodos laborales; si hay solapamientos, estima conservadoramente. Devuelve null si no hay datos suficientes.
- ultimo_cargo / ultima_empresa: corresponden al trabajo más reciente según las fechas.
- educacion_nivel: clasifica el título más alto entre: Secundaria | Técnico | Bachiller | Licenciatura | Maestría | Doctorado
- educacion_carrera / educacion_institucion: del título más alto obtenido.
- idiomas: lista de objetos con "idioma" y "nivel". nivel debe ser: Nativo | Avanzado | Intermedio | Básico.
- skills_tecnicos: herramientas, lenguajes, frameworks y plataformas mencionadas explícitamente.
- experiencia_detalle: todos los empleos, con inicio/fin como texto libre (ej: "2021", "Mar 2022", "Actualidad").
- educacion_detalle: todos los estudios formales.

RESTRICCIONES:
1. Tu respuesta debe ser SOLO un objeto JSON válido, comenzando con {{ y terminando con }}.
2. El JSON DEBE cumplir estrictamente con este schema:
{json_schema_cv}
3. Escapa correctamente las comillas dobles internas (usa \\") o reemplázalas por comillas simples.
4. Reemplaza saltos de línea dentro de los textos por \\n.
""".strip()


SYS_PROMPT_EVALUACION = f"""
Eres un evaluador experto en selección de talento con 15 años de experiencia en RRHH técnico.
Evalúas candidatos de forma objetiva basándote exclusivamente en criterios profesionales.

CONTEXTO:
Recibes:
1. Un perfil de candidato estructurado (extraído de su CV)
2. Una descripción del puesto (Job Description)

TAREA:
Evalúa el ajuste candidato-puesto en 5 dimensiones (score total 0–100):

- skills_tecnicos   ¿Qué % de skills requeridos posee? ¿Tiene skills adicionales valiosos?
- experiencia       ¿Los años y tipo de experiencia coinciden con lo solicitado?
- educacion         ¿La formación cumple los requisitos mínimos? Considera equivalencia por experiencia.
- idiomas           ¿Cumple los requisitos de idiomas del puesto?
- fit_general       ¿Hay coherencia en la trayectoria? ¿El candidato está en el nivel correcto?

RESTRICCIONES:
- Evalúa solo lo que está en los datos. Si un campo es null, asume ausencia.
- Las justificaciones deben ser específicas, nunca genéricas.
  Mal: "Tiene buena experiencia técnica"
  Bien: "3 de 5 skills requeridos presentes; ausencia de Kubernetes es brecha crítica"
- recomendacion debe ser exactamente (en minúsculas):
  0–40   → descartar
  41–60  → considerar
  61–80  → entrevistar
  81–100 → prioridad
- fortalezas y brechas: máximo 3 ítems cada una, concisos (1 oración por ítem).

FORMATO DE RESPUESTA:
SOLO un objeto JSON válido que cumpla este schema:
{json_schema_evaluacion}
""".strip()


# =============================================================
# 2. PROMPTS DEL USUARIO (User Prompts)
# =============================================================

def get_user_prompt_estructuracion(texto_cv: str) -> str:
    return f"Extrae los datos de este CV estrictamente siguiendo las reglas indicadas:\n---\n{texto_cv}\n---\n"

def get_user_prompt_evaluacion(cv_json_str: str, job_spec: str) -> str:
    return f"PUESTO:\n---\n{job_spec}\n---\n\nCANDIDATO (datos estructurados):\n---\n{cv_json_str}\n---\n\nJSON:\n"
