import os
import json
import asyncio
import time
from datetime import datetime, timezone
from typing import List

from dotenv import load_dotenv
load_dotenv()  # Charge automatiquement les variables du .env

from google import genai
from google.genai import types

from api_app.schemas.oral import (
    OralTopicRequest,
    OralTopicCorrectionItem,
    BatchOralCorrectionResponse,
    OralTaskType,
    Task3Subtype,
    Task2Correction,
    Task3DialecticalCorrection,
    Task3AnalyticalCorrection
)
from api_app.prompts.oral_prompts import (
    PROMPT_SYSTEM_TASK_2,
    PROMPT_SYSTEM_TASK_3_DIALECTICAL,
    PROMPT_SYSTEM_TASK_3_ANALYTICAL
)
from api_app.services.rag_service import RAGService

# Récupération de la limite de concurrence via l'environnement
MAX_CONCURRENT_CALLS = int(os.environ.get("MAX_CONCURRENT_LLM_CALLS", "3"))


def _compter_mots(texte: str) -> int:
    if not texte:
        return 0
    return len(texte.split())


def _clean_schema_for_gemini(pydantic_model) -> dict:
    """
    Génère un dictionnaire JSON Schema à partir d'un modèle Pydantic
    et retire la clé 'additionalProperties' incompatible avec Gemini Developer API.
    """
    if hasattr(pydantic_model, "model_json_schema"):
        schema = pydantic_model.model_json_schema()
    elif isinstance(pydantic_model, dict):
        schema = pydantic_model
    else:
        return pydantic_model

    def _recursive_remove_keys(d):
        if isinstance(d, dict):
            d.pop("additionalProperties", None)
            for key, value in list(d.items()):
                _recursive_remove_keys(value)
        elif isinstance(d, list):
            for item in d:
                _recursive_remove_keys(item)

    _recursive_remove_keys(schema)
    return schema


