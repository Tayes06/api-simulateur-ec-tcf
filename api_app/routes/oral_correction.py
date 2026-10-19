# api_app/routes/oral_correction.py
from fastapi import APIRouter, Depends, HTTPException, status

from api_app.core.security import verifier_cle_api
from api_app.schemas.oral import (
    BatchOralTopicRequest,
    BatchOralCorrectionResponse,
    OralTopicRequest,
    OralTopicCorrectionItem
)
from api_app.services.rag_service import RAGService
from api_app.services.llm_service import LLMService

router = APIRouter(prefix="/oral", tags=["Expression Orale"])

def get_rag_service():
    return RAGService()

def get_llm_service():
    return LLMService()

@router.post(
    "/generate-corrections",
    response_model=BatchOralCorrectionResponse,
    dependencies=[Depends(verifier_cle_api)]
)
async def generate_oral_corrections(
    payload: BatchOralTopicRequest,
    rag_service: RAGService = Depends(get_rag_service),
    llm_service: LLMService = Depends(get_llm_service)
):
    """
    Génère les fiches de correction pédagogique en batch pour une liste de sujets d'Expression Orale.
    """
    try:
        # generer_corrections_orales_batch renvoie déjà un BatchOralCorrectionResponse
        batch_response = await llm_service.generer_corrections_orales_batch(payload.topics, rag_service)
        return batch_response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la génération des corrections d'expression orale : {str(e)}"
        )

@router.post(
    "/regenerate-correction",
    response_model=OralTopicCorrectionItem,
    dependencies=[Depends(verifier_cle_api)]
)
async def regenerate_oral_correction(
    topic: OralTopicRequest,
    rag_service: RAGService = Depends(get_rag_service),
    llm_service: LLMService = Depends(get_llm_service)
):
    """
    Régénère la fiche de correction pour un seul sujet d'Expression Orale.
    """
    try:
        batch_response = await llm_service.generer_corrections_orales_batch([topic], rag_service)
        if not batch_response or not batch_response.corrections:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Échec de la régénération du sujet."
            )
        return batch_response.corrections[0]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la régénération : {str(e)}"
        )