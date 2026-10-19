from enum import Enum
from typing import List, Optional, Union, Dict, Any
from pydantic import BaseModel, Field, field_validator

# ------------------------------------------------------------------------------
# 1. ENUMS & REQUEST SCHEMAS
# ------------------------------------------------------------------------------

class OralTaskType(str, Enum):
    TASK_2 = "TASK_2"
    TASK_3 = "TASK_3"

class Task3Subtype(str, Enum):
    DIALECTICAL = "DIALECTICAL"
    ANALYTICAL = "ANALYTICAL"

class OralTopicRequest(BaseModel):
    id: str = Field(..., description="ID unique du sujet côté application web")
    task_type: OralTaskType = Field(..., description="Type de tâche (TASK_2 ou TASK_3)")
    task3_type: Optional[Task3Subtype] = Field(None, description="Requis si TASK_3 : DIALECTICAL ou ANALYTICAL")
    content: str = Field(..., description="Consigne / Intitulé du sujet")

class BatchOralTopicRequest(BaseModel):
    topics: List[OralTopicRequest] = Field(..., min_items=1, description="Liste des sujets à traiter")

# ------------------------------------------------------------------------------
# 2. HELPER FUNCTIONS FOR VALIDATORS
# ------------------------------------------------------------------------------

def _coerce_string_to_list(v: Any) -> List[str]:
    """Transforme une chaîne de caractères ou un champ mal structuré en liste de chaînes."""
    if isinstance(v, str):
        return [line.strip("- *").strip() for line in v.split("\n") if line.strip()]
    if isinstance(v, list):
        return [str(item) for item in v]
        return [str(v)]

# ------------------------------------------------------------------------------
# 3. RESPONSE SCHEMAS (Corrections Pédagogiques)
# ------------------------------------------------------------------------------

class ArgumentStruct(BaseModel):
    argument: str = Field(..., description="L'idée / l'argument principal")
    explanation: str = Field(..., description="Explication détaillée")
    example: str = Field(..., description="Exemple concret et illustratif")

class InteractionPair(BaseModel):
    role: str = Field(..., description="Rôle (ex: examinateur ou candidat)")
    texte: str = Field(..., description="La réplique exacte")

class Task2Correction(BaseModel):
    context: str = Field(..., description="Mise en situation et cadre de l'interaction")
    understanding: str = Field(..., description="Compréhension fine des enjeux")
    objective: str = Field(..., description="Objectif global du candidat")
    expected_information: List[str] = Field(..., description="Informations clés à obtenir")
    suggested_questions: List[str] = Field(..., description="Exemples de questions ciblées selon le registre")
    possible_interaction: List[InteractionPair] = Field(..., description="Échange simulé en 5 à 8 répliques (Examinateur/Candidat)")
    
    useful_expressions: List[str] = Field(..., description="Formules de politesse et relances utiles")
    common_mistakes: List[str] = Field(..., description="Erreurs fréquentes et pièges à éviter")

    @field_validator("expected_information", "suggested_questions", "useful_expressions", "common_mistakes", mode="before")
    def validate_lists(cls, v):
        return _coerce_string_to_list(v)

    @field_validator("possible_interaction", mode="before")
    def coerce_interaction(cls, v):
        if isinstance(v, str):
            lines = [l.strip() for l in v.split("\n") if l.strip()]
            formatted = []
            for line in lines:
                if ":" in line:
                    role, text = line.split(":", 1)
                    formatted.append({"role": role.strip(), "texte": text.strip()})
                else:
                    formatted.append({"role": "intervenant", "texte": line})
            return formatted
        return v

class Task3DialecticalCorrection(BaseModel):
    topic_analysis: str = Field(..., description="Analyse du sujet et amorce")
    problematic: str = Field(..., description="Problématique centrale dégagée")
    position_example: str = Field(..., description="Exemple de prise de position nette")
    arguments: List[ArgumentStruct] = Field(..., description="2 à 3 arguments structurés")
    counter_argument: Optional[str] = Field(None, description="Nuance ou contre-argumentation/ouverture")
    conclusion_example: str = Field(..., description="Exemple de conclusion complète")
    useful_expressions: List[str] = Field(..., description="Connecteurs logiques et tournures d'opinion")
    common_mistakes: List[str] = Field(..., description="Erreurs fréquentes à éviter")

    @field_validator("useful_expressions", "common_mistakes", mode="before")
    def validate_lists(cls, v):
        return _coerce_string_to_list(v)

class Task3AnalyticalCorrection(BaseModel):
    topic_analysis: str = Field(..., description="Analyse du sujet et amorce")
    axes_of_development: List[str] = Field(..., description="Axes / Thématiques de développement")
    plan: List[str] = Field(..., description="Annonce des 2 à 3 parties du plan")
    arguments: List[ArgumentStruct] = Field(..., description="Idées principales avec explications")
    examples: List[str] = Field(..., description="Exemples concrets illustratifs")
    conclusion_example: str = Field(..., description="Exemple de conclusion neutre/synthétique")
    useful_expressions: List[str] = Field(..., description="Connecteurs de structuration et de progression")
    common_mistakes: List[str] = Field(..., description="Erreurs fréquentes à éviter")

    @field_validator("axes_of_development", "plan", "examples", "useful_expressions", "common_mistakes", mode="before")
    def validate_lists(cls, v):
        return _coerce_string_to_list(v)

# ------------------------------------------------------------------------------
# 4. GLOBAL RESPONSE CONTAINERS
# ------------------------------------------------------------------------------

class OralTopicCorrectionItem(BaseModel):
    topic_id: str
    task_type: OralTaskType
    task3_type: Optional[Task3Subtype] = None
    correction: Union[Task2Correction, Task3DialecticalCorrection, Task3AnalyticalCorrection]

class BatchOralCorrectionResponse(BaseModel):
    status: str = "success"
    total_processed: int
    corrections: List[OralTopicCorrectionItem]