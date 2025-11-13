from typing import Optional
from sentence_transformers import SentenceTransformer

# Initialize the embedding model globally
embedding_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")


async def get_embedding(text: str) -> Optional[list[float]]:
    """
    Get embedding using sentence transformers (paraphrase-multilingual-MiniLM-L12-v2)
    Must match the model used for Qdrant storage
    """
    try:
        embedding = embedding_model.encode(text).tolist()
        print(f"Vektorové vyjádření generováno: {len(embedding)} dimenzí")
        return embedding
    except Exception as e:
        print(f"Chyba pri generovani vektoru: {str(e)}")
        return None