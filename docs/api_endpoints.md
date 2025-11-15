# API Endpoints Documentation

This document describes the available endpoints in the Czech Legal Assistant API.

## Authentication

All endpoints require authentication using an API key. The API key should be included in requests in one of the following ways:

1. **Bearer Token (Recommended)**: Include the API key in the Authorization header as a Bearer token:
   ```
   Authorization: Bearer your_secure_api_key_here
   ```

2. **Query Parameter**: Include the API key as a query parameter named `api_key`:
   ```
   /web-search?question=...&api_key=your_secure_api_key_here
   ```

The API key is configured in the .env file using the `API_KEY` variable. If no API key is set in the configuration, the endpoints will not require authentication (useful for development).

## Health Check

### GET `/health`
Returns the health status of the API.

**Response:**
```json
{
  "status": "ok",
  "timestamp": "2023-11-20T12:34:56.789Z"
}
```

## Legal Search Endpoints

### Web Search (Sonar Only)

#### POST `/web-search`
Performs a web search using Perplexity Sonar without case information.

**Request Headers:**
```
Authorization: Bearer your_secure_api_key_here
```

**Request:**
```json
{
  "question": "Jaké jsou právní důsledky neplacení nájmu?",
  "top_k": 5
}
```

**Response:**
```json
{
  "answer": "Web search answer...",
  "source": "Perplexity Sonar via OpenRouter",
  "citations": ["https://example.com/law1", "https://example.com/law2"]
}
```

#### GET `/web-search-stream`
Streaming version of the web search endpoint.

**Query Parameters:**
- `question` (required): Legal question to search
- `top_k` (optional): Number of results (default: 5)
- `api_key` (optional): API key for authentication (alternative to Bearer token)

**Alternative Authentication Method:**
```
/web-search-stream?question=...&top_k=5&api_key=your_secure_api_key_here
```

**Event Stream Types:**
- `web_search_start`: Indicates the start of web search
- `answer_chunk`: Chunks of the answer text
- `citations`: Citations for the answer
- `web_search_end`: Indicates the end of web search
- `error`: Error information

### Case Search (Qdrant + GPT Only)

#### POST `/case-search`
Performs a case search using Qdrant and GPT without web search.

**Request Headers:**
```
Authorization: Bearer your_secure_api_key_here
```

**Request:**
```json
{
  "question": "Jaké jsou právní důsledky neplacení nájmu?",
  "top_k": 5
}
```

**Response:**
```json
{
  "answer": "Case-based answer...",
  "supporting_cases": [
    {
      "case_number": "20 C 123/2023",
      "court": "Okresní soud v Praze",
      "subject": "Nájemné a platby za služby",
      "relevance_score": 0.9123,
      ...
    }
  ]
}
```

#### GET `/case-search-stream`
Streaming version of the case search endpoint.

**Request Headers:**
```
Authorization: Bearer your_secure_api_key_here
```

**Query Parameters:**
- `question` (required): Legal question to search
- `top_k` (optional): Number of cases to retrieve (default: 5)
- `api_key` (optional): API key for authentication (alternative to Bearer token)

**Alternative Authentication Method:**
```
/search-cases-stream?question=...&top_k=5&api_key=your_secure_api_key_here
```

**Event Stream Types:**
- `case_search_start`: Indicates the start of case search
- `cases_fetching`: Indicates cases are being fetched from Qdrant
- `gpt_answer_start`: Indicates GPT answer generation is starting
- `answer_chunk`: Chunks of the GPT answer text
- `gpt_answer_end`: Indicates GPT answer generation is complete
- `cases_start`: Indicates case information will follow
- `case`: Individual case information
- `case_search_end`: Indicates the end of case search
- `error`: Error information

### Combined Search (Web + Case)

#### POST `/combined-search`
Performs both web search and case search, combining results.

**Request:**
```json
{
  "question": "Jaké jsou právní důsledky neplacení nájmu?",
  "top_k": 5
}
```

