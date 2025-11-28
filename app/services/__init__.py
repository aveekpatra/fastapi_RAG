"""
Services Package - LangChain-powered
"""
from app.services.llm import (
    llm_service,
    LLMService,
)

from app.services.embedding import (
    get_embedding,
    get_embeddings_batch,
    get_embedding_model,
)

from app.services.multi_source_search import (
    multi_source_engine,
    DataSource,
    embedding_manager,
    get_configs,
)

__all__ = [
    # LLM
    "llm_service",
    "LLMService",
    # Embedding
    "get_embedding",
    "get_embeddings_batch",
    "get_embedding_model",
    # Multi-source search
    "multi_source_engine",
    "DataSource",
    "embedding_manager",
    "get_configs",
]
