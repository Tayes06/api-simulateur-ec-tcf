from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from typing import List, Optional
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from api_app.services.rag_service import RAGService
from api_app.services.llm_service import LLMService
from api_app.core.security import verifier_cle_api  # Import de tes constantes de sécurité

router = APIRouter(prefix="/tcf", tags=["Evaluation TCF"])

# --- SCHÉMAS DE DONNÉES (PYDANTIC) ---

class TachePayload(BaseModel):
    consigne_sujet: str = Field(..., description="La consigne de l'exercice")
    texte_candidat: str = Field(..., description="La production écrite de l'élève")
    documents_contexte: Optional[List[str]] = Field(default=[], description="Uniquement pour la Tâche 3")

class TCFExamenRequest(BaseModel):
    tache_1: Optional[TachePayload] = None
    tache_2: Optional[TachePayload] = None
    tache_3: Optional[TachePayload] = None


# --- GESTION DES DÉPENDANCES ---

def get_rag_service():
    return RAGService()

def get_llm_service():
    return LLMService()

# Configuration du schéma OAuth2 pour repérer le Token dans l'en-tête Authorization
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


# --- ENDPOINT SÉCURISÉ ---

@router.post("/evaluation-complete")
async def evaluer_examen_complet(
    payload: TCFExamenRequest,
    rag_service: RAGService = Depends(get_rag_service),
    llm_service: LLMService = Depends(get_llm_service),
    current_user: str = Depends(verifier_cle_api)  # 🔒 Sécurisation par clé API
):
    try:
        # L'orchestration globale et parallèle s'exécute uniquement si la clé est valide
        resultat = await llm_service.evaluer_session_complete(payload, rag_service)
        return resultat
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))