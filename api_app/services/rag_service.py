import os
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, PayloadSchemaType
from mistralai.client import Mistral  
from typing import List, Optional

class RAGService:
    def __init__(self):
        self.qdrant_url = os.environ.get("QDRANT_URL")
        self.qdrant_api_key = os.environ.get("QDRANT_API_KEY")
        self.mistral_api_key = os.environ.get("MISTRAL_API_KEY")
        
        # Initialisation du client Qdrant
        self.qdrant_client = QdrantClient(url=self.qdrant_url, api_key=self.qdrant_api_key, check_compatibility=False)
        self.mistral_client = Mistral(api_key=self.mistral_api_key)
        
        self.coll_copies = "tcf_copies_dataset"
        self.coll_methode = "tcf_methodologie"
        
        try:
            self.qdrant_client.create_payload_index(
                collection_name=self.coll_copies,
                field_name="tache_id",
                field_schema=PayloadSchemaType.INTEGER,
            )
            print("[+] Index sur 'tache_id' créé avec succès.")
        except Exception:
            pass

    def _generer_embedding(self, texte: str):
        try:
            response = self.mistral_client.embeddings.create(
                model="mistral-embed",
                inputs=[texte]
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"[-] Erreur génération embedding : {e}")
            return None

    def recuperer_contexte(self, texte_utilisateur: str, tache_id: int):
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
            payload = getattr(hit, "payload", None)
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
            payload = getattr(hit, "payload", None)
            if payload and "texte_candidat" in payload and "evaluation_expert" in payload:
                exemples.append({
                    "texte_candidat": payload["texte_candidat"],
                    "evaluation_expert": payload["evaluation_expert"]
                })

        return {
            "regles": regles,
            "exemples": exemples
        }
        
    def recuperer_contexte_oral(
        self, 
        content_sujet: str, 
        task_type: str, 
        task3_type: Optional[str] = None
    ) -> List[str]:
        query_text = f"Méthodologie TCF Canada Expression Orale {task_type}"
        if task3_type:
            query_text += f" {task3_type}"
        query_text += f" : {content_sujet}"
        
        query_vector = self._generer_embedding(query_text)
        if not query_vector:
            return []

        try:
            search_result = self.qdrant_client.query_points(
                collection_name=self.coll_methode,
                query=query_vector,
                limit=4
            )
            
            contexte_chunks = []
            # FIX : Utilisation explicite de search_result.points au lieu de search_result
            for hit in search_result.points:
                payload = getattr(hit, "payload", None)
                if payload:
                    if "contenu_regle" in payload:
                        contexte_chunks.append(payload["contenu_regle"])
                    elif "text" in payload:
                        contexte_chunks.append(payload["text"])
            
            return contexte_chunks

        except Exception as e:
            print(f"Erreur lors de la récupération RAG oral : {str(e)}")
            return []