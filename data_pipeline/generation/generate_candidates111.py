import os
import json
import time
from pathlib import Path
from groq import Groq
from mistralai import Mistral
from dotenv import load_dotenv

# 1. Chargement de l'environnement depuis la racine
chemin_script = Path(__file__).resolve()
chemin_racine = chemin_script.parent.parent.parent
load_dotenv(dotenv_path=chemin_racine / ".env")

api_key = os.environ.get("GROQ_API_KEY")
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
if not api_key:
    raise ValueError("Clé GROQ_API_KEY introuvable dans le fichier .env")

#client = Groq(api_key=api_key)
client = Mistral(api_key=os.environ.get("MISTRAL_API_KEY"))

# =====================================================================
# PIPELINE 1 : BANQUE DE SUJETS TECHNIQUEMENT DROITS (ENRICHIE)
# =====================================================================
BANQUE_SUJETS = [
    # --- THÈMES DE DÉPART ---
    {
        "tache_id": 1,
        "consigne": "Salut, j'ai appris que tu vas à une salle de sport et qu'elle est magnifique. Peux-tu m'en dire plus ? Écrivez un message pour répondre à votre ami concernant ce sujet.",
        "documents_contexte": [],
        "contraintes": {"min_mots": 60, "max_mots": 120, "type_texte": "Message amical"}
    },
    {
        "tache_id": 2,
        "consigne": "Vous avez fait un voyage mémorable dans une région isolée. Racontez votre expérience dans votre journal de bord ou pour un article de blog destiné à vos proches.",
        "documents_contexte": [],
        "contraintes": {"min_mots": 120, "max_mots": 150, "type_texte": "Récit / Article de blog"}
    },
    {
        "tache_id": 3,
        "consigne": "Le télétravail : opportunité ou isolement social ? Synthétisez les avis des documents fournis et donnez votre propre point de vue argumenté.",
        "documents_contexte": [
            "Doc A: Le télétravail améliore la productivité et offre une flexibilité indispensable aux familles modernes.",
            "Doc B: Le travail à distance détruit le lien social, favorise la dépression et efface la frontière entre vie privée et professionnelle."
        ],
        "contraintes": {"min_mots": 120, "max_mots": 180, "type_texte": "Note argumentative / Synthèse"}
    },

    # --- SUJETS EXTRAITS DU PDF (COLONNE 1 : TÂCHE 1) ---
    {
        "tache_id": 1,
        "consigne": "Je vais bientôt vivre dans ton quartier. Je cherche un endroit sympathique pour faire mes courses. Est-ce que tu connais un marché intéressant ? Vous répondez à votre ami Bernard. Dans votre message, vous décrivez un marché de votre quartier que vous aimez bien (lieu, horaires, produits, etc.).",
        "documents_contexte": [],
        "contraintes": {"min_mots": 80, "max_mots": 120, "type_texte": "Message amical"}
    },
    {
        "tache_id": 1,
        "consigne": "Vous êtes nouveaux dans une université. Décrivez à vos amis comment cela se passe avec les profs, les autres étudiants, les activités et le reste.",
        "documents_contexte": [],
        "contraintes": {"min_mots": 80, "max_mots": 120, "type_texte": "Message amical"}
    },
    {
        "tache_id": 1,
        "consigne": "Salut, Je voudrais m'inscrire dans une salle de sport. Est-ce que tu peux me donner des informations sur les possibilités dans notre quartier ? Merci d'avance. Bisous Laura",
        "documents_contexte": [],
        "contraintes": {"min_mots": 60, "max_mots": 120, "type_texte": "Message amical"}
    },
    {
        "tache_id": 1,
        "consigne": "Vous souhaitez faire du sport et vous voulez que votre ami vous accompagne. Écrivez-lui un message pour lui proposer de pratiquer ensemble.",
        "documents_contexte": [],
        "contraintes": {"min_mots": 60, "max_mots": 120, "type_texte": "Message amical"}
    },
    {
        "tache_id": 1,
        "consigne": "Mathieu a écrit : 'Je cherche un vélo en bon état et bon marché. Contactez-moi par courriel mathieu@gmail.com'. Vous avez un vélo à vendre. Vous écrivez un courriel pour décrire votre vélo et proposer un prix. Vous lui donnez un rendez-vous pour essayer le vélo.",
        "documents_contexte": [],
        "contraintes": {"min_mots": 60, "max_mots": 120, "type_texte": "Courriel informel"}
    },
    {
        "tache_id": 1,
        "consigne": "Vous écrivez un email pour répondre à votre ami(e) qui va passer le week-end dans votre ville. Il faut lui décrire les moyens de transports disponibles.",
        "documents_contexte": [],
        "contraintes": {"min_mots": 60, "max_mots": 120, "type_texte": "Courriel informel"}
    },
    {
        "tache_id": 1,
        "consigne": "Vous invitez un(e) ami(e) pour une semaine de festival de cinéma organisée dans votre ville. Vous lui envoyez un message avec toutes les informations nécessaires (programme, tarif, horaire, date, lieu, etc.).",
        "documents_contexte": [],
        "contraintes": {"min_mots": 60, "max_mots": 120, "type_texte": "Message d'invitation"}
    },
    {
        "tache_id": 1,
        "consigne": "Le journal 'Bienvenue' compte publier un article qui parle des habitants de notre ville. Écrivez-nous un message qui sera diffusé dans ce numéro. Vous vous êtes récemment installé dans cette ville, et il vous est demandé de vous présenter et décrire ensuite tous vos lieux préférés au sein de cette ville.",
        "documents_contexte": [],
        "contraintes": {"min_mots": 60, "max_mots": 120, "type_texte": "Message de présentation / Contribution"}
    },
    {
        "tache_id": 1,
        "consigne": "Rédigez un courriel pour convier une amie à vous accompagner au concert de votre artiste préféré (indiquer le jour, le lieu, le prix, l'artiste, etc.).",
        "documents_contexte": [],
        "contraintes": {"min_mots": 60, "max_mots": 120, "type_texte": "Courriel d'invitation"}
    },

    # --- SUJETS EXTRAITS DU PDF (COLONNE 2 : TÂCHE 2) ---
    {
        "tache_id": 2,
        "consigne": "Vous faites partie d'une association de quartier qui propose des activités aux enfants (aide aux devoirs, sorties, jeux, etc.). Sur votre site internet, vous racontez votre expérience et vous expliquez pourquoi ce type d'association est utile.",
        "documents_contexte": [],
        "contraintes": {"min_mots": 120, "max_mots": 150, "type_texte": "Récit / Témoignage d'expérience"}
    },
    {
        "tache_id": 2,
        "consigne": "Vous avez décidé de ne plus utiliser les réseaux sociaux (Twitter, Instagram, Facebook et autres). Écrivez un message à vos amis en citant les raisons derrière cette décision.",
        "documents_contexte": [],
        "contraintes": {"min_mots": 120, "max_mots": 150, "type_texte": "Lettre / Message à des proches"}
    },
    {
        "tache_id": 2,
        "consigne": "Un site internet propose un concours sur le thème 'Votre plus belle fête, racontez-la nous'. Vous participez au concours. Dans votre texte, vous racontez comment s'est passée cette fête (anniversaire, fête traditionnelle, etc.) et vous expliquez quel souvenir vous en gardez.",
        "documents_contexte": [],
        "contraintes": {"min_mots": 120, "max_mots": 150, "type_texte": "Récit de concours / Blog"}
    },
    {
        "tache_id": 2,
        "consigne": "Vous avez déjà étudié dans une université à l'étranger. Écrivez un article sur votre Blog pour raconter cette expérience.",
        "documents_contexte": [],
        "contraintes": {"min_mots": 120, "max_mots": 150, "type_texte": "Article de blog"}
    },
    {
        "tache_id": 2,
        "consigne": "Écrivez un message à vos amis pour leur partager votre expérience de travail temporaire effectué durant les vacances d'été.",
        "documents_contexte": [],
        "contraintes": {"min_mots": 120, "max_mots": 150, "type_texte": "Message informel"}
    },
    {
        "tache_id": 2,
        "consigne": "Vous avez accueilli un étudiant étranger chez vous pendant une semaine. Écrivez un article sur votre blog pour raconter ce qui vous a intéressé et ce qui vous a le plus impressionné dans cette expérience.",
        "documents_contexte": [],
        "contraintes": {"min_mots": 120, "max_mots": 150, "type_texte": "Article de blog"}
    },
    {
        "tache_id": 2,
        "consigne": "Vous venez d'assister au concert de votre artiste favori. Vous écrivez un article sur votre blog personnel pour partager cette expérience et inciter vos amis et les autres à assister à son prochain concert.",
        "documents_contexte": [],
        "contraintes": {"min_mots": 120, "max_mots": 150, "type_texte": "Article de blog"}
    },
    {
        "tache_id": 2,
        "consigne": "Les enseignants organisent une séance avec les élèves pour leur parler des métiers, et vous aimeriez y prendre part pour partager votre expérience et évoquer les avantages (expérience, collègues, etc.).",
        "documents_contexte": [],
        "contraintes": {"min_mots": 120, "max_mots": 150, "type_texte": "Lettre de participation / Présentation"}
    },
    {
        "tache_id": 2,
        "consigne": "Un site internet recherche des gens pour faire des témoignages sur la vie avec les personnes âgées. Rédigez votre expérience pour faire part de comment vous avez pu vous en sortir.",
        "documents_contexte": [],
        "contraintes": {"min_mots": 120, "max_mots": 150, "type_texte": "Témoignage écrit"}
    },
    {
        "tache_id": 2,
        "consigne": "Vous avez assisté à un festival (gastronomie, musique, sport). Racontez sur votre blog ce qui vous a plu et déplu.",
        "documents_contexte": [],
        "contraintes": {"min_mots": 120, "max_mots": 150, "type_texte": "Article de blog"}
    },

    # --- SUJETS EXTRAITS DU PDF (COLONNE 3 : TÂCHE 3 - SYNTHÈSE + ARGUMENTATION) ---
    {
        "tache_id": 3,
        "consigne": "Le livre papier ou le livre numérique ? Dans la première partie, vous ferez le résumé des deux documents (entre 40 et 60 mots) ; dans la deuxième partie, vous donnerez votre avis sur le sujet (entre 80 et 120 mots).",
        "documents_contexte": [
            "Document 1 : Depuis plusieurs années maintenant, de nombreux lecteurs ont décidé de remplacer la bibliothèque traditionnelle par des livres numériques. L'avantage est avant tout économique (économie de papier, coût réduit) et offre une ouverture sur le monde pour les personnes en situation de handicap grâce aux options d'accessibilité.",
            "Document 2 : Le livre numérique remplacera-t-il le livre papier ? « Non », répondront la plupart des lecteurs. Le support papier transmet de l'esthétique et des émotions (odeur, partage, prêt). À l'inverse, l'outil numérique est impersonnel et exige des compétences informatiques qui peuvent être excluantes."
        ],
        "contraintes": {"min_mots": 120, "max_mots": 180, "type_texte": "Synthèse & Prise de position"}
    },
    {
        "tache_id": 3,
        "consigne": "Les photos sur le CV, pour ou contre ? Dans la première partie, ferez le résumé des documents ; dans la deuxième partie, donnez votre avis argumenté.",
        "documents_contexte": [
            "Document 1 : On parle de l'inutilité de la photo sur le CV, l'important étant les diplômes et l'expérience. Une étude montre que l'analyse des photos fait perdre du temps aux recruteurs. De plus, elle ne doit pas être obligatoire pour éviter d'influencer le choix et de générer des discriminations basées sur l'apparence ou la couleur de peau.",
            "Document 2 : La présence d'une photo sur le CV n'est pas un critère de sélection pur mais s'avère indispensable pour certains métiers d'accueil (comme hôtesse d'accueil). Elle donne une première idée du candidat et répond au besoin de certains employeurs de visualiser à qui ils s'adressent."
        ],
        "contraintes": {"min_mots": 120, "max_mots": 180, "type_texte": "Synthèse & Prise de position"}
    },
    {
        "tache_id": 3,
        "consigne": "La lecture pour les enfants. Dans la première partie, résumez les positions des documents ; dans la deuxième partie, donnez votre avis personnel.",
        "documents_contexte": [
            "Document 1 : Il ne faut surtout pas obliger les enfants à lire. L'acte de lecture est très particulier et le goût de lire ne peut pas s'imposer. Tout comme le sport, il faut chercher à motiver l'enfant plutôt que de recourir à la contrainte, selon les spécialistes de l'enfance.",
            "Document 2 : Les dynamiques d'accès à la culture varient fortement selon les contextes. Les structures opposant le système privé payant au système public réduisent la mixité sociale. Cela limite les occasions de rencontres entre jeunes de milieux sociaux différents et renforce les disparités d'apprentissage d'origine."
        ],
        "contraintes": {"min_mots": 120, "max_mots": 180, "type_texte": "Synthèse & Prise de position"}
    },
    {
        "tache_id": 3,
        "consigne": "L'uniforme scolaire : Pour ou Contre ? Dans la première partie, rédigez le résumé des documents ; dans la deuxième partie, donnez votre avis.",
        "documents_contexte": [
            "Document 1 : Le port de l'uniforme étouffe et écrase la personnalité des élèves. Ils ne peuvent pas s'habiller comme ils le souhaitent ni exprimer leur identité ou leur créativité à travers la mode, ce qui génère de la frustration.",
            "Document 2 : L'uniforme développe un sentiment fort d'appartenance à un collectif et réduit considérablement les discriminations basées sur la classe sociale ou les marques vestimentaires. De plus, il représente une économie financière substantielle pour les parents."
        ],
        "contraintes": {"min_mots": 120, "max_mots": 180, "type_texte": "Synthèse & Prise de position"}
    },
    {
        "tache_id": 3,
        "consigne": "La gratuité des transports en commun. Dans la première partie, faites le résumé des documents (40-60 mots) ; dans la deuxième partie, donnez votre avis (80-120 mots).",
        "documents_contexte": [
            "Document 1 : Les transports gratuits permettent de désengorger les centres-villes en réduisant le trafic automobile, diminuent la pollution de l'air et stimulent l'économie locale en incitant les citoyens à consommer dans les commerces de proximité.",
            "Document 2 : C'est une fausse bonne idée. Cette gratuité engendre un coût financier massif pour les municipalités au détriment d'autres priorités (espaces verts). Il vaudrait mieux étendre le réseau dans les zones isolées et maintenir un service payant pour garantir le respect du matériel par les usagers."
        ],
        "contraintes": {"min_mots": 120, "max_mots": 180, "type_texte": "Synthèse & Prise de position"}
    },
    {
        "tache_id": 3,
        "consigne": "La restauration rapide. Faites le résumé des documents puis exprimez votre point de vue sur la question.",
        "documents_contexte": [
            "Document 1 : Manger régulièrement dans des fast-foods est dangereux pour la santé en raison de l'apport excessif en calories (frites, sodas). Par ailleurs, l'utilisation massive d'emballages plastiques à usage unique accroît considérablement la production de déchets et la pollution.",
            "Document 2 : La restauration rapide remplit un rôle utilitaire indispensable. Elle offre une nourriture chaude, rapide d'accès et économique pour les personnes pressées. De plus, son maillage géographique est excellent et les règles d'hygiène y sont extrêmement strictes."
        ],
        "contraintes": {"min_mots": 120, "max_mots": 180, "type_texte": "Synthèse & Prise de position"}
    },
    {
        "tache_id": 3,
        "consigne": "Les jeux vidéo. Résumez les deux documents puis présentez votre opinion.",
        "documents_contexte": [
            "Document 1 : L'exposition régulière aux jeux vidéo, en particulier aux contenus violents, augmente les comportements agressifs et les pensées négatives chez les enfants et adolescents, un phénomène jugé inévitable malgré la vigilance parentale.",
            "Document 2 : Les jeux vidéo apportent des bénéfices notables pour le fonctionnement cérébral. Ils stimulent des fonctions cognitives cruciales telles que la concentration, la créativité et la capacité d'analyse fine pour résoudre des problèmes complexes."
        ],
        "contraintes": {"min_mots": 120, "max_mots": 180, "type_texte": "Synthèse & Prise de position"}
    },
    {
        "tache_id": 3,
        "consigne": "La location périodique de son appartement / logement. Résumez les points de vue des deux documents avant de donner votre opinion personnelle.",
        "documents_contexte": [
            "Document 1 : Louer temporairement son logement permet de générer des revenus complémentaires réguliers, d'offrir une solution d'hébergement plus abordable que l'hôtel basée sur la confiance, et de favoriser des échanges humains enrichissants.",
            "Document 2 : Cette pratique engendre des risques importants : dégradation des lieux par des locataires indélicats, nuisances pour le voisinage, charge de travail chronophage (gestion, ménage) et complexité de planification financière à long terme."
        ],
        "contraintes": {"min_mots": 120, "max_mots": 180, "type_texte": "Synthèse & Prise de position"}
    },
    {
        "tache_id": 3,
        "consigne": "La distribution des boissons dans les lycées. Rédigez le résumé objectif puis votre point de vue argumenté.",
        "documents_contexte": [
            "Document 1 : Installer des distributeurs permet de maintenir une bonne hydratation chez les élèves, ce qui favorise la concentration. Cela leur évite également de perdre du temps en sortant de l'établissement et offre l'opportunité de mettre à disposition des choix équilibrés.",
            "Document 2 : Cette présence favorise l'accès facile aux sodas et boissons sucrées, augmentant les risques d'obésité et de mauvaise alimentation. De plus, cela détourne les lycéens de la consommation d'eau pure, essentielle à une bonne santé."
        ],
        "contraintes": {"min_mots": 120, "max_mots": 180, "type_texte": "Synthèse & Prise de position"}
    },
    {
        "tache_id": 3,
        "consigne": "L'interdiction des voitures en ville. Résumez les documents puis exposez vos arguments.",
        "documents_contexte": [
            "Document 1 : L'interdiction des voitures améliore le cadre de vie des piétons, des cyclistes et des commerces de centre-ville. Les bénéfices sur la qualité de l'air et le dynamisme économique local sont immédiats et garantis.",
            "Document 2 : Cette mesure est inefficace et contre-productive. Elle ne supprime pas la pollution mais déplace simplement le trafic vers la périphérie. De plus, elle pénalise l'économie locale en ciblant les entreprises liées à l'automobile."
        ],
        "contraintes": {"min_mots": 120, "max_mots": 180, "type_texte": "Synthèse & Prise de position"}
    },
    {
        "tache_id": 3,
        "consigne": "L'apprentissage des langues à distance. Procédez à la synthèse des documents puis donnez votre avis.",
        "documents_contexte": [
            "Document 1 : Les cours en ligne offrent une flexibilité complète (rythme, gestion du temps), un coût souvent plus abordable, ainsi qu'une richesse d'outils interactifs permettant d'échanger directement avec des locuteurs natifs à travers le monde.",
            "Document 2 : Cette méthode manque d'interactions en face-à-face en temps réel pour la pratique orale. Elle exige une autodiscipline rigoureuse, accentue les inégalités d'accès aux technologies et s'avère moins structurée pour les profils ayant besoin d'un cadre traditionnel."
        ],
        "contraintes": {"min_mots": 120, "max_mots": 180, "type_texte": "Synthèse & Prise de position"}
    },
    {
        "tache_id": 3,
        "consigne": "La vie à la campagne ou en ville. Résumez les positions des documents avant d'exprimer votre avis personnel.",
        "documents_contexte": [
            "Document 1 : Vivre en ville offre une multitude d'activités de divertissement à proximité immédiate (cinémas, restaurants, shopping, musées, théâtres). Les infrastructures de transport permettent d'accéder à tout sans effort.",
            "Document 2 : Choisir la campagne permet de se rapprocher de la nature et de retrouver le calme. Les relations sociales y sont plus conviviales (barbues dans le jardin, terrasses) et le coût de l'immobilier y est nettement inférieur, offrant de plus grands espaces pour un même budget."
        ],
        "contraintes": {"min_mots": 120, "max_mots": 180, "type_texte": "Synthèse & Prise de position"}
    }
]

