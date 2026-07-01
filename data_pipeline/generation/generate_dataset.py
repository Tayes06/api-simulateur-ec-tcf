import os
import json
import time
from pathlib import Path
from groq import Groq
from dotenv import load_dotenv

# Trouver le chemin du fichier .env à la racine (2 niveaux au-dessus de ce script)
chemin_script = Path(__file__).resolve()
chemin_racine = chemin_script.parent.parent.parent
chemin_env = chemin_racine / ".env"

# Charger les variables du fichier .env dans l'environnement système
load_dotenv(dotenv_path=chemin_env)

# 1. Vérification et initialisation du client Groq
api_key = os.environ.get("GROQ_API_KEY")
if not api_key:
    raise ValueError(f"La clé GROQ_API_KEY n'a pas pu être chargée depuis le fichier .env situé à l'emplacement : {chemin_env}")

client = Groq(api_key=api_key)

# 2. Base de sujets réels (inspirés de vos documents OPAL)
SUJETS_TCF = [
    {
        "tache_id": 1,
        "consigne": "Salut, j'ai appris que tu vas à une salle de sport et qu'elle est magnifique. Peux-tu m'en dire plus ? Écrivez un message pour répondre à votre ami concernant ce sujet (60-120 mots)."
    },
    {
        "tache_id": 1,
        "consigne": "Vous avez invité votre ami Éric à votre mariage au château de Chmbony et il vous a répondu qu'il ne connaît pas ce château. Décrivez à votre ami (lieu, localisation, transport, etc.) (60-120 mots)."
    }
]

# Nous ciblons les niveaux intermédiaires et avancés là où la demande de correction est forte
NIVEAUX_CIBLES = ["A1", "A2", "B1", "B2", "C1", "C2"]
# 1. Base de données des tâches enrichie des règles officielles du TCF
CONFIG_TACHES = {
    1: {
        "limite_mots": "entre 60 et 120 mots",
        "instructions_structure": "la présence de formules de salutation (début/fin), de paragraphes et de connecteurs logiques adaptés à un message amical ou formel.",
        "contexte_supplementaire": ""
    },
    2: {
        "limite_mots": "entre 120 et 150 mots",
        "instructions_structure": "la structure d'un récit (introduction, déroulement chronologique, conclusion) et la bonne utilisation des temps du passé (imparfait/passé composé).",
        "contexte_supplementaire": ""
    },
    3: {
        "limite_mots": "entre 120 et 180 mots",
        "instructions_structure": "l'organisation d'une argumentation solide : une première partie synthétisant les deux points de vue des documents, et une seconde partie exposant l'avis personnel du candidat de façon fluide sans salutations.",
        "contexte_supplementaire": "IMPORTANT : Le candidat doit obligatoirement s'appuyer sur les documents textuels fournis dans la clé 'documents_contexte' pour rédiger sa production."
    }
}

