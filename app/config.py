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

    @property
    def qdrant_protocol(self) -> str:
        return "https" if self.QDRANT_HTTPS else "http"

    @property
    def qdrant_url(self) -> str:
        return f"{self.qdrant_protocol}://{self.QDRANT_HOST}:{self.QDRANT_PORT}"


settings = Settings()
