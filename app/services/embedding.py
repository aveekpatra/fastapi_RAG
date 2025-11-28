"""
Embedding Service - LangChain-powered
Provides embedding generation using HuggingFace models
"""
from typing import List, Optional

from langchain_huggingface import HuggingFaceEmbeddings

from app.config import settings

_embedding_model: Optional[HuggingFaceEmbeddings] = None


def get_embedding_model() -> HuggingFaceEmbeddings:
    """Get or create the embedding model singleton"""
    global _embedding_model

    if _embedding_model is None:
        _embedding_model = HuggingFaceEmbeddings(
            model_name=settings.EMBEDDING_MODEL,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": False},
        )
        print(f"✅ Embedding model loaded: {settings.EMBEDDING_MODEL}")

    return _embedding_model


async def get_embedding(text: str) -> Optional[List[float]]:
    """Generate embedding for text"""
    try:
        model = get_embedding_model()
        embedding = model.embed_query(text)
        return embedding
    except Exception as e:
        print(f"❌ Embedding error: {e}")
        return None


async def get_embeddings_batch(texts: List[str]) -> Optional[List[List[float]]]:
    """Generate embeddings for multiple texts"""
    try:
        model = get_embedding_model()
        embeddings = model.embed_documents(texts)
        return embeddings
    except Exception as e:
        print(f"❌ Batch embedding error: {e}")
        return None