def generer_donnees_tcf(sujet, niveau):
    """
    Demande à Llama 3 70B de simuler une copie d'élève et de générer 
    l'analyse pédagogique stricte attendue au format JSON.
    """
    system_prompt = (
        "Tu es un ingénieur de données et un examinateur expert certifié du TCF Canada. "
        "Tu maîtrises parfaitement les grilles d'évaluation du NCLC. "
        "Tu dois impérativement générer un objet JSON unique, valide, sans aucune introduction ni conclusion textuelle."
    )
    
    user_prompt = f"""
        Basé sur ce sujet officiel du TCF Canada (Tâche {sujet['tache_id']}) :
        "{sujet['consigne']}"
        {config['contexte_supplementaire']}

        Étape 1 : Rédige la production écrite d'un candidat fictif qui obtiendrait STRICTEMENT le niveau NCLC {niveau}.
        - Si le niveau est A1, A2, B1 ou B2, insère des erreurs réalistes et fréquentes (orthographe, accords, mauvaise syntaxe).
        - Respecte impérativement la contrainte de longueur officielle qui est : {config['limite_mots']}.

        Étape 2 : Analyse ce texte comme un correcteur expérimenté et renvoie EXACTEMENT la structure JSON suivante :
        {{
        "texte_candidat": "[Insérer ici le texte généré à l'étape 1]",
        "meta_performance": {{
            "score_tache": "[Note simulée sur 4.0, ex: 2.4/4]",
            "niveau_nclc_estime": "{niveau}",
            "nombre_mots": [Nombre exact de mots]
        }},
        "analyse_pedagogique": {{
            "comprehension_sujet": "[Critique détaillée de l'adéquation avec la consigne]",
            "methodologie_structure": "[Analyse axée sur {config['instructions_structure']}]",
            "niveau_linguistique": "[Analyse de la morphosyntaxe et du lexique]"
        }},
        "tableau_erreurs": [
            {{
            "original": "[Segment erroné]",
            "correction": "[Segment corrigé]",
            "type": "orthographe | grammaire | syntaxe | vocabulaire",
            "explication_pedagogique": "[Règle mnémonique claire]"
            }}
        ],
        "versions_proposees": {{
            "version_corrigee_fidele": "[Le texte nettoyé mais fidèle au style de l'élève]",
            "version_optimisee_c1": "[Réécriture complète de niveau supérieur]"
        }}
        }}
    """

    try:
        # Utilisation du modèle Llama 3 70B (Gratuit et ultra-performant pour le JSON structuré)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"[-] Erreur de communication avec l'API Groq : {e}")
        return None

def exporter_vers_jsonl(sujet, data_json, dossier_dataset="../datasets"):
    """
    Prend le JSON produit, le formate selon les standards d'entraînement 
    des LLM (Messages: System, User, Assistant) et l'écrit dans un fichier .jsonl.
    """
    os.makedirs(dossier_dataset, exist_ok=True)
    fichier_sortie = os.path.join(dossier_dataset, "tcf_dataset_preparation.jsonl")
    
    # Structure de Fine-Tuning standard (Format Chat)
    ligne_entrainement = {
        "messages": [
            {
                "role": "system",
                "content": "Tu es l'examinateur officiel de l'API TCF Canada. Évalue la production du candidat selon les critères du NCLC. Tu dois impérativement répondre au format JSON strict."
            },
            {
                "role": "user",
                "content": f"Sujet Tâche {sujet['tache_id']} : {sujet['consigne']}\n\nProduction du candidat :\n{data_json['texte_candidat']}"
            },
            {
                "role": "assistant",
                "content": json.dumps({
                    "meta_performance": data_json["meta_performance"],
                    "analyse_pedagogique": data_json["analyse_pedagogique"],
                    "tableau_erreurs": data_json["tableau_erreurs"],
                    "versions_proposees": data_json["versions_proposees"]
                }, ensure_ascii=False)
            }
        ]
    }
    
    with open(fichier_sortie, "a", encoding="utf-8") as f:
        f.write(json.dumps(ligne_entrainement, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    print("[*] Lancement du pipeline de génération de données gratuit...")
    
    for count, sujet in enumerate(SUJETS_TCF, 1):
        print(f"\n--- Traitement du Sujet {count} (Tâche {sujet['tache_id']}) ---")
        for niveau in NIVEAUX_CIBLES:
            print(f"[~] Génération de la variante de niveau : {niveau}...")
            
            resultat = generer_donnees_tcf(sujet, niveau)
            
            if resultat and "texte_candidat" in resultat:
                exporter_vers_jsonl(sujet, resultat)
                print(f"[+] Variante {niveau} sauvegardée avec succès.")
            else:
                print(f"[-] Échec de génération pour le niveau {niveau}.")
            
            # Petite pause de sécurité pour respecter le Rate Limit gratuit de Groq
            time.sleep(3)
            
    print("\n[+] Pipeline terminé ! Vos données sont prêtes dans data_pipeline/datasets/tcf_dataset_preparation.jsonl")