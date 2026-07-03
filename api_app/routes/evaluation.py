from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from fastapi.security import OAuth2PasswordBearer

from api_app.services.rag_service import RAGService
from api_app.services.llm_service import LLMService
from api_app.core.security import verifier_cle_api  # Import de tes constantes de sécurité

router = APIRouter(prefix="/tcf", tags=["Evaluation TCF"])

# --- SCHÉMAS DE DONNÉES ENTRANTES (PAYLOAD) ---

class TachePayload(BaseModel):
    consigne_sujet: str = Field(..., description="La consigne de l'exercice")
    texte_candidat: str = Field(..., description="La production écrite de l'élève")
    documents_contexte: Optional[List[str]] = Field(default=[], description="Uniquement pour la Tâche 3")

class TCFExamenRequest(BaseModel):
    tache_1: Optional[TachePayload] = None
    tache_2: Optional[TachePayload] = None
    tache_3: Optional[TachePayload] = None


# --- SCHÉMAS DE DONNÉES SORTANTES (RÉPONSE) ---

class ScoreGlobal(BaseModel):
    sur_20: float
    pourcentage: int
    mention: str

class NiveauGlobal(BaseModel):
    cecrl: str
    nclc: str

class BilanGlobalResponse(BaseModel):
    score: ScoreGlobal
    niveau: NiveauGlobal
    resume: str
    points_forts: List[str] = []
    priorites_progression: List[str] = []

class MetaResponse(BaseModel):
    exam: str
    epreuve: str
    date_evaluation: str
    version_analyse: str
    mode: str

# Ce modèle valide désormais la structure exacte générée par ton service
class TCFEvaluationGlobaleResponse(BaseModel):
    status: str
    meta: MetaResponse
    bilan_global: BilanGlobalResponse
    evaluations: List[Optional[Dict[str, Any]]] = Field(
        ..., 
        description="Liste contenant les analyses détaillées enrichies du nombre de mots pour chaque tâche"
    )


# --- GESTION DES DÉPENDANCES ---

def get_rag_service():
    return RAGService()

def get_llm_service():
    return LLMService()

# Configuration du schéma OAuth2 pour repérer le Token dans l'en-tête Authorization
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


# --- ENDPOINT SÉCURISÉ ---

@router.post("/evaluation-complete", response_model=TCFEvaluationGlobaleResponse)
async def evaluer_examen_complet(
    payload: TCFExamenRequest,
    rag_service: RAGService = Depends(get_rag_service),
    llm_service: LLMService = Depends(get_llm_service),
    current_user: str = Depends(verifier_cle_api)  # 🔒 Sécurisation par clé API
):
    try:
        # L'orchestration globale s'exécute, injecte le compte de mots et conserve l'ancien format
        resultat = await llm_service.evaluer_session_complete(payload, rag_service)
        return resultat
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))