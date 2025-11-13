# 📚 Complete Documentation: Czech Legal RAG System

## Table of Contents
1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Project Structure](#project-structure)
4. [Core Components](#core-components)
5. [API Endpoints](#api-endpoints)
6. [Configuration](#configuration)
7. [Deployment](#deployment)
8. [Development Guide](#development-guide)
9. [Troubleshooting](#troubleshooting)
10. [Security](#security)

---

## Project Overview

### What is This?

A **Retrieval-Augmented Generation (RAG)** system for Czech legal case analysis that combines:
- **Vector search** via Qdrant for finding relevant court cases
- **Perplexity Sonar** for general legal knowledge
- **GPT-4o Mini** for case-based legal reasoning

### Key Features

✅ **Dual-mode answering:**
- Sonar provides general legal context with web citations
- GPT-4o analyzes specific Czech court cases from Qdrant

✅ **Vector similarity search:**
- Semantic search using multilingual embeddings
- Returns most relevant cases based on question context

✅ **Streaming responses:**
- Real-time streaming for better UX
- Server-Sent Events (SSE) for progressive rendering

✅ **Citation tracking:**
- Captures sources from Perplexity Sonar
- References specific court decisions (ECLI, case numbers)

---

## Architecture

### High-Level Flow

```
┌─────────────┐
│   Client    │
│   Request   │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│         FastAPI Router              │
│  /legal-query  /search-cases  etc.  │
└──────┬──────────────────────────────┘
       │
       ├──────────────┬─────────────────┬──────────────┐
       ▼              ▼                 ▼              ▼
┌──────────┐   ┌──────────┐     ┌──────────┐   ┌──────────┐
│ Perplexity│   │   GPT-4o │     │  Qdrant  │   │Sentence  │
│   Sonar   │   │   Mini   │     │  Vector  │   │Transform.│
│  Service  │   │  Service │     │    DB    │   │  Service │
└──────────┘   └──────────┘     └──────────┘   └──────────┘
       │              │                 │              │
       └──────────────┴─────────────────┴──────────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │   Response   │
                    │  Aggregator  │
                    └──────────────┘
```

### Design Pattern

**Service-Oriented Architecture** with clear separation:
- **Routers**: Handle HTTP requests/responses
- **Services**: Business logic (LLM calls, DB queries)
- **Models**: Data validation and schema
- **Utils**: Helper functions
- **Config**: Centralized configuration

---

## Project Structure

```
fastapi_RAG/
│
├── app/                          # Main application package
│   ├── __init__.py              # Package initializer
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                # Configuration management
│   ├── models.py                # Pydantic data models
│   │
│   ├── routers/                 # API route handlers
│   │   ├── __init__.py
│   │   ├── health.py           # Health check endpoint
│   │   ├── legal.py            # Legal query endpoints
│   │   └── search.py           # Case search endpoints
│   │
│   ├── services/                # Business logic layer
│   │   ├── __init__.py
│   │   ├── embedding.py        # Text embedding generation
│   │   ├── llm.py              # LLM interactions (Sonar, GPT)
│   │   └── qdrant.py           # Vector database operations
│   │
│   └── utils/                   # Utility functions
│       ├── __init__.py
│       └── formatters.py       # Data formatting helpers
│
├── .env                         # Environment variables (NOT in git)
├── .gitignore                   # Git ignore rules
├── requirements.txt             # Python dependencies
├── railway.json                 # Railway deployment config
├── README.md                    # Project documentation
└── LICENSE.md                   # MIT License
```

---

## Core Components

### 1. Configuration (`app/config.py`)

**Purpose:** Centralized configuration management using environment variables.

```python
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

    @property
    def qdrant_protocol(self) -> str:
        return "https" if self.QDRANT_HTTPS else "http"

    @property
    def qdrant_url(self) -> str:
        return f"{self.qdrant_protocol}://{self.QDRANT_HOST}:{self.QDRANT_PORT}"
```

**Key Features:**
- ✅ Type hints for all settings
- ✅ Default values for local development
- ✅ Computed properties for derived URLs
- ✅ Environment-based configuration (12-factor app)

**Environment Variables:**
| Variable | Description | Example |
|----------|-------------|---------|
| `OPENROUTER_API_KEY` | OpenRouter API key | `sk-or-v1-...` |
| `QDRANT_HOST` | Qdrant server hostname | `qdrant.railway.internal` |
| `QDRANT_PORT` | Qdrant server port | `6333` |
| `QDRANT_API_KEY` | Qdrant authentication key | `eyJh...` |
| `QDRANT_HTTPS` | Use HTTPS for Qdrant | `True` or `False` |
| `QDRANT_COLLECTION` | Collection name | `czech_court_decisions_rag` |
| `PORT` | Server port | `8000` |
| `HOST` | Server host | `0.0.0.0` |

---

### 2. Data Models (`app/models.py`)

**Purpose:** Pydantic models for request/response validation and serialization.

#### `QueryRequest`
```python
class QueryRequest(BaseModel):
    question: str          # User's legal question
    top_k: int = 5        # Number of cases to retrieve (default: 5)
```

**Usage:**
```python
# POST /legal-query
{
    "question": "Jaké jsou podmínky pro náhradu škody?",
    "top_k": 3
}
```

#### `CaseResult`
```python
class CaseResult(BaseModel):
    case_number: str                      # e.g., "25 Cdo 1234/2023"
    court: str                            # e.g., "Nejvyšší soud"
    judge: Optional[str] = None           # Judge name
    subject: str                          # Case subject/summary
    date_issued: Optional[str] = None     # YYYY-MM-DD
    date_published: Optional[str] = None  # YYYY-MM-DD
    ecli: Optional[str] = None           # ECLI identifier
    keywords: list[str] = []             # Legal keywords
    legal_references: list[str] = []     # § references
    source_url: Optional[str] = None     # Original source URL
    relevance_score: float               # Cosine similarity (0-1)
```

**Example:**
```json
{
    "case_number": "25 Cdo 1234/2023",
    "court": "Nejvyšší soud",
    "judge": "JUDr. Jan Novák",
    "subject": "Náhrada škody způsobené dopravní nehodou",
    "date_issued": "2023-05-15",
    "ecli": "ECLI:CZ:NS:2023:25.CDO.1234.2023.1",
    "keywords": ["náhrada škody", "dopravní nehoda"],
    "legal_references": ["§ 2910 ObčZ", "§ 2951 ObčZ"],
    "source_url": "https://nsoud.cz/...",
    "relevance_score": 0.8542
}
```

#### `LegalQueryResponse`
```python
class LegalQueryResponse(BaseModel):
    sonar_answer: str                     # Perplexity's answer
    sonar_source: str                     # "Perplexity Sonar via OpenRouter"
    sonar_citations: list[str] = []       # Web source URLs
    case_based_answer: str                # GPT answer based on cases
    supporting_cases: list[CaseResult]    # Relevant cases from Qdrant
```

**Example:**
```json
{
    "sonar_answer": "Podle českého práva...",
    "sonar_source": "Perplexity Sonar via OpenRouter",
    "sonar_citations": [
        "https://www.zakonyprolidi.cz/cs/2012-89",
        "https://nsoud.cz/judikatura/..."
    ],
    "case_based_answer": "Na základě rozhodnutí NS 25 Cdo...",
    "supporting_cases": [...]
}
```

---

### 3. Embedding Service (`app/services/embedding.py`)

**Purpose:** Convert text to 384-dimensional vectors for semantic search.

```python
embedding_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

async def get_embedding(text: str) -> Optional[list[float]]:
    """
    Get embedding using sentence transformers
    Must match the model used for Qdrant storage
    """
    try:
        embedding = embedding_model.encode(text).tolist()
        print(f"Vektorové vyjádření generováno: {len(embedding)} dimenzí")
        return embedding
    except Exception as e:
        print(f"Chyba pri generovani vektoru: {str(e)}")
        return None
```

**Model Details:**
- **Name:** `paraphrase-multilingual-MiniLM-L12-v2`
- **Dimensions:** 384
- **Languages:** 50+ including Czech
- **Use case:** Sentence similarity, semantic search
- **Source:** Hugging Face

**Why This Model?**
✅ Excellent Czech language support  
✅ Balanced performance/size  
✅ Fast inference (~50ms per query)  
✅ Proven for legal domain

**Important:** This model MUST match the one used to create embeddings in Qdrant.

---

### 4. Qdrant Service (`app/services/qdrant.py`)

**Purpose:** Vector database operations for case retrieval.

#### Main Function: `get_cases_from_qdrant()`

```python
async def get_cases_from_qdrant(
    question: str, 
    top_k: int
) -> list[CaseResult]:
    """
    Search Qdrant for most relevant cases using sentence transformers
    
    Args:
        question: User's legal query
        top_k: Number of cases to return
        
    Returns:
        List of CaseResult objects sorted by relevance
    """
```

**Process Flow:**
1. Convert question to 384-dim vector via `get_embedding()`
2. Send vector to Qdrant `/points/search` endpoint
3. Receive top_k most similar case vectors
4. Extract payloads and convert to `CaseResult` objects
5. Return sorted by relevance score

**API Call:**
```python
response = await client.post(
    f"{settings.qdrant_url}/collections/{settings.QDRANT_COLLECTION}/points/search",
    headers={"api-key": settings.QDRANT_API_KEY},
    json={
        "vector": vector,        # 384-dim float array
        "limit": top_k,          # e.g., 5
        "with_payload": True,    # Return full case data
    },
    timeout=10.0,
)
```

**Response Structure:**
```json
{
    "result": [
        {
            "id": "uuid-here",
            "score": 0.8542,
            "payload": {
                "case_number": "25 Cdo 1234/2023",
                "court": "Nejvyšší soud",
                ...
            }
        }
    ]
}
```

#### Debug Function: `debug_qdrant_connection()`

```python
async def debug_qdrant_connection() -> dict:
    """
    Debug Qdrant connection and return status
    Useful for troubleshooting deployment issues
    """
```

**Returns:**
```json
{
    "status": 200,
    "url": "http://qdrant.railway.internal:6333",
    "text": "{\"result\":{\"collections\":[...]}}",
    "headers": {...}
}
```

---

### 5. LLM Service (`app/services/llm.py`)

**Purpose:** Interact with OpenRouter API for Perplexity Sonar and GPT-4o Mini.

#### Function: `get_openai_client()`

```python
def get_openai_client() -> OpenAI:
    """Get configured OpenAI client for OpenRouter"""
    return OpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,  # OpenRouter proxy
    )
```

**Why OpenRouter?**
- Single API for multiple LLM providers
- Pay-per-use pricing
- Automatic failover
- Unified interface

#### Function: `get_sonar_answer()`

```python
async def get_sonar_answer(question: str) -> tuple[str, list[str]]:
    """
    Get answer from Perplexity Sonar with citations
    
    Returns: (answer_text, citations_list)
    """
    client = get_openai_client()
    
    sonar_response = client.chat.completions.create(
        model="perplexity/sonar",
        messages=[{"role": "user", "content": question}],
        stream=False,  # Need full response for citations
    )
    
    sonar_answer = sonar_response.choices[0].message.content or ""
    
    # Extract citations from response metadata
    sonar_citations = getattr(sonar_response, "citations", [])
    if not sonar_citations:
        search_results = getattr(sonar_response, "search_results", [])
        sonar_citations = [
            result.get("url", "") 
            for result in search_results 
            if result.get("url")
        ]
    
    return sonar_answer, sonar_citations
```

**Why Perplexity Sonar?**
✅ Real-time web search  
✅ Automatic source citations  
✅ Good for current legal info  
✅ Complements case-based search

#### Function: `answer_based_on_cases()`

```python
async def answer_based_on_cases(
    question: str, 
    cases: list[CaseResult], 
    client: OpenAI
) -> str:
    """
    GPT-4o answers the question based on all case data with citations
    
    Args:
        question: User's legal query
        cases: List of relevant cases from Qdrant
        client: OpenAI client instance
        
    Returns:
        Detailed answer in Czech referencing specific cases
    """
```

**System Prompt (Czech Legal Expert):**
```python
SYSTEM_PROMPT = """Jste právní expert se specialistem na české právo. 
Odpovídejte na otázky uživatele VÝHRADNĚ na základě poskytnutých 
rozhodnutí českých soudů. 

Vaše odpověď musí obsahovat:
1. Přímou odpověď na položenou otázku
2. Citace všech relevantních rozhodnutí:
   - Spisová značka rozsudku
   - Název soudu
   - Datum vydání
   - ECLI reference
   - Relevantní právní předpisy (§ citace)
   - Klíčové právní principy

Odpověď musí být:
- Strukturovaná a logická
- Psaná v češtině
- Soustředěna výhradně na poskytnutá rozhodnutí
- Bez generalizací mimo základnu rozhodnutí
- S přesnými citacemi
"""
```

**Model Parameters:**
```python
response = client.chat.completions.create(
    model="openai/gpt-4o-mini",
    temperature=0.5,       # Balanced creativity/consistency
    max_tokens=2000,       # ~1500 words
    messages=[...]
)
```

**Why GPT-4o Mini?**
✅ Excellent reasoning capabilities  
✅ Cost-effective ($0.15/M tokens)  
✅ Fast response times  
✅ Strong multilingual support (Czech)

#### Function: `answer_based_on_cases_stream()`

```python
async def answer_based_on_cases_stream(
    question: str, 
    cases: list[CaseResult], 
    client: OpenAI
):
    """
    Stream GPT-4o answer token-by-token
    
    Yields: Individual text chunks as they're generated
    """
    stream = client.chat.completions.create(
        model="openai/gpt-4o-mini",
        messages=[...],
        stream=True,  # Enable streaming
    )
    
    for chunk in stream:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
```

**Streaming Benefits:**
- Faster perceived response time
- Better UX for long answers
- Reduced memory usage
- Real-time user feedback

---

### 6. Formatters (`app/utils/formatters.py`)

**Purpose:** Convert case data to GPT-readable context.

```python
def format_cases_for_context(cases: list[CaseResult]) -> str:
    """
    Format all cases for GPT context without truncation
    
    Args:
        cases: List of CaseResult objects
        
    Returns:
        Formatted string with all case details
    """
    context = ""
    for i, case in enumerate(cases, 1):
        context += f"""
ROZHODNUTÍ {i}:
Spisová značka: {case.case_number}
Soud: {case.court}
Soudce: {case.judge or "Neuvedeno"}
Datum vydání: {case.date_issued}
Datum publikace: {case.date_published}
ECLI: {case.ecli}
Předmět sporu: {case.subject}
Klíčová slova: {', '.join(case.keywords) if case.keywords else 'Neuvedena'}
Právní předpisy: {', '.join(case.legal_references) if case.legal_references else 'Neuvedeny'}
Zdroj: {case.source_url}
Relevance: {case.relevance_score}
---
"""
    return context
```

**Example Output:**
```
ROZHODNUTÍ 1:
Spisová značka: 25 Cdo 1234/2023
Soud: Nejvyšší soud
Soudce: JUDr. Jan Novák
Datum vydání: 2023-05-15
Datum publikace: 2023-06-01
ECLI: ECLI:CZ:NS:2023:25.CDO.1234.2023.1
Předmět sporu: Náhrada škody způsobené dopravní nehodou
Klíčová slova: náhrada škody, dopravní nehoda, objektivní odpovědnost
Právní předpisy: § 2910 ObčZ, § 2951 ObčZ
Zdroj: https://nsoud.cz/Judikatura/...
Relevance: 0.8542
---

ROZHODNUTÍ 2:
...
```

**Why This Format?**
✅ Structured and consistent  
✅ Easy for GPT to parse  
✅ All relevant metadata included  
✅ No truncation (full context)

---

## API Endpoints

### 1. Health Check

#### `GET /health`

**Purpose:** Verify service is running.

**Request:**
```bash
curl http://localhost:8000/health
```

**Response:**
```json
{
    "status": "ok",
    "timestamp": "2025-11-13T04:00:00.000000"
}
```

**Use Cases:**
- Load balancer health checks
- Monitoring/alerting
- Deployment verification

---

### 2. Legal Query (Non-Streaming)

#### `POST /legal-query`

**Purpose:** Complete legal analysis with Sonar + case-based answers.

**Request:**
```bash
curl -X POST http://localhost:8000/legal-query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Jaké jsou podmínky pro náhradu škody při dopravní nehodě?",
    "top_k": 5
  }'
```

**Response:**
```json
{
    "sonar_answer": "Podle českého práva existuje několik podmínek...",
    "sonar_source": "Perplexity Sonar via OpenRouter",
    "sonar_citations": [
        "https://www.zakonyprolidi.cz/cs/2012-89",
        "https://nsoud.cz/Judikatura/judikatura_ns.nsf/..."
    ],
    "case_based_answer": "Na základě rozhodnutí Nejvyššího soudu...",
    "supporting_cases": [
        {
            "case_number": "25 Cdo 1234/2023",
            "court": "Nejvyšší soud",
            "subject": "Náhrada škody při dopravní nehodě",
            "relevance_score": 0.8542,
            ...
        }
    ]
}
```

**Processing Flow:**
1. **Stage 1:** Query Perplexity Sonar → Get general answer + web citations
2. **Stage 2:** Query Qdrant → Get top_k relevant cases
3. **Stage 3:** Feed cases to GPT-4o → Get case-specific analysis
4. **Stage 4:** Combine all results → Return complete response

**Response Time:** ~8-15 seconds (depends on case complexity)

---

### 3. Legal Query (Streaming)

#### `GET /legal-query-stream?question=...&top_k=5`

**Purpose:** Stream responses for better UX.

**Request:**
```bash
curl -N http://localhost:8000/legal-query-stream?question=Jaké%20jsou%20podmínky&top_k=5
```

**Response (Server-Sent Events):**
```
data: {"type": "sonar_start"}

data: {"type": "sonar_chunk", "content": "Podle"}

data: {"type": "sonar_chunk", "content": " českého"}

data: {"type": "sonar_chunk", "content": " práva"}

data: {"type": "sonar_citations", "citations": ["https://..."]}

data: {"type": "sonar_end"}

data: {"type": "cases_fetching"}

data: {"type": "gpt_answer_start"}

data: {"type": "gpt_answer_chunk", "content": "Na"}

data: {"type": "gpt_answer_chunk", "content": " základě"}

data: {"type": "gpt_answer_end"}

data: {"type": "cases_start"}

data: {"type": "case", "case_number": "25 Cdo 1234/2023", ...}

data: {"type": "done"}
```

**Event Types:**
| Type | Description | Data |
|------|-------------|------|
| `sonar_start` | Sonar answer begins | None |
| `sonar_chunk` | Sonar text chunk | `{content: string}` |
| `sonar_citations` | Sonar sources | `{citations: string[]}` |
| `sonar_end` | Sonar complete | None |
| `cases_fetching` | Querying Qdrant | None |
| `gpt_answer_start` | GPT answer begins | None |
| `gpt_answer_chunk` | GPT text chunk | `{content: string}` |
| `gpt_answer_end` | GPT complete | None |
| `cases_start` | Case list begins | None |
| `case` | Individual case | `CaseResult` object |
| `done` | All complete | None |
| `error` | Error occurred | `{message: string}` |

**Frontend Example (JavaScript):**
```javascript
const eventSource = new EventSource('/legal-query-stream?question=...');

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    switch(data.type) {
        case 'sonar_chunk':
            appendToSonarDiv(data.content);
            break;
        case 'gpt_answer_chunk':
            appendToGptDiv(data.content);
            break;
        case 'case':
            renderCase(data);
            break;
        case 'done':
            eventSource.close();
            break;
    }
};
```

---

### 4. Direct Case Search

#### `GET /search-cases?question=...&top_k=5`

**Purpose:** Vector search only (no LLM processing).

**Request:**
```bash
curl "http://localhost:8000/search-cases?question=náhrada%20škody&top_k=3"
```

**Response:**
```json
{
    "query": "náhrada škody",
    "total_results": 3,
    "cases": [
        {
            "case_number": "25 Cdo 1234/2023",
            "court": "Nejvyšší soud",
            "subject": "Náhrada škody při dopravní nehodě",
            "date_issued": "2023-05-15",
            "ecli": "ECLI:CZ:NS:2023:25.CDO.1234.2023.1",
            "keywords": ["náhrada škody", "dopravní nehoda"],
            "legal_references": ["§ 2910 ObčZ", "§ 2951 ObčZ"],
            "source_url": "https://nsoud.cz/...",
            "relevance_score": 0.8542
        },
        ...
    ]
}
```

**Use Cases:**
- Quick case lookup
- Building custom UIs
- Testing Qdrant connection
- Debugging vector search

**Response Time:** ~100-500ms (vector search only)

---

### 5. Case Search (Streaming)

#### `GET /search-cases-stream?question=...&top_k=5`

**Purpose:** Stream case results one-by-one.

**Response (SSE):**
```
data: {"type": "search_start"}

data: {"type": "search_info", "query": "náhrada škody", "total_results": 3}

data: {"type": "case_result", "index": 1, "case_number": "25 Cdo 1234/2023", ...}

data: {"type": "case_result", "index": 2, "case_number": "30 Cdo 5678/2023", ...}

data: {"type": "done"}
```

---

### 6. Debug Qdrant

#### `GET /debug/qdrant`

**Purpose:** Troubleshoot Qdrant connection.

**Request:**
```bash
curl http://localhost:8000/debug/qdrant
```

**Response (Success):**
```json
{
    "status": 200,
    "url": "http://qdrant.railway.internal:6333",
    "text": "{\"result\":{\"collections\":[{\"name\":\"czech_court_decisions_rag\"}]}}",
    "headers": {
        "content-type": "application/json",
        "content-length": "123"
    }
}
```

**Response (Error):**
```json
{
    "error": "Connection refused",
    "url": "http://qdrant.railway.internal:6333",
    "type": "ConnectionError"
}
```

**Use Cases:**
- Deployment troubleshooting
- Network diagnostics
- Collection verification

---

## Configuration

### Environment Variables

Create `.env` file in project root:

```bash
# OpenRouter (for Perplexity Sonar & GPT-4o)
OPENROUTER_API_KEY=sk-or-v1-your-key-here

# Qdrant Vector Database
QDRANT_HOST=qdrant.railway.internal    # or localhost for local
QDRANT_PORT=6333
QDRANT_API_KEY=your-qdrant-api-key
QDRANT_HTTPS=False                      # True for production
QDRANT_COLLECTION=czech_court_decisions_rag

# Server
PORT=8000
HOST=0.0.0.0
```

### Local Development

```bash
# For local Qdrant Docker instance
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_HTTPS=False
QDRANT_API_KEY=  # Leave empty if no auth
```

### Production (Railway)

```bash
# Use Railway's internal networking
QDRANT_HOST=qdrant.railway.internal
QDRANT_PORT=6333
QDRANT_HTTPS=True  # If Qdrant is public
```

**Important:** Never commit `.env` to git!

---

## Deployment

### Local Development

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Create .env file (see Configuration section)

# 3. Run with uvicorn (development mode)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 4. Test health endpoint
curl http://localhost:8000/health
```

### Railway Deployment

#### Prerequisites
- Railway account
- Railway CLI installed
- Git repository

#### Step 1: Initialize Railway Project

```bash
# Login to Railway
railway login

# Initialize project
railway init

# Link to existing project (if applicable)
railway link
```

#### Step 2: Set Environment Variables

```bash
railway variables set OPENROUTER_API_KEY=sk-or-v1-...
railway variables set QDRANT_HOST=qdrant.railway.internal
railway variables set QDRANT_PORT=6333
railway variables set QDRANT_API_KEY=your-key
railway variables set QDRANT_HTTPS=False
railway variables set QDRANT_COLLECTION=czech_court_decisions_rag
```

#### Step 3: Configure `railway.json`

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
  }
}
```

#### Step 4: Deploy

```bash
# Commit changes
git add .
git commit -m "Deploy to Railway"

# Push to deploy
git push origin main

# Or use Railway CLI
railway up
```

#### Step 5: Verify Deployment

```bash
# Get deployment URL
railway domain

# Test health endpoint
curl https://your-app.railway.app/health
```

### Docker Deployment (Alternative)

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ ./app/

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:

```bash
# Build image
docker build -t czech-legal-rag .

# Run container
docker run -p 8000:8000 --env-file .env czech-legal-rag
```

---

## Development Guide

### Setting Up Development Environment

```bash
# 1. Clone repository
git clone <repository-url>
cd fastapi_RAG

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env file
cp .env.example .env  # Edit with your credentials

# 5. Run local Qdrant (optional)
docker run -p 6333:6333 qdrant/qdrant

# 6. Start development server
uvicorn app.main:app --reload
```

### Project Structure Guidelines

**Adding New Endpoints:**
1. Create router in `app/routers/`
2. Import in `app/main.py`
3. Use `app.include_router()`

**Adding New Services:**
1. Create service in `app/services/`
2. Import in relevant router
3. Follow async/await patterns

**Adding New Models:**
1. Define Pydantic model in `app/models.py`
2. Use for request/response validation

### Code Style

**Follow PEP 8:**
```bash
# Install tools
pip install black isort flake8

# Format code
black app/
isort app/

# Check style
flake8 app/
```

**Type Hints:**
```python
# Always use type hints
async def get_cases(question: str, top_k: int) -> list[CaseResult]:
    ...

# Use Optional for nullable values
from typing import Optional
def process(value: Optional[str] = None) -> str:
    ...
```

**Docstrings:**
```python
def format_cases(cases: list[CaseResult]) -> str:
    """
    Format cases for GPT context.
    
    Args:
        cases: List of case results from Qdrant
        
    Returns:
        Formatted string with all case details
    """
```

### Testing

Create `tests/` directory:

```bash
tests/
├── __init__.py
├── test_models.py
├── test_services.py
└── test_endpoints.py
```

**Example Test:**
```python
# tests/test_endpoints.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_legal_query():
    response = client.post(
        "/legal-query",
        json={"question": "Test otázka", "top_k": 3}
    )
    assert response.status_code == 200
    assert "sonar_answer" in response.json()
```

Run tests:
```bash
pip install pytest pytest-asyncio
pytest tests/
```

---

## Troubleshooting

### Common Issues

#### 1. **Import Errors**

**Problem:**
```
ModuleNotFoundError: No module named 'app'
```

**Solution:**
```bash
# Run from project root
cd fastapi_RAG
python -m uvicorn app.main:app --reload

# Or use the module directly
python -m app.main
```

#### 2. **Qdrant Connection Fails**

**Problem:**
```
Connection refused to Qdrant
```

**Solutions:**
```bash
# Check Qdrant is running
curl http://localhost:6333/collections

# Verify QDRANT_HOST in .env
# For local: localhost
# For Railway: qdrant.railway.internal

# Check debug endpoint
curl http://localhost:8000/debug/qdrant
```

#### 3. **OpenRouter API Errors**

**Problem:**
```
401 Unauthorized
```

**Solutions:**
```bash
# Verify API key
echo $OPENROUTER_API_KEY

# Test manually
curl https://openrouter.ai/api/v1/models \
  -H "Authorization: Bearer $OPENROUTER_API_KEY"

# Check balance
# https://openrouter.ai/credits
```

#### 4. **Embedding Model Download**

**Problem:**
```
Downloading paraphrase-multilingual-MiniLM-L12-v2...
```

**Solution:**
- First run downloads ~50MB model
- Takes 1-2 minutes
- Cached in `~/.cache/huggingface/`
- Subsequent runs are instant

#### 5. **Memory Issues**

**Problem:**
```
OOM (Out of Memory) error
```

**Solutions:**
```bash
# Reduce top_k
{"question": "...", "top_k": 3}  # Instead of 10

# Use streaming endpoints
GET /legal-query-stream

# Increase Railway memory
# Dashboard → Settings → Resources → 512MB+
```

---

## Security

### API Key Management

**❌ NEVER do this:**
```python
# Hard-coding keys
OPENROUTER_API_KEY = "sk-or-v1-..."
```

**✅ Always do this:**
```python
# Use environment variables
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
```

### .env File Security

**Checklist:**
- [ ] `.env` is in `.gitignore`
- [ ] Never commit `.env` to git
- [ ] Use different keys for dev/prod
- [ ] Rotate keys regularly
- [ ] Use Railway secrets for production

### Input Validation

**All inputs validated via Pydantic:**
```python
class QueryRequest(BaseModel):
    question: str          # Required, non-empty
    top_k: int = 5        # Default value, int only
```

### CORS Configuration (if needed)

```python
# app/main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Rate Limiting (recommended)

```bash
pip install slowapi
```

```python
# app/main.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(429, _rate_limit_exceeded_handler)

@app.post("/legal-query")
@limiter.limit("10/minute")
async def legal_query(request: Request, query: QueryRequest):
    ...
```

---

## Performance Optimization

### Caching Embeddings

```python
# Add to app/services/embedding.py
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_embedding_cached(text: str) -> list[float]:
    return embedding_model.encode(text).tolist()
```

### Connection Pooling

```python
# app/services/qdrant.py
import httpx

# Reuse client
http_client = httpx.AsyncClient(
    timeout=10.0,
    limits=httpx.Limits(max_connections=100)
)
```

### Async Best Practices

```python
# ✅ Good: Proper async/await
async def get_data():
    result = await db.query()
    return result

# ❌ Bad: Blocking in async
async def get_data():
    result = time.sleep(1)  # Blocks event loop!
    return result
```

---

## Monitoring & Logging

### Structured Logging

```python
# app/main.py
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

@app.post("/legal-query")
async def legal_query(request: QueryRequest):
    logger.info(f"Legal query received: {request.question[:50]}...")
    # ...
```

### Health Monitoring

```python
# Add detailed health check
@app.get("/health/detailed")
async def detailed_health():
    qdrant_status = await check_qdrant()
    openrouter_status = await check_openrouter()
    
    return {
        "status": "ok" if all([qdrant_status, openrouter_status]) else "degraded",
        "services": {
            "qdrant": qdrant_status,
            "openrouter": openrouter_status
        },
        "timestamp": datetime.now().isoformat()
    }
```

---

## Future Enhancements

### Potential Features

1. **Authentication & Authorization**
   - User accounts
   - API key management
   - Usage quotas

2. **Enhanced Search**
   - Filter by court
   - Filter by date range
   - Filter by legal area

3. **Case Analytics**
   - Trend analysis
   - Citation networks
   - Judge statistics

4. **Multi-language Support**
   - English interface
   - Slovak legal cases

5. **Export Features**
   - PDF generation
   - Word documents
   - Citation export

6. **Advanced RAG**
   - Reranking
   - Hybrid search (keyword + vector)
   - Multi-hop reasoning

---

## Appendix

### Glossary

| Term | Definition |
|------|------------|
| **RAG** | Retrieval-Augmented Generation - combining search with LLM |
| **Vector Embedding** | Numerical representation of text (384-dim in this project) |
| **Cosine Similarity** | Measure of similarity between vectors (0-1 score) |
| **ECLI** | European Case Law Identifier |
| **SSE** | Server-Sent Events - one-way streaming from server to client |
| **LLM** | Large Language Model (GPT-4o, Sonar) |
| **Qdrant** | Vector database for similarity search |

### Useful Links

- **FastAPI Docs:** https://fastapi.tiangolo.com/
- **Qdrant Docs:** https://qdrant.tech/documentation/
- **OpenRouter:** https://openrouter.ai/docs
- **Sentence Transformers:** https://www.sbert.net/
- **Railway Docs:** https://docs.railway.app/

### File Size Reference

| Component | Size |
|-----------|------|
| Embedding model | ~50 MB |
| FastAPI app | ~5 MB |
| Total dependencies | ~500 MB |
| Docker image | ~800 MB |

---

## Conclusion

This documentation covers the complete Czech Legal RAG system. For questions or contributions, please refer to the project's GitHub repository or contact the maintainers.

**Happy coding! 🚀**