class LLMService:
    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("LLM_API_KEY")
        if not api_key:
            raise ValueError("❌ GEMINI_API_KEY est introuvable dans les variables d'environnement.")

        # Configuration du client avec l'API v1
        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(api_version="v1")
        )
        
        modele_brut = os.environ.get("LLM_MODEL_NAME", "gemini-3.8-flash")
        self.modele = modele_brut.replace("models/", "").replace("google/", "").strip()

    def _generer_prompt_systeme(self, num_tache: int, bareme_max: int, regles: str, exemples: str) -> str:
        """Génère un prompt système ultra-spécifique avec les exigences du TCF Canada."""
        instructions_tache = ""
        
        if num_tache == 1:
            instructions_tache = """
                CRITÈRES SPÉCIFIQUES - TÂCHE 1 (Récit / Description / Message / Invitation) :
                - Longueur attendue : STRICTEMENT entre 60 et 120 mots maximum.
                - RÈGLE ABSOLUE POUR LA VERSION MODÈLE : La 'version_modele_c2' ne doit JAMAIS dépasser 120 mots (Vise 100 mots).
                - ESPACEMENT & PARAGRAPHES OBLIGATOIRES : Génère obligatoirement des sauts de ligne doubles (\\n\\n) pour séparer distinctement chaque bloc : Salutation, Corps du texte, Formule de politesse et Signature.
                """
        elif num_tache == 2:
            instructions_tache = """
                CRITÈRES SPÉCIFIQUES - TÂCHE 2 (Article / Lettre formelle) :
                - Longueur attendue : STRICTEMENT entre 120 et 150 mots maximum.
                - RÈGLE ABSOLUE POUR LA VERSION MODÈLE : La 'version_modele_c2' ne doit JAMAIS faire moins de 120 mots ni plus de 150 mots.
                - ESPACEMENT & PARAGRAPHES OBLIGATOIRES : Utilise impérativement des sauts de ligne doubles (\\n\\n) entre ton Titre, ton Introduction, ton Développement d'arguments, ta Recommandation et ta Signature. Chaque paragraphe doit être visuellement isolé.
                """
        elif num_tache == 3:
            instructions_tache = """
                CRITÈRES SPÉCIFIQUES - TÂCHE 3 (Synthèse et Argumentation) :
                - Longueur attendue : STRICTEMENT entre 120 et 180 mots maximum.
                - RÈGLE DE COUPE STRATÉGIQUE : La 'version_modele_c2' doit être un modèle de concision. Elle ne doit JAMAIS dépasser 170 mots.
                - ESPACEMENT & PARAGRAPHES OBLIGATOIRES : Structure la 'version_modele_c2' textuelle en utilisant strictly des doubles sauts de ligne (\\n\\n) dans cet ordre précis :
                  * Le Titre (max 9 mots)
                  * [Saut de ligne \\n\\n]
                  * Partie 1 : Résumé neutre et confrontation des points de vue (CIBLE : 45-55 mots).
                  * [Saut de ligne \\n\\n]
                  * Partie 2 : Avis personnel [saut de ligne \\n], argument 1 et exemple illustratif [ saut de ligne\\n], argument 2 illustré. (CIBLE : 60-80 mots).
                  * [Saut de ligne \\n\\n]
                  * Conclusion : Réaffirmation de la position et nuance (CIBLE : 20-30 mots).
                """

        structure_json_tache = {
            "tache": num_tache,
            "consigne": "Répéter ici scrupuleusement la consigne complète du sujet initial fournie.",
            "copie": {"texte_original": "", "nombre_mots": 0},
            "score": {"obtenu": 0.0, "maximum": bareme_max},
            "niveau_estime": {"cecrl": "A1 à C2", "nclc": "3 à 10+"},
            "controle_methodologie": {
                "respect_nombre_mots": True, "structure_attendue": True, "registre_adapte": True,
                "paragraphes": True, "connecteurs": True, "salutation": True, "signature": True,
                "titre": True, "conclusion": True
            },
            "analyse": {
                "comprehension_sujet": {"note": 0.0, "commentaire": ""},
                "respect_methodologie": {"note": 0.0, "commentaire": ""},
                "coherence_cohesion": {"note": 0.0, "commentaire": ""},
                "lexique": {"note": 0.0, "commentaire": ""},
                "grammaire": {"note": 0.0, "commentaire": ""},
                "orthographe": {"note": 0.0, "commentaire": ""}
            },
            "statistiques": {
                "richesse_lexicale": {"score": 0, "niveau": "", "commentaire": ""},
                "complexite_syntaxique": {"score": 0, "niveau": "", "commentaire": ""},
                "fluidite": {"score": 0, "niveau": "", "commentaire": ""}
            },
            "erreurs": [
                {"id": 1, "gravite": "Moyenne", "type": "Grammaire", "segment_original": "", "correction": "", "explication": "", "regle": "", "exemple": ""}
            ],
            "versions": {
                "version_corrigee": "Texte du candidat nettoyé des fautes et respectant la marge des mots (T1: max 120 mots, T2: max 150 mots, T3: max 170 mots).", 
                "version_modele_c2": "RÉDACTION EXEMPLE C2 EXTRÊMEMENT CONCISE (T1: max 120 mots, T2: max 150 mots, T3: max 170 mots). Sépare chaque paragraphe par un double saut de ligne \\n\\n."
            },
            "coaching": {"points_forts": [], "points_a_ameliorer": [], "conseils": [], "objective_prochaine_copie": ""}
        }

        prompt = f"""Tu es un examinateur officiel intransigeant du TCF Canada pour France Éducation International (FEI).
            Évalue la production écrite de la Tâche {num_tache} avec la plus grande rigueur professionnelle.

            La note maximale absolue pour cette tâche est de {bareme_max} points. Tu dois ventiler les sous-notes de l'évaluation ('analyse') de manière à ce que leur somme soit strictly égale à la note obtenue.

            {instructions_tache}

            Règles méthodologiques issues de la base de connaissances (RAG) :
            ATTENTION : La version_modele_c2 doit IMPÉRATIVEMENT respecter les limites de mots de l'épreuve du TCF. Pour la Tâche 1 : 60-120 mots. Pour la Tâche 2 : 120-150 mots. Pour la Tâche 3 : 120-180 mots.
            Tout texte dépassant ces limites ou omettant les doubles sauts de ligne (\\n\\n) entre les paragraphes sera considéré comme méthodologiquement faux.
            {regles}

            Exemples de copies de référence :
            {exemples}

            Consigne de rigueur pour les erreurs :
            Sois très précis sur l'extraction des erreurs. Ne liste que les vraies erreurs. S'il n'y a pas d'erreur, renvoie un tableau vide [].
            
            🚨 CONSIGNE DE COMPTAGE INVIOLABLE (VALABLE POUR LA CLÉ 'version_modele_c2') :
            Vise une cible basse. Si la version_modele_c2 de la Tâche 3 s'approche des 180 mots, arrête-toi immédiatement. Supprime les fioritures avant de renvoyer le résultat.
            
            Tu dois retourner obligatoirement un objet JSON valide respectant cette structure exacte :
            {json.dumps(structure_json_tache, ensure_ascii=False)}
            
            Ne réponds jamais par autre chose que le JSON strictly conforme à la structure ci-dessus. Ne réponds pas par du texte libre ou des commentaires en dehors du JSON. Respecte scrupuleusement le fait d'inclure la consigne d'origine complète dans le champ 'consigne'."""
        
        return prompt

    async def _analyser_une_tache(self, num_tache: int, bareme_max: int, donnees_tache, rag_service) -> dict:
        if not donnees_tache or not donnees_tache.texte_candidat:
            return None

        # Récupération du contexte RAG (Qdrant / Embeddings)
        contexte = rag_service.recuperer_contexte(donnees_tache.texte_candidat, num_tache)
        regles_txt = "\n".join([f"- {r}" for r in contexte["regles"]])
        exemples_txt = json.dumps(contexte["exemples"], ensure_ascii=False)

        if num_tache == 3:
            docs = getattr(donnees_tache, "documents_contexte", [])
            doc1 = docs[0] if len(docs) > 0 else ""
            doc2 = docs[1] if len(docs) > 1 else ""
            consigne_complete = (
                f"TITRE : {donnees_tache.consigne_sujet}\n\n"
                f"Document 1 :\n{doc1}\n\n"
                f"Document 2 :\n{doc2}"
            )
        else:
            consigne_complete = donnees_tache.consigne_sujet

        sys_prompt = self._generer_prompt_systeme(num_tache, bareme_max, regles_txt, exemples_txt)
        user_prompt = f"Consigne:\n{consigne_complete}\n\nCopie du candidat:\n{donnees_tache.texte_candidat}"

        # Appel LLM unifié sur Gemini (gemini-3.8-flash)
        response_json = await asyncio.to_thread(
            self._appeler_llm_json,
            system_prompt=sys_prompt,
            user_prompt=user_prompt
        )
        
        # Consolidation des données pour le front-end / retour API
        response_json["copie"]["nombre_mots"] = len(donnees_tache.texte_candidat.split())
        response_json["copie"]["texte_original"] = donnees_tache.texte_candidat
        response_json["consigne"] = consigne_complete
        return response_json
    
    
    def _determiner_niveaux_tcf(self, note_sur_20: float) -> tuple:
        note_arrondie = round(note_sur_20)
        if note_arrondie >= 18: return "C2", "10+", "Excellent"
        elif note_arrondie >= 16: return "C1", "10+", "Très Bien"
        elif note_arrondie >= 14: return "C1", "9", "Bien"
        elif note_arrondie >= 12: return "B2", "8", "Assez Bien"
        elif note_arrondie >= 10: return "B2", "7", "Passable"
        elif note_arrondie >= 7: return "B1", "6", "Médiocre"
        elif note_arrondie == 6: return "B1", "5", "Insuffisant"
        elif note_arrondie >= 4: return "A2", "4", "Très Insuffisant"
        else: return "A1", "3", "A renforcer"

    def _calculer_niveaux_par_tache(self, note_obtenue: float, note_max: int) -> tuple:
        if note_max <= 0: return "A1", "3 ou moins"
        note_sur_20 = (note_obtenue / note_max) * 20
        note_arrondie = round(note_sur_20)
        if note_arrondie >= 18: return "C2", "10+"
        elif note_arrondie >= 16: return "C1", "10+"
        elif note_arrondie >= 14: return "C1", "9"
        elif note_arrondie >= 12: return "B2", "8"
        elif note_arrondie >= 10: return "B2", "7"
        elif note_arrondie >= 7: return "B1", "6"
        elif note_arrondie == 6: return "B1", "5"
        elif note_arrondie >= 4: return "A2", "4"
        else: return "A1", "3"

    async def evaluer_session_complete(self, examen_payload, rag_service) -> dict:
        evaluations_finales = []
        score_total_obtenu = 0.0

        res_t1 = await self._analyser_une_tache(1, 4, examen_payload.tache_1, rag_service)
        if res_t1:
            vrai_cecrl, vrai_nclc = self._calculer_niveaux_par_tache(res_t1["score"]["obtenu"], 4)
            res_t1["niveau_estime"]["cecrl"] = vrai_cecrl
            res_t1["niveau_estime"]["nclc"] = vrai_nclc
            res_t1["consigne"] = examen_payload.tache_1.consigne_sujet
            texte_modele = res_t1.get("versions", {}).get("version_modele_c2", "")
            res_t1["nombre_mots_candidat"] = _compter_mots(examen_payload.tache_1.texte_candidat)
            res_t1["nombre_mots_exemple"] = _compter_mots(texte_modele)
            evaluations_finales.append(res_t1)
            score_total_obtenu += res_t1["score"]["obtenu"]
        else:
            evaluations_finales.append(self._generer_tache_vide(1, 4, examen_payload.tache_1))

        if MAX_CONCURRENT_CALLS == 1:
            await asyncio.sleep(1.0)

        res_t2 = await self._analyser_une_tache(2, 7, examen_payload.tache_2, rag_service)
        if res_t2:
            vrai_cecrl, vrai_nclc = self._calculer_niveaux_par_tache(res_t2["score"]["obtenu"], 7)
            res_t2["niveau_estime"]["cecrl"] = vrai_cecrl
            res_t2["niveau_estime"]["nclc"] = vrai_nclc
            res_t2["consigne"] = examen_payload.tache_2.consigne_sujet
            texte_modele = res_t2.get("versions", {}).get("version_modele_c2", "")
            res_t2["nombre_mots_candidat"] = _compter_mots(examen_payload.tache_2.texte_candidat)
            res_t2["nombre_mots_exemple"] = _compter_mots(texte_modele)
            evaluations_finales.append(res_t2)
            score_total_obtenu += res_t2["score"]["obtenu"]
        else:
            evaluations_finales.append(self._generer_tache_vide(2, 7, examen_payload.tache_2))

        if MAX_CONCURRENT_CALLS == 1:
            await asyncio.sleep(1.0)

        res_t3 = await self._analyser_une_tache(3, 9, examen_payload.tache_3, rag_service)
        if res_t3:
            vrai_cecrl, vrai_nclc = self._calculer_niveaux_par_tache(res_t3["score"]["obtenu"], 9)
            res_t3["niveau_estime"]["cecrl"] = vrai_cecrl
            res_t3["niveau_estime"]["nclc"] = vrai_nclc

            titre = examen_payload.tache_3.consigne_sujet
            docs = getattr(examen_payload.tache_3, "documents_contexte", [])
            doc1 = docs[0] if len(docs) > 0 else ""
            doc2 = docs[1] if len(docs) > 1 else ""
            
            res_t3["consigne"] = f"TITRE : {titre}\n\n{doc1}\n\n{doc2}"
            texte_modele = res_t3.get("versions", {}).get("version_modele_c2", "")
            res_t3["nombre_mots_candidat"] = _compter_mots(examen_payload.tache_3.texte_candidat)
            res_t3["nombre_mots_exemple"] = _compter_mots(texte_modele)
            evaluations_finales.append(res_t3)
            score_total_obtenu += res_t3["score"]["obtenu"]
        else:
            evaluations_finales.append(self._generer_tache_vide(3, 9, examen_payload.tache_3))

        note_sur_20 = round(score_total_obtenu, 2)
        pourcentage = round((note_sur_20 / 20) * 100)
        cecrl, nclc, mention = self._determiner_niveaux_tcf(note_sur_20)

        return {
            "status": "success",
            "meta": {
                "exam": "TCF Canada",
                "epreuve": "Expression écrite",
                "date_evaluation": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "version_analyse": "1.0.0",
                "mode": "evaluation_complete"
            },
            "bilan_global": {
                "score": {
                    "sur_20": note_sur_20,
                    "pourcentage": pourcentage,
                    "mention": mention
                },
                "niveau": {
                    "cecrl": cecrl,
                    "nclc": nclc
                },
                "resume": "Bilan global consolidé basé sur les épreuves soumises.",
                "points_forts": [],
                "priorites_progression": []
            },
            "evaluations": evaluations_finales
        }

    def _generer_tache_vide(self, num_tache: int, max_points: int, payload_tache) -> dict:
        return {
            "tache": num_tache,
            "consigne": payload_tache.consigne_sujet if payload_tache else "",
            "copie": {
                "texte_original": payload_tache.texte_candidat if payload_tache else "",
                "nombre_mots": 0
            },
            "score": {"obtenu": 0.0, "maximum": max_points},
            "niveau_estime": {"cecrl": "A1", "nclc": "3 ou moins"},
            "controle_methodologie": {
                "respect_nombre_mots": False, "structure_attendue": False, "registre_adapte": False,
                "paragraphes": False, "connecteurs": False, "salutation": False, "signature": False,
                "titre": False, "conclusion": False
            },
            "analyse": {},
            "statistiques": {},
            "erreurs": [],
            "versions": {"version_corrigee": "", "version_modele_c2": ""},
            "coaching": {"points_forts": [], "points_a_ameliorer": ["Tâche non traitée."], "conseils": [], "objective_prochaine_copie": ""}
        }

    async def generer_corrections_orales_batch(
        self, 
        topics: List[OralTopicRequest], 
        rag_service: RAGService
    ) -> BatchOralCorrectionResponse:
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_CALLS)

        async def _traiter_avec_limite(topic: OralTopicRequest):
            async with semaphore:
                res = await self._traiter_un_sujet_oral(topic, rag_service)
                if MAX_CONCURRENT_CALLS == 1:
                    await asyncio.sleep(1.0)
                return res

        tasks = [_traiter_avec_limite(topic) for topic in topics]
        corrections = await asyncio.gather(*tasks)

        return BatchOralCorrectionResponse(
            status="success",
            total_processed=len(corrections),
            corrections=corrections
        )

    async def _traiter_un_sujet_oral(
        self, 
        topic: OralTopicRequest, 
        rag_service: RAGService
    ) -> OralTopicCorrectionItem:
        context_rag = rag_service.recuperer_contexte_oral(
            content_sujet=topic.content,
            task_type=topic.task_type.value,
            task3_type=topic.task3_type.value if topic.task3_type else None
        )
        context_str = "\n---\n".join(context_rag) if context_rag else "Aucun contexte spécifique trouvé."

        system_prompt, response_schema = self._obtenir_config_prompt_oral(topic)

        user_prompt = f"""
            CONTEXTE MÉTHODOLOGIQUE (RAG) :
            {context_str}

            SUJET À TRAITER :
            Tâche : {topic.task_type.value}
            Subtype Tâche 3 : {topic.task3_type.value if topic.task3_type else 'N/A'}
            Consigne : {topic.content}

            Génère la fiche de correction au format JSON strict en respectant le schéma attendu.
            """

        response_json = await asyncio.to_thread(
            self._appeler_llm_json,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=response_schema
        )

        correction_data = response_schema.model_validate(response_json)

        return OralTopicCorrectionItem(
            topic_id=topic.id,
            task_type=topic.task_type,
            task3_type=topic.task3_type,
            correction=correction_data
        )

    def _obtenir_config_prompt_oral(self, topic: OralTopicRequest):
        if topic.task_type == OralTaskType.TASK_2:
            return PROMPT_SYSTEM_TASK_2, Task2Correction
        elif topic.task_type == OralTaskType.TASK_3:
            if topic.task3_type == Task3Subtype.DIALECTICAL:
                return PROMPT_SYSTEM_TASK_3_DIALECTICAL, Task3DialecticalCorrection
            elif topic.task3_type == Task3Subtype.ANALYTICAL:
                return PROMPT_SYSTEM_TASK_3_ANALYTICAL, Task3AnalyticalCorrection
            else:
                raise ValueError("Le sous-type pour la Tâche 3 doit être DIALECTICAL ou ANALYTICAL.")
        else:
            raise ValueError(f"Type de tâche non supporté : {topic.task_type}")

    def _appeler_llm_json(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        response_schema = None,
        max_retries: int = 3
    ) -> dict:
        config_args = {
            "system_instruction": system_prompt,
            "response_mime_type": "application/json",
            "temperature": 0.0
        }
        
        if response_schema:
            cleaned_schema = _clean_schema_for_gemini(response_schema)
            config_args["response_schema"] = cleaned_schema

        config = types.GenerateContentConfig(**config_args)
        
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.modele,
                    contents=user_prompt,
                    config=config
                )
                return json.loads(response.text)
            except Exception as e:
                msg_erreur = str(e)
                if ("429" in msg_erreur or "503" in msg_erreur) and attempt < max_retries - 1:
                    temps_attente = 2 * (2 ** attempt)
                    print(f"[⚠️ Erreur Gemini Temporelle] Réessai dans {temps_attente}s...")
                    time.sleep(temps_attente)
                else:
                    print(f"[❌ Erreur Gemini] Échec sur le modèle '{self.modele}' : {msg_erreur}")
                    raise e