**Response:**
```json
{
  "web_answer": "Web search answer...",
  "web_source": "Perplexity Sonar via OpenRouter",
  "web_citations": ["https://example.com/law1", "https://example.com/law2"],
  "case_answer": "Case-based answer...",
  "supporting_cases": [
    {
      "case_number": "20 C 123/2023",
      "court": "Okresní soud v Praze",
      "subject": "Nájemné a platby za služby",
      "relevance_score": 0.9123,
      ...
    }
  ]
}
```

#### GET `/combined-search-stream`
Streaming version of the combined search endpoint.

**Query Parameters:**
- `question` (required): Legal question to search
- `top_k` (optional): Number of cases to retrieve (default: 5)

**Event Stream Types:**
- `web_search_start`: Indicates the start of web search
- `web_answer_chunk`: Chunks of the web answer text
- `web_citations`: Citations for the web answer
- `web_search_end`: Indicates the end of web search
- `case_search_start`: Indicates the start of case search
- `cases_fetching`: Indicates cases are being fetched from Qdrant
- `gpt_answer_start`: Indicates GPT answer generation is starting
- `case_answer_chunk`: Chunks of the GPT answer text
- `gpt_answer_end`: Indicates GPT answer generation is complete
- `cases_start`: Indicates case information will follow
- `case`: Individual case information
- `combined_search_end`: Indicates the end of combined search
- `error`: Error information

## Direct Case Search

### GET `/search-cases`
Direct vector search in Qdrant without AI processing, returning raw case information.

**Query Parameters:**
- `question` (required): Legal question to search
- `top_k` (optional): Number of cases to retrieve (default: 5)

**Response:**
```json
{
  "query": "Jaké jsou právní důsledky neplacení nájmu?",
  "total_results": 3,
  "cases": [
    {
      "case_number": "20 C 123/2023",
      "court": "Okresní soud v Praze",
      "subject": "Nájemné a platby za služby",
      "relevance_score": 0.9123,
      ...
    }
  ]
}
```

### GET `/search-cases-stream`
Streaming version of the direct case search.

**Query Parameters:**
- `question` (required): Legal question to search
- `top_k` (optional): Number of cases to retrieve (default: 5)

**Event Stream Types:**
- `search_start`: Indicates the start of search
- `search_info`: Information about the search (query, total results)
- `case_result`: Individual case information
- `done`: Indicates the end of search
- `error`: Error information

## Debug Endpoints

### GET `/debug/qdrant`
Debug endpoint to verify Qdrant connection status.

**Request Headers:**
```
Authorization: Bearer your_secure_api_key_here
```

**Response:**
```json
{
  "status": 200,
  "url": "http://localhost:6333",
  "text": "...",
  "headers": {...}
}
```
```

## Summary of Changes

I've successfully restructured the API to provide separate, dedicated endpoints for each search type as requested:

### 1. New Endpoint Structure
- `/web-search` - Sonar web search only
- `/case-search` - Qdrant + GPT search only
- `/combined-search` - Both web and case search together

Each endpoint has both a standard POST version and a streaming GET version.

### 2. Response Models
Created three new response models:
- `WebSearchResponse` - For web search only
- `CaseSearchResponse` - For case search only
- `CombinedSearchResponse` - For combined searches

### 3. Maintained Existing Functionality
- Kept the existing `/search-cases` endpoints for direct vector search
- Kept the health check and debug endpoints
- Preserved all streaming capabilities with appropriate event types

### 4. Benefits of This Structure
- **Security**: Each endpoint has a single responsibility
- **Maintainability**: Clear separation of concerns
- **Performance**: No conditional logic overhead
- **Flexibility**: Frontend can choose exactly which search types to use

The old `/legal-query` endpoint has been removed as requested, with its functionality now distributed across the new, more focused endpoints.

Is there anything else you'd like me to adjust in the implementation?