import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # OpenRouter configuration
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # Qdrant configuration
    QDRANT_HOST: str = os.getenv("QDRANT_HOST", "")
    QDRANT_PORT: str = os.getenv("QDRANT_PORT", "6333")
    QDRANT_API_KEY: str = os.getenv("QDRANT_API_KEY", "")
    QDRANT_HTTPS: bool = os.getenv("QDRANT_HTTPS", "False").lower() == "true"
    QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "")
    
    # Multi-collection configuration (new collections use Seznam/retromae-small-cs)
    QDRANT_CONSTITUTIONAL_COURT: str = os.getenv("QDRANT_CONSTITUTIONAL_COURT", "czech_constitutional_court")
    QDRANT_SUPREME_COURT: str = os.getenv("QDRANT_SUPREME_COURT", "czech_supreme_court")
    QDRANT_SUPREME_ADMIN_COURT: str = os.getenv("QDRANT_SUPREME_ADMIN_COURT", "czech_supreme_admin_court")
    
    # Seznam embedding model for new collections
    SEZNAM_EMBEDDING_MODEL: str = os.getenv("SEZNAM_EMBEDDING_MODEL", "Seznam/retromae-small-cs")
    SEZNAM_VECTOR_SIZE: int = 256

    # Server configuration
    PORT: int = int(os.getenv("PORT", "8000"))
    HOST: str = os.getenv("HOST", "0.0.0.0")

    # API security
    API_KEY: str = os.getenv("API_KEY", "")
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")

    # Qdrant retry configuration for serverless cold starts
    QDRANT_MAX_RETRIES: int = int(os.getenv("QDRANT_MAX_RETRIES", "3"))
    QDRANT_INITIAL_TIMEOUT: int = int(os.getenv("QDRANT_INITIAL_TIMEOUT", "30"))

    # Improved RAG pipeline configuration - HARDCODED
    USE_IMPROVED_RAG: bool = True  # Always use improved RAG with hybrid search
    NUM_GENERATED_QUERIES: int = 2  # Generate 2 queries (original + 1 variant)
    RESULTS_PER_QUERY: int = 10  # Get 10 results per query
    FINAL_TOP_K: int = 5  # Return top 5 final results
    
    # Hybrid search configuration - HARDCODED
    HYBRID_DENSE_WEIGHT: float = 0.7  # 70% semantic similarity (dense vectors)
    HYBRID_SPARSE_WEIGHT: float = 0.3  # 30% keyword matching (sparse vectors/BM25)
    USE_RRF_FUSION: bool = True  # Use Reciprocal Rank Fusion for combining results

    # LangChain configuration
    LANGCHAIN_TRACING_V2: bool = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    LANGCHAIN_API_KEY: str = os.getenv("LANGCHAIN_API_KEY", "")
    LANGCHAIN_PROJECT: str = os.getenv("LANGCHAIN_PROJECT", "czech-legal-assistant")
    
    # LLM configuration
    LLM_MODEL: str = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "4000"))
    LLM_TIMEOUT: float = float(os.getenv("LLM_TIMEOUT", "300.0"))
    
    # Embedding configuration
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")

    @property
    def qdrant_protocol(self) -> str:
        return "https" if self.QDRANT_HTTPS else "http"

    @property
    def qdrant_url(self) -> str:
        return f"{self.qdrant_protocol}://{self.QDRANT_HOST}:{self.QDRANT_PORT}"


settings = Settings()