# =====================================================================
# PIPELINE 2 : MATRICE DE PROFILS POUR LA DIVERSITÉ DES DONNÉES
# =====================================================================
PROFILS_CANDIDATS = [
    {
        "profil_id": "candidat_debutant_limite",
        "origine_linguistique": "Allophone (Fortes interférences de la langue maternelle, calques grossiers)",
        "richesse_lexicale": "Très limitée, répétitions immédiates, mots tronqués ou inventés",
        "style": "Phrases juxtaposées, ponctuation anarchique, pas de connecteurs"
    },
    {
        "profil_id": "candidat_anglophone_syntaxe_intermediaire",
        "origine_linguistique": "Anglophone (Oublis systématiques des accords de genre/nombre, faux-amis réguliers)",
        "richesse_lexicale": "Moyenne, calquée sur le vocabulaire fonctionnel quotidien",
        "style": "Phrases courtes et linéaires, calques de structures idiomatiques anglaises"
    },
    {
        "profil_id": "candidat_expert_academique",
        "origine_linguistique": "Niveau universitaire / Grande habitude des écrits formels",
        "richesse_lexicale": "Soutenue, riche, nuances idiomatiques maîtrisées, figures de style",
        "style": "Argumentation fluide, maîtrise des propositions subordonnées complexes"
    }
]

