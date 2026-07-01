import os
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, PayloadSchemaType
from mistralai.client import Mistral  

class RAGService:
    def __init__(self):
        self.qdrant_url = os.environ.get("QDRANT_URL")
        self.qdrant_api_key = os.environ.get("QDRANT_API_KEY")
        self.mistral_api_key = os.environ.get("MISTRAL_API_KEY")
        
        # Initialisation du client Qdrant
        self.qdrant_client = QdrantClient(url=self.qdrant_url, api_key=self.qdrant_api_key, check_compatibility=False)
        
        # 💥 CORRECTION : Initialisation du client Mistral manquant
        self.mistral_client = Mistral(api_key=self.mistral_api_key)
        
        self.coll_copies = "tcf_copies_dataset"
        self.coll_methode = "tcf_methodologie"
        
        # SÉCURITÉ : Assurer la création de l'index pour le filtrage par tache_id
        try:
            self.qdrant_client.create_payload_index(
                collection_name=self.coll_copies,
                field_name="tache_id",
                field_schema=PayloadSchemaType.INTEGER,
            )
            print("[+] Index sur 'tache_id' créé avec succès.")
        except Exception as e:
            # Si l'index existe déjà, Qdrant lève une exception qu'on passe silencieusement
            pass
        

    def _generer_embedding(self, texte: str):
        try:
            # Fonctionne maintenant parfaitement grâce à self.mistral_client
            response = self.mistral_client.embeddings.create(
                model="mistral-embed",
                inputs=[texte]
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"[-] Erreur génération embedding : {e}")
            return None

    def recuperer_contexte(self, texte_utilisateur: str, tache_id: int):
        """
        Interroge en parallèle les deux collections Qdrant pour extraire
        les règles de barème et des exemples de copies similaires.
        """
        vecteur = self._generer_embedding(texte_utilisateur)
        if not vecteur:
            return {"regles": [], "exemples": []}

        # 1. Extraction de la méthodologie (Top 3)
        resultats_methode = self.qdrant_client.query_points(
            collection_name=self.coll_methode,
            query=vecteur,
            limit=3
        )
        
        regles = []
        for hit in resultats_methode.points:
            payload = hit.payload if hasattr(hit, "payload") else getattr(hit, "id", None)
            if isinstance(hit, dict) and "payload" in hit:
                payload = hit["payload"]
            
            if payload and "contenu_regle" in payload:
                regles.append(payload["contenu_regle"])

        # 2. Extraction des copies similaires filtrées par tache_id (Top 2)
        filtre_tache = Filter(
            must=[FieldCondition(key="tache_id", match=MatchValue(value=tache_id))]
        )
        resultats_copies = self.qdrant_client.query_points(
            collection_name=self.coll_copies,
            query=vecteur,
            query_filter=filtre_tache,
            limit=2
        )
        
        exemples = []
        for hit in resultats_copies.points:
            payload = hit.payload if hasattr(hit, "payload") else getattr(hit, "id", None)
            if isinstance(hit, dict) and "payload" in hit:
                payload = hit["payload"]
                
            if payload and "texte_candidat" in payload and "evaluation_expert" in payload:
                exemples.append({
                    "texte_candidat": payload["texte_candidat"],
                    "evaluation_expert": payload["evaluation_expert"]
                })

        return {
            "regles": regles,
            "exemples": exemples
        }