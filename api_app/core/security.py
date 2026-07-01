import os
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

# On définit le nom de l'en-tête HTTP que ton frontend React va envoyer
API_KEY_NAME = "X-API-Key"

# FastAPI va chercher automatiquement cet en-tête dans les requêtes
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def verifier_cle_api(api_key: str = Security(api_key_header)):
    # On récupère la clé attendue définie dans le fichier .env
    cle_attendue = os.getenv("TCF_API_KEY", "cle_par_defaut_si_vide")
    
    # On compare la clé reçue avec celle du .env
    if not api_key or api_key != cle_attendue:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé : Clé d'API invalide ou manquante dans l'en-tête X-API-Key"
        )
    
    return "application_react"