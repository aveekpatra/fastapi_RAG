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
    
    # Collection configuration - 4 collections total
    # Original collection (384 dim, paraphrase-multilingual-MiniLM-L12-v2)
    QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "czech_court_decisions_rag")
    
    # New collections (256 dim, Seznam/retromae-small-cs)
    QDRANT_CONSTITUTIONAL_COURT: str = os.getenv("QDRANT_CONSTITUTIONAL_COURT", "czech_constitutional_court")
    QDRANT_SUPREME_COURT: str = os.getenv("QDRANT_SUPREME_COURT", "czech_supreme_court")
    QDRANT_SUPREME_ADMIN_COURT: str = os.getenv("QDRANT_SUPREME_ADMIN_COURT", "czech_supreme_administrative_court")

    # Server configuration
    PORT: int = int(os.getenv("PORT", "8000"))
    HOST: str = os.getenv("HOST", "0.0.0.0")

    # API security
    API_KEY: str = os.getenv("API_KEY", "")
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")

    # Qdrant retry configuration - increased for large collections
    QDRANT_MAX_RETRIES: int = int(os.getenv("QDRANT_MAX_RETRIES", "3"))
    QDRANT_INITIAL_TIMEOUT: int = int(os.getenv("QDRANT_INITIAL_TIMEOUT", "120"))  # 2 minutes per search

    # LangChain configuration
    LANGCHAIN_TRACING_V2: bool = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    LANGCHAIN_API_KEY: str = os.getenv("LANGCHAIN_API_KEY", "")
    LANGCHAIN_PROJECT: str = os.getenv("LANGCHAIN_PROJECT", "czech-legal-assistant")

    # GPT-5-mini configuration (400K context, optimized for reasoning)
    LLM_MODEL: str = os.getenv("LLM_MODEL", "openai/gpt-5-mini")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.15"))  # Balanced for understanding and precision
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "32000"))  # GPT-5-mini supports 400K context
    LLM_TIMEOUT: float = float(os.getenv("LLM_TIMEOUT", "600.0"))  # 10 min for reasoning/thinking
    LLM_THINKING_BUDGET: int = int(os.getenv("LLM_THINKING_BUDGET", "10000"))  # Thinking tokens budget
    
    # Fast model for simple tasks (query generation, reranking)
    FAST_MODEL: str = os.getenv("FAST_MODEL", "openai/gpt-5-nano")  # Ultra-fast for simple tasks
    
    # Reranking model (for quality improvement)
    RERANK_MODEL: str = os.getenv("RERANK_MODEL", "openai/gpt-5-nano")
    
    # Embedding models
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
    SEZNAM_EMBEDDING_MODEL: str = os.getenv("SEZNAM_EMBEDDING_MODEL", "Seznam/retromae-small-cs")
    SEZNAM_VECTOR_SIZE: int = 256

    # e-Sbírka API configuration
    ESBIRKA_API_KEY: str = os.getenv("ESBIRKA_API_KEY", "")
    ESBIRKA_API_ENDPOINT: str = os.getenv("ESBIRKA_API_ENDPOINT", "https://opendata.eselpoint.cz/api/v1")

    # RAG Pipeline configuration
    NUM_GENERATED_QUERIES: int = 5  # Generate up to 5 query variants (dynamic based on complexity)
    RESULTS_PER_QUERY: int = 15  # Get more results for better reranking
    FINAL_TOP_K: int = 10  # Return top 10 after reranking
    RERANK_TOP_K: int = 25  # Rerank top 25 candidates
    
    # Quality thresholds
    MIN_RELEVANCE_SCORE: float = 0.3  # Minimum score to include (cast wider net)
    HIGH_RELEVANCE_THRESHOLD: float = 0.7  # High confidence threshold
    
    # Search optimization (simplified, robust defaults)
    ENABLE_ENTITY_EXTRACTION: bool = os.getenv("ENABLE_ENTITY_EXTRACTION", "true").lower() == "true"
    ENABLE_DOCUMENT_AGGREGATION: bool = os.getenv("ENABLE_DOCUMENT_AGGREGATION", "true").lower() == "true"

    @property
    def qdrant_protocol(self) -> str:
        return "https" if self.QDRANT_HTTPS else "http"

    @property
    def qdrant_url(self) -> str:
        return f"{self.qdrant_protocol}://{self.QDRANT_HOST}:{self.QDRANT_PORT}"


settings = Settings()
