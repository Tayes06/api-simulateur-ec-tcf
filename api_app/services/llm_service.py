import os
import json
import asyncio
from datetime import datetime, timezone
from mistralai.client import Mistral

class LLMService:
    def __init__(self):
        # Utilisation du client asynchrone pour les performances
        self.client = Mistral(api_key=os.environ.get("MISTRAL_API_KEY"))
        self.modele = "mistral-large-latest"

    def _generer_prompt_systeme(self, num_tache: int, bareme_max: int, regles: str, exemples: str) -> str:
        """Génère un prompt système ultra-spécifique avec les exigences du TCF Canada."""
        
        # 1. Définition des briques d'instructions spécifiques
        instructions_tache = ""
        
        if num_tache == 1:
            instructions_tache = """
                CRITÈRES SPÉCIFIQUES - TÂCHE 1 (Récit / Description) :
                - Longueur attendue : 60 à 120 mots. Si la copie fait moins de 60 mots, pénalise sévèrement le critère 'respect_methodologie'.
                - Format obligatoire : Lettre, message ou courriel amical/familier.
                - Éléments requis : Une salutation initiale amicale (ex: 'Chers amis,', 'Bonjour Paul,'), une formule de prise de congé ou conclusion chaleureuse, et une signature (un prénom).
                - Contenu : Le candidat doit décrire une situation, raconter un événement ou inviter ses proches en donnant des détails concrets (lieux, data, impressions).
                """
        elif num_tache == 2:
            instructions_tache = """
                CRITÈRES SPÉCIFIQUES - TÂCHE 2 (Article / Lettre formelle) :
                - Longueur attendue : 120 à 150 mots. Si en dehors des clous, pénalise le 'respect_methodologie'.
                - Format obligatoire : Article de journal, contribution à un blog ou lettre formelle / témoignage destiné à un public large.
                - Éléments requis : Structure claire avec des paragraphes bien distincts. Titre, Introduction du sujet, développement des arguments, conclusion textuelle, recommandation et signature (prenom).
                - Contenu : Rendre compte d'une expérience et exprimer des arguments clairs pour justifier une décision (ex: raisons de l'arrêt des réseaux sociaux). Présence obligatoire de connecteurs de cause, conséquence ou opposition (En effet, Par conséquent, Cependant, etc.).
                """
        elif num_tache == 3:
            instructions_tache = """
                CRITÈRES SPÉCIFIQUES - TÂCHE 3 (Synthèse et Argumentation) :
                - Longueur attendue : 120 à 180 mots. Si < 120 mots ou > 180 mots, la notation doit être très sévère.
                - Format obligatoire : Un titre, un texte argumentatif en deux parties distinctes et équilibrées.
                - Partie 1 (Confrontation) : Le candidat doit impérativement résumer et confronter les points de vue des documents fournis (ou du sujet) de manière NEUTRE, sans donner son avis personnel immédiatement. Utilisation de structures de comparaison (D'une part / d'autre part, Tandis que, En revanche).
                - Partie 2 (Opinion personnelle) : Le candidat donne son avis propre sur le débat, étayé par un ou deux arguments solides et un exemple.
                - Éléments requis : Titre, introduction générale (De nos jours...), transition fluide entre la synthèse et l'avis personnel, conclusion claire.
                """

        # 2. Structure JSON attendue (inchangée pour préserver ton contrat d'interface)
        structure_json_tache = {
            "tache": num_tache,
            "consigne": "Répéter la consigne",
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
            "versions": {"version_corrigee": "", "version_modele_c1": ""},
            "coaching": {"points_forts": [], "points_a_ameliorer": [], "conseils": [], "objectif_prochaine_copie": ""}
        }

        # 3. Assemblage du Prompt Master
        prompt = f"""Tu es un examinateur officiel intransigeant du TCF Canada pour France Éducation International (FEI).
            Évalue la production écrite de la Tâche {num_tache} avec la plus grande rigueur professionnelle.

            La note maximale absolue pour cette tâche est de {bareme_max} points. Tu dois ventiler les sous-notes de l'évaluation ('analyse') de manière à ce que leur somme soit strictement égale à la note obtenue.

            {instructions_tache}

            Règles méthodologiques issues de la base de connaissances (RAG) :
            {regles}

            Exemples de copies de référence :
            {exemples}

            Consigne de rigueur pour les erreurs :
            Sois très précis sur l'extraction des erreurs. Ne liste que les vraies erreurs (orthographe, grammaire, ponctuation importante, contresens). S'il n'y a pas d'erreur, renvoie un tableau vide [].

            Tu dois retourner obligatoirement un objet JSON valide respectant cette structure exacte :
            {json.dumps(structure_json_tache, ensure_ascii=False)}"""
        
        return prompt

    async def _analyser_une_tache(self, num_tache: int, bareme_max: int, donnees_tache, rag_service) -> dict:
        """Gère l'analyse asynchrone d'une seule tâche (RAG + Appel Mistral)."""
        if not donnees_tache or not donnees_tache.texte_candidat:
            return None

        # 1. RAG
        contexte = rag_service.recuperer_contexte(donnees_tache.texte_candidat, num_tache)
        regles_txt = "\n".join([f"- {r}" for r in contexte["regles"]])
        exemples_txt = json.dumps(contexte["exemples"], ensure_ascii=False)

        # 2. Prompts
        sys_prompt = self._generer_prompt_systeme(num_tache, bareme_max, regles_txt, exemples_txt)
        user_prompt = f"Consigne: {donnees_tache.consigne_sujet}\n\nCopie du candidat:\n{donnees_tache.texte_candidat}"

        # 3. Appel API via le client asynchrone de Mistral
        # Note : On utilise 'chat.complete_async' si disponible ou on l'exécute dans un thread pour ne pas bloquer la boucle
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
        res_dict["consigne"] = donnees_tache.consigne_sujet
        return res_dict

    def _determiner_niveaux_tcf(self, note_sur_20: float) -> tuple:
        """
        Applique strictement la grille de correspondance de l'image_9db4cb.png
        pour l'Expression Écrite.
        """
        # Arrondi standard pour correspondre aux entiers de la grille si nécessaire
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
            return "B1", "5", "Insuffisat"
        elif note_arrondie >= 4:
            return "A2", "4", "Très Insuffisant"
        else:
            return "A1", "3", "A renforcer"

    def _calculer_niveaux_par_tache(self, note_obtenue: float, note_max: int) -> tuple:
        """
        Ramène proportionnellement la note d'une tâche sur 20 
        pour en déduire le niveau exact selon la grille officielle du TCF.
        """
        if note_max <= 0:
            return "A1", "3 ou moins"
            
        # Projection mathématique sur 20
        note_sur_20 = (note_obtenue / note_max) * 20
        note_arrondie = round(note_sur_20)

        # Application stricte de la grille Expression Écrite (image_9db4cb.png)
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
        """Orchestre l'évaluation et calcule le bilan global final basé sur l'image_9db4cb.png"""
        
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
            # Alignement forcé du niveau de la tâche basé sur son score réel
            vrai_cecrl, vrai_nclc = self._calculer_niveaux_par_tache(resultats[0]["score"]["obtenu"], 4)
            resultats[0]["niveau_estime"]["cecrl"] = vrai_cecrl
            resultats[0]["niveau_estime"]["nclc"] = vrai_nclc
            
            evaluations_finales.append(resultats[0])
            score_total_obtenu += resultats[0]["score"]["obtenu"]
        else:
            evaluations_finales.append(self._generer_tache_vide(1, 4, examen_payload.tache_1))

        # Tâche 2 (Sur 7)
        if resultats[1]:
            # Alignement forcé du niveau de la tâche basé sur son score réel
            vrai_cecrl, vrai_nclc = self._calculer_niveaux_par_tache(resultats[1]["score"]["obtenu"], 7)
            resultats[1]["niveau_estime"]["cecrl"] = vrai_cecrl
            resultats[1]["niveau_estime"]["nclc"] = vrai_nclc
            
            evaluations_finales.append(resultats[1])
            score_total_obtenu += resultats[1]["score"]["obtenu"]
        else:
            evaluations_finales.append(self._generer_tache_vide(2, 7, examen_payload.tache_2))

        # Tâche 3 (Sur 9)
        if resultats[2]:
            # Alignement forcé du niveau de la tâche basé sur son score réel
            vrai_cecrl, vrai_nclc = self._calculer_niveaux_par_tache(resultats[2]["score"]["obtenu"], 9)
            resultats[2]["niveau_estime"]["cecrl"] = vrai_cecrl
            resultats[2]["niveau_estime"]["nclc"] = vrai_nclc
            
            evaluations_finales.append(resultats[2])
            score_total_obtenu += resultats[2]["score"]["obtenu"]
        else:
            evaluations_finales.append(self._generer_tache_vide(3, 9, examen_payload.tache_3))

        # 3. Calculs globaux immuables sur 20
        note_sur_20 = round(score_total_obtenu, 2)
        pourcentage = round((note_sur_20 / 20) * 100)
        
        # Récupération des niveaux du tableau de l'image_9db4cb.png
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
            "versions": {"version_corrigee": "", "version_modele_c1": ""},
            "coaching": {"points_forts": [], "points_a_ameliorer": ["Tâche non traitée."], "conseils": [], "objectif_prochaine_copie": ""}
        }