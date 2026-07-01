import os
import json
import time
from pathlib import Path
from mistralai.client import Mistral
from dotenv import load_dotenv

# 1. Configuration de l'environnement et du client
chemin_script = Path(__file__).resolve()
chemin_racine = chemin_script.parent.parent.parent
load_dotenv(dotenv_path=chemin_racine / ".env")

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
if not MISTRAL_API_KEY:
    raise ValueError("Clé MISTRAL_API_KEY introuvable dans le fichier .env")

client = Mistral(api_key=MISTRAL_API_KEY)

def evaluer_copie_expert(sujet_consigne, contexte_docs, texte_candidat, tache_id):
    """
    Analyse la copie d'un candidat selon le barème officiel FEI du TCF Canada
    et extrait un positionnement direct sur l'échelle NCLC (1 à 12).
    """
    # Détermination dynamique de la note maximale selon la tâche
    note_max = 4 if tache_id == 1 else (7 if tache_id == 2 else 9)

    system_prompt = (
        "Tu es un correcteur officiel et expert du TCF Canada, certifié pour l'évaluation "
        "des Niveaux de compétence linguistique canadiens (NCLC). Ton rôle est d'évaluer de manière "
        "rigoureuse, impartiale et analytique les productions écrites. Tu ne fais preuve d'aucune indulgence."
    )
    
    contexte_str = f"\nDocuments de contexte fournis :\n" + "\n".join(contexte_docs) if contexte_docs else ""

    user_prompt = f"""
    Effectue une correction analytique approfondie de la copie suivante.
    
    [DONNÉES DE L'EXAMEN]
    Tâche TCF : {tache_id}
    Consigne officielle : "{sujet_consigne}"{contexte_str}
    
    [COPIE DU CANDIDAT À ÉVALUER]
    --- DÉBUT DE LA COPIE ---
    {texte_candidat}
    --- FIN DE LA COPIE ---
    
    [CONSIGNES DE NOTATION STRICTES - TÂCHE {tache_id}]
    Conformément aux normes du TCF, tu dois attribuer une note globale sur {note_max} (Note maximale pour la Tâche {tache_id}).
    Base ton évaluation sur :
    1. Le respect de la consigne et la longueur demandée.
    2. La cohérence et la structure (connecteurs, logique).
    3. La richesse globale du lexique et de la syntaxe.
    4. La correction grammaticale et l'orthographe.
    
    Tu dois également positionner le candidat sur l'échelle canadienne officielle : **NCLC de 1 à 12** (ex: NCLC 5, NCLC 7, NCLC 10).
    
    [FORMAT DE SORTIE REQUIS]
    Tu dois répondre UNIQUEMENT sous la forme d'un objet JSON valide. Ne saisis aucun texte avant ou après le JSON.
    Format attendu :
    {{
        "evaluation_analytique": {{
            "note_obtenue": <float_ou_int_entre_0_et_{note_max}>,
            "note_maximale_tache": {note_max},
            "niveau_nclc_estime": "NCLC <numéro_de_1_à_12>",
            "analyse_critères": {{
                "consigne_et_structure": "Commentaire sur le respect des consignes et l'organisation",
                "lexique_et_grammaire": "Commentaire sur la justesse de la langue et les erreurs repérées"
            }},
            "justification_pedagogique": "Explication globale synthétique justifiant la note et le niveau NCLC attribués."
        }}
    }}
    """

    retries = 5
    backoff_delay = 4

    for attempt in range(retries):
        try:
            response = client.chat.complete(
                model="mistral-large-latest",
                temperature=0.1,  # Température très basse pour garantir la fidélité de la notation
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            return json.loads(response.choices[0].message.content.strip())
            
        except Exception as e:
            if "429" in str(e) or "rate_limited" in str(e).lower():
                time.sleep(backoff_delay)
                backoff_delay *= 2
            else:
                print(f"\n[-] Erreur d'évaluation : {e}")
                return None
    return None

if __name__ == "__main__":
    dossier_datasets = chemin_racine / "data_pipeline" / "datasets"
    fichier_entree = dossier_datasets / "copies_candidates_brutes.jsonl"
    fichier_sortie = dossier_datasets / "copies_evaluees.jsonl"
    
    if not fichier_entree.exists():
        raise FileNotFoundError(f"Le fichier source {fichier_entree} n'existe pas.")

    print("[*] Lancement du Pipeline 3 : Moteur d'évaluation expert au barème TCF (Note sur 4/7/9)...")
    
    with open(fichier_entree, "r", encoding="utf-8") as f:
        lignes = f.readlines()
    
    total = len(lignes)
    print(f"[+] {total} copies prêtes à être analysées et labellisées au format NCLC.")

    with open(fichier_sortie, "a", encoding="utf-8") as out_f:
        for index, ligne in enumerate(lignes, 1):
            donnees = json.loads(ligne.strip())
            
            print(f"[{index}/{total}] Évaluation Copie Tâche {donnees['tache_id']} (Cible théorique: {donnees['metadata_candidat']['niveau_cecrl_cible']})... ", end="", flush=True)
            
            # Appel à l'évaluateur adapté au barème FEI et échelle NCLC
            evaluation = evaluer_copie_expert(
                sujet_consigne=donnees["sujet_consigne"],
                contexte_docs=donnees["documents_contexte"],
                texte_candidat=donnees["texte_candidat"],
                tache_id=donnees["tache_id"]
            )
            
            if evaluation:
                # Intégration transparente de l'évaluation dans l'objet d'origine
                donnees["evaluation_expert"] = evaluation["evaluation_analytique"]
                
                # Sauvegarde au fil de l'eau
                out_f.write(json.dumps(donnees, ensure_ascii=False) + "\n")
                print("OK")
            else:
                print("ÉCHEC")
            
            time.sleep(2.0)  # Sécurité anti-rate limit

    print(f"\n[+] Évaluation terminée ! Ton dataset aligné TCF Canada / NCLC est dans : {fichier_sortie}")