# Spectre complet du CECRL demandé
NIVEAUX_CECRL = ["A1", "A2", "B1", "B2", "C1", "C2"]

# Table de conversion stricte vers le NCLC pour la conformité TCF Canada
CONVERSION_NCLC = {
    "A1": "NCLC 1-2",
    "A2": "NCLC 3-4",
    "B1": "NCLC 5-6",
    "B2": "NCLC 7-8",
    "C1": "NCLC 9-10",
    "C2": "NCLC 11-12"
}

def simuler_copie_candidat(sujet, profil, niveau):
    """
    Exécute le Pipeline 2 en demandant à Llama 3.3 de simuler la production
    textuelle brute d'un élève selon son profil et son niveau CECRL.
    """
    system_prompt = (
        "Tu es un simulateur de comportement humain et un ingénieur de données linguistique. "
        "Ton rôle unique est d'écrire une copie d'examen brute, exactement comme le ferait un vrai candidat."
    )
    
    contexte_docs = ""
    if sujet["tache_id"] == 3:
        contexte_docs = f"Documents sources à utiliser obligatoirement pour la synthèse :\n" + "\n".join(sujet["documents_contexte"])

    user_prompt = f"""
    Génère uniquement la production textuelle d'un candidat passant le TCF Canada.
    
    [PARAMÈTRES DU CANDIDAT]
    - Niveau à simuler (Échelle CECRL) : {niveau} (Correspondance officielle : {CONVERSION_NCLC[niveau]})
    - Origine linguistique & biais : {profil['origine_linguistique']}
    - Richesse du vocabulaire : {profil['richesse_lexicale']}
    - Style rédactionnel : {profil['style']}
    
    [CONSIGNES DE LA TÂCHE {sujet['tache_id']}]
    Sujet : "{sujet['consigne']}"
    {contexte_docs}
    Contrainte de longueur : {sujet['contraintes']['min_mots']} à {sujet['contraintes']['max_mots']} mots.
    Type de texte attendu : {sujet['contraintes']['type_texte']}
    
    [DIRECTIVE STRICTE DE SORTIE]
    Rédige le texte brut directement. Ne mets pas de guillemets autour du texte, pas d'introduction. Écris UNIQUEMENT ce que le candidat écrit sur sa feuille d'examen. Respecte scrupuleusement le niveau {niveau} : si le niveau est A1/A2, le texte DOIT être truffé d'erreurs massives et de phrases inachevées. Si le niveau est C1/C2, le texte doit être d'une clarté irréprochable.
    """

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0.8,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[-] Erreur lors de la simulation de copie : {e}")
        return None


    

