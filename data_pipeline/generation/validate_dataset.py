import json
from pathlib import Path

# Configuration des chemins
chemin_script = Path(__file__).resolve()
chemin_racine = chemin_script.parent.parent.parent
fichier_dataset = chemin_racine / "data_pipeline" / "datasets" / "copies_evaluees.jsonl"

def valider_dataset(chemin_fichier):
    if not chemin_fichier.exists():
        print(f"[-] Erreur : Le fichier {chemin_fichier} n'existe pas.")
        return

    print(f"[*] Début de la validation du dataset : {chemin_fichier.name}\n")

    lignes_valides = 0
    lignes_corrompues = 0
    alertes_bareme = 0
    
    # Dictionnaires pour les statistiques de distribution
    stats_taches = {1: 0, 2: 0, 3: 0}
    distribution_nclc = {}

    with open(chemin_fichier, "r", encoding="utf-8") as f:
        for index, ligne in enumerate(f, 1):
            chaine_propre = ligne.strip()
            if not chaine_propre:
                continue  # On ignore les sauts de ligne vides en fin de fichier

            try:
                donnees = json.loads(chaine_propre)
                lignes_valides += 1
            except json.JSONDecodeError:
                print(f"[ALERTE JSON] Ligne {index} : Chaîne JSON invalide ou tronquée.")
                lignes_corrompues += 1
                continue

            # 1. Vérification des clés structurelles principales
            cles_requises = ["tache_id", "sujet_consigne", "texte_candidat", "evaluation_expert"]
            cles_manquantes = [cle for cle in cles_requises if cle not in donnees]
            
            if cles_manquantes:
                print(f"[ALERTE STRUCTURE] Ligne {index} : Clés manquantes -> {cles_manquantes}")
                lignes_corrompues += 1
                continue

            # 2. Validation stricte du barème FEI selon la tâche
            tache_id = donnees["tache_id"]
            eval_expert = donnees["evaluation_expert"]
            note = eval_expert.get("note_obtenue")
            
            # Mise à jour des stats par tâche
            if tache_id in stats_taches:
                stats_taches[tache_id] += 1

            # Plafonds officiels
            plafond = 4 if tache_id == 1 else (7 if tache_id == 2 else 9)
            
            if note is not None:
                if note < 0 or note > plafond:
                    print(f"[ALERTE BARÈME] Ligne {index} (Tâche {tache_id}) : Note de {note} hors limite (Max attendu: {plafond})")
                    alertes_bareme += 1
            else:
                print(f"[ALERTE DONNÉES] Ligne {index} : 'note_obtenue' est manquante dans l'évaluation.")

            # 3. Collecte de la distribution NCLC
            nclc = eval_expert.get("niveau_nclc_estime", "Inconnu")
            distribution_nclc[nclc] = distribution_nclc.get(nclc, 0) + 1

    # --- RAPPORT FINAL ---
    print("\n" + "="*50)
    print("                RAPPORT DE VALIDATION              ")
    print("="*50)
    print(f"[+] Lignes analysées et valides : {lignes_valides}")
    print(f"[-] Lignes corrompues / rejetées : {lignes_corrompues}")
    print(f"[!] Anomalies de barème détectées : {alertes_bareme}")
    print("-"*50)
    print("📊 Répartition par Tâche TCF :")
    for t, count in stats_taches.items():
        plafond = 4 if t == 1 else (7 if t == 2 else 9)
        print(f"   - Tâche {t} (Notée sur {plafond}) : {count} copies")
        
    print("-"*50)
    print("🇨🇦 Distribution des Niveaux NCLC estimés :")
    for niveau, count in sorted(distribution_nclc.items()):
        print(f"   - {niveau} : {count} copies")
    print("="*50)

    if lignes_corrompues == 0 and alertes_bareme == 0:
        print("\n[🎉 SUCCÈS] Le dataset est 100% conforme pour le stockage et l'entraînement !")
    else:
        print("\n[⚠️ ATTENTION] Des corrections sont nécessaires avant de passer à la suite.")

if __name__ == "__main__":
    valider_dataset(fichier_dataset)