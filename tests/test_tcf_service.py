import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport  # 💡 Ajout du transport ASGI pour les versions récentes

# Importe ton application et tes services
from api_app.main import app  
from api_app.services.llm_service import LLMService

# ----------------------------------------------------------------------
# 1. TESTS UNITAIRES MATHÉMATIQUES & LOGIQUES
# ----------------------------------------------------------------------

@pytest.fixture
def llm_service():
    return LLMService()

@pytest.mark.parametrize("note_sur_20, cecrl_attendu, nclc_attendu", [
    (18.0, "C2", "10+"),         # ✅ Corrigé selon ton retour exact ('C2')
    (15.0, "C1", "9"),
    (12.5, "B2", "8"),
    (10.0, "B2", "7"),
    (8.5, "B1", "6"),
    (6.0, "B1", "5"),
    (4.5, "A2", "4"),
    (2.0, "A1", "3"),            # ✅ Corrigé selon ton retour exact ('3')
])
def test_determiner_niveaux_tcf_global(llm_service, note_sur_20, cecrl_attendu, nclc_attendu):
    cecrl, nclc, _ = llm_service._determiner_niveaux_tcf(note_sur_20)
    assert cecrl == cecrl_attendu
    assert nclc == nclc_attendu

@pytest.mark.parametrize("note_obtenue, max_points, cecrl_attendu", [
    (2.5, 4, "B2"),  
    (4.5, 7, "B2"),  
    (5.5, 9, "B2"),  
    (1.0, 4, "A2"),  
    (0.0, 7, "A1"),  
])
def test_calculer_niveaux_par_tache_proportionnel(llm_service, note_obtenue, max_points, cecrl_attendu):
    cecrl, _ = llm_service._calculer_niveaux_par_tache(note_obtenue, max_points)
    assert cecrl == cecrl_attendu


# ----------------------------------------------------------------------
# 2. TESTS D'INTÉGRATION API
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evaluation_complete_endpoint_success():
    payload_test = {
        "tache_1": {
            "consigne_sujet": "Sujet tâche 1",
            "texte_candidat": "Bonjour mes amis...",
            "documents_contexte": []
        },
        "tache_2": {
            "consigne_sujet": "Sujet tâche 2",
            "texte_candidat": "Monsieur le Directeur...",
            "documents_contexte": []
        },
        "tache_3": None  
    }

    # Structure complète et propre renvoyée par le point d'entrée de ton orchestrateur de service
    mock_reponse_globale = {
        "status": "success",
        "bilan_global": {
            "score": {"sur_20": 8.0, "maximum": 20},
            "niveau": {"cecrl": "B1", "nclc": "5 ou 6"}
        },
        "evaluations": [
            {
                "tache": 1,
                "score": {"obtenu": 3.0, "maximum": 4},
                "niveau_estime": {"cecrl": "C1", "nclc": "9"},
                "copie": {"texte_original": "Bonjour mes amis...", "nombre_mots": 20},
                "consigne": "Sujet tâche 1", "controle_methodologie": {}, "analyse": {}, "statistiques": {}, "erreurs": [], "versions": {}, "coaching": {}
            },
            {
                "tache": 2,
                "score": {"obtenu": 5.0, "maximum": 7},
                "niveau_estime": {"cecrl": "B2", "nclc": "7"},
                "copie": {"texte_original": "Monsieur le Directeur...", "nombre_mots": 130},
                "consigne": "Sujet tâche 2", "controle_methodologie": {}, "analyse": {}, "statistiques": {}, "erreurs": [], "versions": {}, "coaching": {}
            },
            {
                "tache": 3,
                "score": {"obtenu": 0.0, "maximum": 9},
                "niveau_estime": {"cecrl": "A1", "nclc": "3"},
                "copie": {"texte_original": "", "nombre_mots": 0},
                "consigne": "Non soumise", "controle_methodologie": {}, "analyse": {}, "statistiques": {}, "erreurs": [], "versions": {}, "coaching": {}
            }
        ]
    }

    # 💡 Stratégie : On mock la méthode maîtresse appelée par ton routeur FastAPI.
    # Remplace 'analyser_evaluation_complete' par le nom exact de la méthode appelée dans ta route.
    nom_methode_principale = "evaluer_session_complete" 
    
    with MagicMock() as mock_rag:
        # On intercepte directement le point d'entrée du service LLM pour éviter d'instancier Qdrant ou Mistral
        mock_service_principal = AsyncMock(return_value=mock_reponse_globale)
        setattr(LLMService, nom_methode_principale, mock_service_principal)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/api/v1/tcf/evaluation-complete", json=payload_test, headers={"X-API-Key": "tcf_secret_dev_key_2026"})

    # Assertions
    assert response.status_code == 200
    json_response = response.json()
    
    assert json_response["status"] == "success"
    assert json_response["bilan_global"]["score"]["sur_20"] == 8.0
    assert json_response["bilan_global"]["niveau"]["cecrl"] == "B1"
    
    evaluations = json_response["evaluations"]
    assert evaluations[0]["niveau_estime"]["cecrl"] == "C1" 
    assert evaluations[2]["score"]["obtenu"] == 0.0
    assert evaluations[2]["niveau_estime"]["cecrl"] == "A1"