if __name__ == "__main__":
    print("[*] Initialisation des Pipelines 1 & 2 (Gamme complète A1 -> C2)...")
    
    dossier_sorties = chemin_racine / "data_pipeline" / "datasets"
    os.makedirs(dossier_sorties, exist_ok=True)
    fichier_sorties = dossier_sorties / "copies_candidates_brutes.jsonl"
    
    for sujet in BANQUE_SUJETS:
        print(f"\n--- Traitement de la Tâche {sujet['tache_id']} ({sujet['contraintes']['type_texte']}) ---")
        for profil in PROFILS_CANDIDATS:
            for niveau in NIVEAUX_CECRL:
                print(f"[~] Simulation Profil: {profil['profil_id']} | Niveau CECRL: {niveau}...")
                
                copie_brute = simuler_copie_candidat(sujet, profil, niveau)
                
                if copie_brute:
                    donnees_paire = {
                        "tache_id": sujet["tache_id"],
                        "sujet_consigne": sujet["consigne"],
                        "documents_contexte": sujet["documents_contexte"],
                        "contraintes": sujet["contraintes"],
                        "metadata_candidat": {
                            "profil_id": profil["profil_id"],
                            "niveau_cecrl_cible": niveau,
                            "equivalent_nclc": CONVERSION_NCLC[niveau]
                        },
                        "texte_candidat": copie_brute
                    }
                    
                    with open(fichier_sorties, "a", encoding="utf-8") as f:
                        f.write(json.dumps(donnees_paire, ensure_ascii=False) + "\n")
                        
                    time.sleep(2)  # Respect des quotas d'appels Groq
                    
    print(f"\n[+] Succès ! Le fichier de copies multi-niveaux a été enrichi : {fichier_sorties}")