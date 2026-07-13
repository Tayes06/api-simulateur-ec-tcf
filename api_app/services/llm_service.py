import os
import json
import asyncio
from datetime import datetime, timezone
from mistralai.client import Mistral


def _compter_mots(texte: str) -> int:
    if not texte:
        return 0
    return len(texte.split())


class LLMService:
    def __init__(self):
        # Utilisation du client asynchrone pour les performances
        self.client = Mistral(api_key=os.environ.get("MISTRAL_API_KEY"))
        self.modele = "mistral-large-latest"

    def _generer_prompt_systeme(self, num_tache: int, bareme_max: int, regles: str, exemples: str) -> str:
        """Génère un prompt système ultra-spécifique avec les exigences du TCF Canada."""
        
        # 1. Définition des briques d'instructions spécifiques et de l'espacement
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
                - ESPACEMENT & PARAGRAPHES OBLIGATOIRES : Structure la 'version_modele_c2' textuelle en utilisant strictement des doubles sauts de ligne (\\n\\n) dans cet ordre précis :
                  * Le Titre (max 9 mots)
                  * [Saut de ligne \\n\\n]
                  * Partie 1 : Résumé neutre et confrontation des points de vue (CIBLE : 45-55 mots).
                  * [Saut de ligne \\n\\n]
                  * Partie 2 : Avis personnel [saut de ligne \\n], argument 1 et exemple illustratif [ saut de ligne\\n], argument 2 illustré. (CIBLE : 60-80 mots).
                  * [Saut de ligne \\n\\n]
                  * Conclusion : Réaffirmation de la position et nuance (CIBLE : 20-30 mots).
                """

        # 2. Structure JSON attendue (Nettoyée pour éviter les biais de génération)
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
                "version_corrigee": "Texte du candidat nettoyé des fautes.", 
                "version_modele_c2": "RÉDACTION EXEMPLE C2 EXTRÊMEMENT CONCISE (T1: max 120 mots, T2: max 150 mots, T3: max 170 mots). Sépare chaque paragraphe par un double saut de ligne \\n\\n."
            },
            "coaching": {"points_forts": [], "points_a_ameliorer": [], "conseils": [], "objective_prochaine_copie": ""}
        }

        # 3. Assemblage du Prompt Master
        prompt = f"""Tu es un examinateur officiel intransigeant du TCF Canada pour France Éducation International (FEI).
            Évalue la production écrite de la Tâche {num_tache} avec la plus grande rigueur professionnelle.

            La note maximale absolue pour cette tâche est de {bareme_max} points. Tu dois ventiler les sous-notes de l'évaluation ('analyse') de manière à ce que leur somme soit strictement égale à la note obtenue.

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
            
            Ne réponds jamais par autre chose que le JSON strictement conforme à la structure ci-dessus. Ne réponds pas par du texte libre ou des commentaires en dehors du JSON. Respecte scrupuleusement le fait d'inclure la consigne d'origine complète dans le champ 'consigne'."""
        
        return prompt

    async def _analyser_une_tache(self, num_tache: int, bareme_max: int, donnees_tache, rag_service) -> dict:
        """Gère l'analyse asynchrone d'une seule tâche (RAG + Appel Mistral)."""
        if not donnees_tache or not donnees_tache.texte_candidat:
            return None

        # 1. RAG
        contexte = rag_service.recuperer_contexte(donnees_tache.texte_candidat, num_tache)
        regles_txt = "\n".join([f"- {r}" for r in contexte["regles"]])
        exemples_txt = json.dumps(contexte["exemples"], ensure_ascii=False)

        # 2. Construction dynamique de la consigne complète passée au LLM pour la Tâche 3
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

        # 3. Prompts
        sys_prompt = self._generer_prompt_systeme(num_tache, bareme_max, regles_txt, exemples_txt)
        user_prompt = f"Consigne:\n{consigne_complete}\n\nCopie du candidat:\n{donnees_tache.texte_candidat}"

        # 4. Appel API via le client asynchrone de Mistral
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: self.client.chat.complete(
                model=self.modele,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
            )
        )
        
        res_dict = json.loads(response.choices[0].message.content)
        # Forcer l'injection des valeurs réelles mesurées côté backend pour plus de précision
        res_dict["copie"]["nombre_mots"] = len(donnees_tache.texte_candidat.split())
        res_dict["copie"]["texte_original"] = donnees_tache.texte_candidat
        res_dict["consigne"] = consigne_complete
        return res_dict

    def _determiner_niveaux_tcf(self, note_sur_20: float) -> tuple:
        """Applique strictement la grille de correspondance pour l'Expression Écrite."""
        note_arrondie = round(note_sur_20)

        if note_arrondie >= 18:
            return "C2", "10+", "Excellent"
        elif note_arrondie >= 16:
            return "C1", "10+", "Très Bien"
        elif note_arrondie >= 14:
            return "C1", "9", "Bien"
        elif note_arrondie >= 12:
            return "B2", "8", "Assez Bien"
        elif note_arrondie >= 10:
            return "B2", "7", "Passable"
        elif note_arrondie >= 7:
            return "B1", "6", "Médiocre"
        elif note_arrondie == 6:
            return "B1", "5", "Insuffisant"
        elif note_arrondie >= 4:
            return "A2", "4", "Très Insuffisant"
        else:
            return "A1", "3", "A renforcer"

    def _calculer_niveaux_par_tache(self, note_obtenue: float, note_max: int) -> tuple:
        """Ramène proportionnellement la note d'une tâche sur 20 pour en déduire le niveau."""
        if note_max <= 0:
            return "A1", "3 ou moins"
            
        note_sur_20 = (note_obtenue / note_max) * 20
        note_arrondie = round(note_sur_20)

        if note_arrondie >= 18:
            return "C2", "10+"
        elif note_arrondie >= 16:
            return "C1", "10+"
        elif note_arrondie >= 14:
            return "C1", "9"
        elif note_arrondie >= 12:
            return "B2", "8"
        elif note_arrondie >= 10:
            return "B2", "7"
        elif note_arrondie >= 7:
            return "B1", "6"
        elif note_arrondie == 6:
            return "B1", "5"
        elif note_arrondie >= 4:
            return "A2", "4"
        else:
            return "A1", "3"

    async def evaluer_session_complete(self, examen_payload, rag_service) -> dict:
        """Orchestre l'évaluation et calcule le bilan global final."""
        
        # 1. Lancement des tâches en parallèle
        taches_tasks = [
            self._analyser_une_tache(1, 4, examen_payload.tache_1, rag_service),
            self._analyser_une_tache(2, 7, examen_payload.tache_2, rag_service),
            self._analyser_une_tache(3, 9, examen_payload.tache_3, rag_service)
        ]
        
        resultats = await asyncio.gather(*taches_tasks)
        evaluations_finales = []
        score_total_obtenu = 0.0

        # 2. Traitement des résultats (injection de 0 si la tâche est nulle + correction des paliers)
        # Tâche 1 (Sur 4)
        if resultats[0]:
            vrai_cecrl, vrai_nclc = self._calculer_niveaux_par_tache(resultats[0]["score"]["obtenu"], 4)
            resultats[0]["niveau_estime"]["cecrl"] = vrai_cecrl
            resultats[0]["niveau_estime"]["nclc"] = vrai_nclc
            
            resultats[0]["consigne"] = examen_payload.tache_1.consigne_sujet
            
            versions = resultats[0].get("versions", {})
            texte_modele = versions.get("version_modele_c2", "") # Extraction C2 corrigée
            
            resultats[0]["nombre_mots_candidat"] = _compter_mots(examen_payload.tache_1.texte_candidat)
            resultats[0]["nombre_mots_exemple"] = _compter_mots(texte_modele)
            
            evaluations_finales.append(resultats[0])
            score_total_obtenu += resultats[0]["score"]["obtenu"]
        else:
            evaluations_finales.append(self._generer_tache_vide(1, 4, examen_payload.tache_1))

        # Tâche 2 (Sur 7)
        if resultats[1]:
            vrai_cecrl, vrai_nclc = self._calculer_niveaux_par_tache(resultats[1]["score"]["obtenu"], 7)
            resultats[1]["niveau_estime"]["cecrl"] = vrai_cecrl
            resultats[1]["niveau_estime"]["nclc"] = vrai_nclc
            
            resultats[1]["consigne"] = examen_payload.tache_2.consigne_sujet
            
            versions = resultats[1].get("versions", {})
            texte_modele = versions.get("version_modele_c2", "") # Extraction C2 corrigée
            
            resultats[1]["nombre_mots_candidat"] = _compter_mots(examen_payload.tache_2.texte_candidat)
            resultats[1]["nombre_mots_exemple"] = _compter_mots(texte_modele)
            
            evaluations_finales.append(resultats[1])
            score_total_obtenu += resultats[1]["score"]["obtenu"]
        else:
            evaluations_finales.append(self._generer_tache_vide(2, 7, examen_payload.tache_2))

        # Tâche 3 (Sur 9)
        if resultats[2]:
            vrai_cecrl, vrai_nclc = self._calculer_niveaux_par_tache(resultats[2]["score"]["obtenu"], 9)
            resultats[2]["niveau_estime"]["cecrl"] = vrai_cecrl
            resultats[2]["niveau_estime"]["nclc"] = vrai_nclc

            # 🛠️ RECONSTRUCTION ET SÉCURISATION DU BLOC DE SORTIE DE LA CONSIGNE TÂCHE 3
            titre = examen_payload.tache_3.consigne_sujet
            docs = getattr(examen_payload.tache_3, "documents_contexte", [])
            doc1 = docs[0] if len(docs) > 0 else ""
            doc2 = docs[1] if len(docs) > 1 else ""
            
            # Formatage propre multi-ligne pour l'affichage final
            resultats[2]["consigne"] = (
                f"TITRE : {titre}\n\n"
                f"{doc1}\n\n"
                f"{doc2}"
            )
            
            versions = resultats[2].get("versions", {})
            texte_modele = versions.get("version_modele_c2", "") # Extraction C2 corrigée
            
            resultats[2]["nombre_mots_candidat"] = _compter_mots(examen_payload.tache_3.texte_candidat)
            resultats[2]["nombre_mots_exemple"] = _compter_mots(texte_modele)
            
            evaluations_finales.append(resultats[2])
            score_total_obtenu += resultats[2]["score"]["obtenu"]
        else:
            evaluations_finales.append(self._generer_tache_vide(3, 9, examen_payload.tache_3))

        # 3. Calculs globaux immuables sur 20
        note_sur_20 = round(score_total_obtenu, 2)
        pourcentage = round((note_sur_20 / 20) * 100)
        
        cecrl, nclc, mention = self._determiner_niveaux_tcf(note_sur_20)

        # 4. Construction du contrat de sortie
        payload_sortie = {
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
        
        return payload_sortie

    def _generer_tache_vide(self, num_tache: int, max_points: int, payload_tache) -> dict:
        """Génère un bloc d'évaluation à zéro pour une tâche non fournie ou vide."""
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
            "versions": {"version_corrigee": "", "version_modele_c2": ""}, # Corrigé ici aussi
            "coaching": {"points_forts": [], "points_a_ameliorer": ["Tâche non traitée."], "conseils": [], "objective_prochaine_copie": ""}
        }