# Czech Legal Assistant API Documentation

## Overview
This API provides AI-powered legal search capabilities for Czech law using:
- **Web Search**: Perplexity Sonar for general legal information via OpenRouter
- **Case Search**: Czech court cases via Qdrant vector database with GPT analysis
- **Combined Search**: Both web and case-based answers in a single request

## Base URL
```
https://your-api-host.com
```

## Authentication
All endpoints require API key authentication except `/health`.

### Method 1: Bearer Token (Recommended)
```
Authorization: Bearer YOUR_API_KEY
```

### Method 2: Query Parameter
```
api_key=YOUR_API_KEY
```

### Data Models

#### Perplexity Sonar Response Format
The Perplexity Sonar API via OpenRouter returns responses in the following format:

**Base Response Structure**:
```json
{
  "id": "string - Unique identifier for the response",
  "object": "chat.completion",
  "created": "integer - Timestamp of response creation",
  "model": "string - Model name (e.g., 'perplexity/sonar')",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "string - Generated answer"
      },
      "finish_reason": "string - Reason for completion (e.g., 'stop')"
    }
  ],
  "usage": {
    "prompt_tokens": "integer - Number of input tokens",
    "completion_tokens": "integer - Number of output tokens",
    "total_tokens": "integer - Total tokens used",
    "search_context_size": "string - Size of search context (low/medium/high)",
    "cost": {
      "input_tokens_cost": "number - Cost for input tokens",
      "output_tokens_cost": "number - Cost for output tokens",
      "request_cost": "number - Cost for the request",
      "total_cost": "number - Total cost"
    }
  },
  "citations": [
    "string - URL of cited source"
  ],
  "search_results": [
    {
      "title": "string - Title of the search result",
      "url": "string - URL of the search result",
      "date": "string - Date of the content",
      "last_updated": "string - Last update date",
      "snippet": "string - Brief excerpt from the source"
    }
  ]
}
```

**Citations Handling**:
- Citations are returned both as a top-level `citations` array and within `search_results`
- Each citation is a complete URL to the source
- The number of citations varies based on the query complexity and available sources
- If citations are not available in the top-level field, they are extracted from `search_results`

### QueryRequest
Used for POST endpoints that accept a JSON body.

```json
{
  "question": "string (required) - Legal question to search",
  "top_k": "integer (optional, default: 5) - Number of cases to retrieve"
}
```

### CaseResult
Represents a single court case returned from the system.

```json
{
  "case_number": "string - Official case number",
  "court": "string - Name of the court",
  "judge": "string (optional) - Name of the presiding judge",
  "subject": "string - Subject matter of the case",
  "date_issued": "string (optional) - Date the decision was issued",
  "date_published": "string (optional) - Date the case was published",
  "ecli": "string (optional) - European Case Law Identifier",
  "keywords": "array of strings - Keywords associated with the case",
  "legal_references": "array of strings - Legal references cited in the case",
  "source_url": "string (optional) - URL to the full case document",
  "relevance_score": "float - Relevance score from 0 to 1, higher is more relevant"
}
```

## Endpoints

### 1. Health Check
Check API service status.

```
GET /health
```

**Authentication**: None required

**Response**:
```json
{
  "status": "string - Service status (e.g., 'ok')",
  "timestamp": "string - ISO 8601 formatted timestamp"
}
```

**Example Response**:
```json
{
  "status": "ok",
  "timestamp": "2024-01-01T12:00:00.000Z"
}
```

---

### 2. Web Search (Sonar Only)
Search for legal information using Perplexity Sonar without case references.

#### 2.1 Standard Web Search
```
POST /web-search
```

**Authentication**: Bearer Token or Query Parameter

**Request Body**:
```json
{
  "question": "Jaké jsou právní důsledky neplacení nájmu?",
  "top_k": 5
}
```

**Response**:
```json
{
  "answer": "string - AI-generated legal answer based on web sources",
  "source": "string - Always 'Perplexity Sonar via OpenRouter'",
  "citations": "array of strings - URLs of cited sources from Perplexity Sonar web search"
}
```

**Example Response**:
```json
{
  "answer": "Nájemce, který nehradí nájemné včas, vystavuje se několika právním důsledkům. V první řadě může pronajímatel požadovat zaplacení dlužného nájemného a smluvních pokut stanovených v nájemní smlouvě. Pokud nájemce nadále nehradí, pronajímatel může po uplynutí výpovědní lhůty podat návrh na vydání exekučního titulu pro vypořádání dluhů. V krajním případě může pronajímatel požádat soud o vydání rozsudku pro ukončení nájmu a vyklizení nemovitosti.",
  "source": "Perplexity Sonar via OpenRouter",
  "citations": [
    "https://www.zakonyprolidi.cz/cs/2000-50",
    "https://www.zakonyprolidi.cz/cs/2013-89",
    "https://www.nsoud.cz/Judikatur/ns_justice/SpisZnacka.jsp"
  ]
}
```

#### 2.2 Streaming Web Search
```
GET /web-search-stream
```

**Authentication**: Query Parameter only

**Query Parameters**:
- `question` (required): Legal question to search
- `api_key` (required): Your API key

**Response**: Server-Sent Events (SSE) stream

**Stream Events**:
1. Search initiation:
```json
{"type": "web_search_start"}
```

2. Answer chunks (multiple events):
```json
{"type": "web_answer_chunk", "content": "Partial answer text"}
```

3. Citations (single event):
```json
{"type": "web_citations", "citations": ["URL1", "URL2", ...]}
```

4. Search completion:
```json
{"type": "web_search_end"}
```

**Example Stream**:
```
data: {"type": "web_search_start"}

data: {"type": "web_answer_chunk", "content": "Nájemce, který nehradí"}
data: {"type": "web_answer_chunk", "content": " nájemné včas,"}
data: {"type": "web_answer_chunk", "content": " vystavuje se několika právním"}

data: {"type": "web_citations", "citations": ["https://www.zakonyprolidi.cz/cs/2000-50", "https://www.nsoud.cz/Judikatur/ns_justice/SpisZnacka.jsp"]}

data: {"type": "web_search_end"}
```

**Note**: The streaming response from Perplexity Sonar does not include citations in the individual chunks. Citations are only available in the final response object after the stream completes. The API handles this by yielding the final answer with citations in a separate event.

---

### 3. Case Search (Qdrant + GPT)
Search for legal answers based on Czech court cases.

#### 3.1 Standard Case Search
```
POST /case-search
```

**Authentication**: Bearer Token or Query Parameter

**Request Body**:
```json
{
  "question": "Jaké jsou právní důsledky neplacení nájmu?",
  "top_k": 5
}
```

**Response**:
```json
{
  "answer": "string - AI-generated answer based on court cases",
  "supporting_cases": "array of CaseResult objects"
}
```

**Example Response**:
```json
{
  "answer": "Podle relevantních soudních rozhodnutí neplacení nájmu představuje podstatné porušení nájemní smlouvy. V případech (20 C 123/2023) a (15 C 987/2022) soudy konstatovaly, že pronajímatel je oprávněn po splatnosti požadovat zaplacení dlužného nájemného a úroky z prodlení. Pokud nájemce neplní své platební povinnosti déle než tři měsíce, může pronajímatel podle § 2284 odst. 1 Zákona č. 89/2012 Sb. nájemní smlouvu vypovědět s jednoměsíční výpovědní lhůtou.",
  "supporting_cases": [
    {
      "case_number": "20 C 123/2023",
      "court": "Okresní soud v Praze",
      "judge": "JUDr. Jan Novák",
      "subject": "Nájemné a platby za služby",
      "date_issued": "2023-05-15",
      "date_published": "2023-05-20",
      "ecli": "ECLI:cz:osp:2023:12345",
      "keywords": ["nájem", "neplacení", "výpověď", "plnění smlouvy"],
      "legal_references": ["§ 2284 ZS", "§ 2249 ZS"],
      "source_url": "https://www.psp.cz/sqw/text/orig2.sqz?idd=12345",
      "relevance_score": 0.9123
    },
    {
      "case_number": "15 C 987/2022",
      "court": "Městský soud v Brně",
      "judge": "JUDr. Eva Svobodová",
      "subject": "Neplacení nájmu",
      "date_issued": "2022-11-30",
      "date_published": "2022-12-05",
      "ecli": "ECLI:cz:msp:2022:9876",
      "keywords": ["nájem", "neplacení", "smluvní pokuty"],
      "legal_references": ["§ 2913 ZS"],
      "source_url": "https://www.psp.cz/sqw/text/orig2.sqz?idd=67890",
      "relevance_score": 0.8547
    }
  ]
}
```

#### 3.2 Streaming Case Search
```
GET /case-search-stream
```

**Authentication**: Query Parameter only

**Query Parameters**:
- `question` (required): Legal question to search
- `top_k` (optional, default: 5): Number of cases to retrieve
- `api_key` (required): Your API key

**Response**: Server-Sent Events (SSE) stream

**Stream Events**:
1. Case search initiation:
```json
{"type": "case_search_start"}
```

2. Case fetching notification:
```json
{"type": "cases_fetching"}
```

3. GPT answer generation start:
```json
{"type": "gpt_answer_start"}
```

4. Answer chunks (multiple events):
```json
{"type": "case_answer_chunk", "content": "Partial answer text"}
```

5. GPT answer generation end:
```json
{"type": "gpt_answer_end"}
```

6. Case data start:
```json
{"type": "cases_start"}
```

7. Case details (multiple events, one per case):
```json
{
  "type": "case",
  "case_number": "string",
  "court": "string",
  "judge": "string",
  "subject": "string",
  "date_issued": "string",
  "date_published": "string",
  "ecli": "string",
  "keywords": ["string1", "string2"],
  "legal_references": ["string1", "string2"],
  "source_url": "string",
  "relevance_score": "float"
}
```

8. Case search completion:
```json
{"type": "case_search_end"}
```

**Example Stream**:
```
data: {"type": "case_search_start"}

data: {"type": "cases_fetching"}

data: {"type": "gpt_answer_start"}

data: {"type": "case_answer_chunk", "content": "Podle relevantních"}
data: {"type": "case_answer_chunk", "content": " soudních rozhodnutí"}

data: {"type": "gpt_answer_end"}

data: {"type": "cases_start"}

data: {"type": "case", "case_number": "20 C 123/2023", ...}

data: {"type": "case_search_end"}
```

---

### 4. Combined Search (Web + Cases)
Search for legal information using both web sources and Czech court cases.

#### 4.1 Standard Combined Search
```
POST /combined-search
```

**Authentication**: Bearer Token or Query Parameter

**Request Body**:
```json
{
  "question": "Jaké jsou právní důsledky neplacení nájmu?",
  "top_k": 5
}
```

**Response**:
```json
{
  "web_answer": "string - AI-generated answer based on web sources",
  "web_source": "string - Always 'Perplexity Sonar via OpenRouter'",
  "web_citations": "array of strings - URLs of web sources",
  "case_answer": "string - AI-generated answer based on court cases",
  "supporting_cases": "array of CaseResult objects"
}
```

**Example Response**:
```json
{
  "web_answer": "Nájemce, který nehradí nájemné včas, vystavuje se několika právním důsledkům. V první řadě může pronajímatel požadovat zaplacení dlužného nájemného a smluvních pokut stanovených v nájemní smlouvě. Pokud nájemce nadále nehradí, pronajímatel může po uplynutí výpovědní lhůty podat návrh na vydání exekučního titulu pro vypořádání dluhů.",
  "web_source": "Perplexity Sonar via OpenRouter",
  "web_citations": [
    "https://www.zakonyprolidi.cz/cs/2000-50",
    "https://www.zakonyprolidi.cz/cs/2013-89",
    "https://www.nsoud.cz/Judikatur/ns_justice/SpisZnacka.jsp"
  ],
  "case_answer": "Podle relevantních soudních rozhodnutí neplacení nájmu představuje podstatné porušení nájemní smlouvy. V případech (20 C 123/2023) a (15 C 987/2022) soudy konstatovaly, že pronajímatel je oprávněn po splatnosti požadovat zaplacení dlužného nájemného a úroky z prodlení.",
  "supporting_cases": [
    {
      "case_number": "20 C 123/2023",
      "court": "Okresní soud v Praze",
      "subject": "Nájemné a platby za služby",
      "relevance_score": 0.9123
    }
  ]
}
```

#### 4.2 Streaming Combined Search
```
GET /combined-search-stream
```

**Authentication**: Query Parameter only

**Query Parameters**:
- `question` (required): Legal question to search
- `top_k` (optional, default: 5): Number of cases to retrieve
- `api_key` (required): Your API key

**Response**: Server-Sent Events (SSE) stream

The stream follows the pattern of the web search followed by the case search:

**Stream Events**:
1. Web search initiation:
```json
{"type": "web_search_start"}
```

2. Web answer chunks:
```json
{"type": "web_answer_chunk", "content": "Partial web answer text"}
```

3. Web citations:
```json
{"type": "web_citations", "citations": ["URL1", "URL2", ...]}
```

4. Web search completion:
```json
{"type": "web_search_end"}
```

5. Case search initiation:
```json
{"type": "case_search_start"}
```

6. Case search events (as described in section 3.2)

7. Combined search completion:
```json
{"type": "combined_search_end"}
```

**Note**: Similar to the web search stream, the Perplexity Sonar portion of the combined search stream doesn't include citations in individual chunks. Citations are provided in a separate event after the web answer is complete.

---

### 5. Direct Case Search
Search for court cases without AI analysis of the results.

#### 5.1 Standard Case Search
```
GET /search-cases
```

**Authentication**: Bearer Token or Query Parameter

**Query Parameters**:
- `question` (required): Legal question to search
- `top_k` (optional, default: 5): Number of cases to retrieve
- `api_key` (optional if using Bearer Token): Your API key

**Response**:
```json
{
  "query": "string - The search query",
  "total_results": "integer - Number of results returned",
  "cases": "array of CaseResult objects",
  "message": "string - Optional message when no results found"
}
```

**Example Response**:
```json
{
  "query": "Jaké jsou právní důsledky neplacení nájmu?",
  "total_results": 3,
  "cases": [
    {
      "case_number": "20 C 123/2023",
      "court": "Okresní soud v Praze",
      "subject": "Nájemné a platby za služby",
      "relevance_score": 0.9123
    }
  ]
}
```

#### 5.2 Streaming Case Search
```
GET /search-cases-stream
```

**Authentication**: Query Parameter only

**Query Parameters**:
- `question` (required): Legal question to search
- `top_k` (optional, default: 5): Number of cases to retrieve
- `api_key` (required): Your API key

**Response**: Server-Sent Events (SSE) stream

**Stream Events**:
1. Search initiation:
```json
{"type": "search_start"}
```

2. Search info:
```json
{
  "type": "search_info",
  "query": "string - The search query",
  "total_results": "integer - Number of results"
}
```

3. Case results (multiple events, one per case):
```json
{
  "type": "case_result",
  "index": "integer - Sequential index starting from 1",
  "case_number": "string",
  "court": "string",
  "subject": "string",
  "relevance_score": "float"
}
```

4. Completion:
```json
{"type": "done"}
```

---

### 6. Debug Endpoint
Debug endpoint to verify Qdrant connection.

```
GET /debug/qdrant
```

**Authentication**: Bearer Token or Query Parameter

**Response**:
```json
{
  "status": "integer - HTTP status code",
  "url": "string - Qdrant server URL",
  "text": "string - Response text",
  "headers": "object - Response headers",
  "attempts": "integer - Number of connection attempts"
}
```

**Example Response**:
```json
{
  "status": 200,
  "url": "https://your-qdrant-host.com",
  "text": "Qdrant is running",
  "headers": {
    "content-type": "application/json",
    "content-length": "22"
  },
  "attempts": 1
}
```

## Error Handling

All endpoints return appropriate HTTP status codes and error messages.

**401 Unauthorized**:
```json
{
  "detail": "Invalid or missing API key"
}
```

**500 Internal Server Error**:
```json
{
  "detail": "Error description"
}
```

**Stream Errors** (for streaming endpoints):
```json
{
  "type": "error",
  "message": "Error description"
}
```

## Implementation Examples

### JavaScript/Fetch Example

```javascript
// Combined search with streaming
async function searchLegal(question) {
  const response = await fetch(
    `https://your-api-host.com/combined-search-stream?question=${encodeURIComponent(question)}`,
    {
      headers: {
        'Authorization': `Bearer ${YOUR_API_KEY}`
      }
    }
  );
  
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let webAnswer = '';
  let caseAnswer = '';
  let cases = [];
  
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    
    const chunk = decoder.decode(value, { stream: true });
    const lines = chunk.split('\n');
    
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const data = JSON.parse(line.slice(6));
          
          switch (data.type) {
            case 'web_answer_chunk':
              webAnswer += data.content;
              break;
            case 'case_answer_chunk':
              caseAnswer += data.content;
              break;
            case 'case':
              cases.push(data);
              break;
            case 'error':
              throw new Error(data.message);
          }
        } catch (e) {
          console.error('Error parsing SSE data:', e);
        }
      }
    }
  }
  
  return { webAnswer, caseAnswer, cases };
}

// Usage
searchLegal('Jaké jsou právní důsledky neplacení nájmu?')
  .then(result => {
    console.log('Web Answer:', result.webAnswer);
    console.log('Case Answer:', result.caseAnswer);
    console.log('Supporting Cases:', result.cases);
  })
  .catch(error => console.error(error));
```

### Python/Requests Example

```python
import requests

def combined_search(question, api_key, top_k=5):
    """Make a combined search request"""
    url = "https://your-api-host.com/combined-search"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "question": question,
        "top_k": top_k
    }
    
    response = requests.post(url, headers=headers, json=payload)
    
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Error: {response.status_code} - {response.text}")

# Usage
try:
    result = combined_search(
        "Jaké jsou právní důsledky neplacení nájmu?",
        "your_api_key_here"
    )
    
    print(f"Web Answer: {result['web_answer']}")
    print(f"Case Answer: {result['case_answer']}")
    for case in result['supporting_cases']:
        print(f"Case: {case['case_number']} - {case['subject']} (Score: {case['relevance_score']})")
except Exception as e:
    print(f"Error: {e}")
```

### Node.js/axios Example

```javascript
const axios = require('axios');

async function caseSearch(question, apiKey, topK = 5) {
  try {
    const response = await axios.get(
      'https://your-api-host.com/search-cases',
      {
        params: {
          question: question,
          top_k: topK,
          api_key: apiKey
        }
      }
    );
    
    return response.data;
  } catch (error) {
    if (error.response) {
      // The request was made and the server responded with a status code
      // that falls out of the range of 2xx
      throw new Error(`API Error: ${error.response.status} - ${error.response.data.detail}`);
    } else if (error.request) {
      // The request was made but no response was received
      throw new Error('Network error: No response received from server');
    } else {
      // Something happened in setting up the request that triggered an Error
      throw new Error(`Request setup error: ${error.message}`);
    }
  }
}

// Usage
(async () => {
  try {
    const result = await caseSearch(
      'Jaké jsou právní důsledky neplacení nájmu?',
      'your_api_key_here'
    );
    
    console.log(`Found ${result.total_results} cases:`);
    result.cases.forEach((case_, i) => {
      console.log(`${i + 1}. ${case_.case_number} - ${case_.court} (Score: ${case_.relevance_score})`);
      console.log(`   Subject: ${case_.subject}`);
    });
  } catch (error) {
    console.error(error);
  }
})();
```

## Environment Variables

The following environment variables are used by the API:

```
# Authentication
API_KEY=your_secure_api_key_here

# OpenRouter API (for Perplexity Sonar)
OPENROUTER_API_KEY=your_openrouter_api_key_here

# Qdrant Vector Database
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_API_KEY=your_qdrant_api_key_here
QDRANT_HTTPS=False
QDRANT_COLLECTION=your_collection_name
QDRANT_MAX_RETRIES=3
QDRANT_INITIAL_TIMEOUT=30

# Server Configuration
HOST=0.0.0.0
PORT=8000
ALLOWED_ORIGINS=http://localhost:3000,https://yourdomain.com
```

## Rate Limits and Considerations

1. **Client-Side Rate Limiting**: Implement appropriate rate limiting in client applications to prevent abuse.

2. **Qdrant Connection**: The API includes automatic retry logic for Qdrant connections with exponential backoff, particularly useful for serverless deployments with cold starts.

3. **URL Encoding**: All question parameters should be URL-encoded when using GET requests to handle special characters and Czech language characters.

4. **Streaming Endpoints**: 
   - Use Server-Sent Events (SSE) format
   - Clients should handle connection errors and implement appropriate reconnection logic
   - Consider timeouts for streaming operations

5. **Error Responses**: Always check for error events in streaming responses and handle them appropriately.

## Browser Compatibility

For browser applications:
- Use the [EventSource](https://developer.mozilla.org/en-US/docs/Web/API/EventSource) API for consuming SSE streams
- Note that EventSource doesn't support custom headers, so you'll need to use the query parameter method for authentication
- For custom header support, consider using the [Fetch API](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API) with streaming response handling

## Special Considerations for Perplexity Sonar

### Limitations
1. **Citation Availability**: 
   - Citations are only available in the final response object, not in individual streaming chunks
   - The number of citations varies based on query complexity and available sources
   - Some responses may have no citations if the information doesn't require external sources

2. **Content Restrictions**:
   - Perplexity Sonar has built-in content filtering and SafeSearch enabled by default
   - Certain types of queries may be limited or refused based on content policies

3. **Cost Structure**:
   - Pricing includes both token costs and a per-request cost ($0.005 per request for low context)
   - Search context size (low/medium/high) affects total cost
   - More complex queries with higher search context cost more

### Best Practices
1. **Query Formulation**:
   - Be specific in your legal questions to get more relevant results
   - Include relevant Czech legal terms when possible for better accuracy
   - Complex questions may yield better results than simple ones

2. **Citation Handling**:
   - Always check the citations array, even when it appears to be empty
   - Implement fallback to extract URLs from search_results if needed
   - Handle cases where citations might be missing gracefully

3. **Error Handling**:
   - Implement retry logic for network timeouts
   - Handle cases where the API returns empty responses
   - Validate citation URLs before displaying them to users

### Performance Notes
- Standard (non-streaming) responses typically complete within 2-5 seconds
- Streaming responses provide immediate feedback but citations arrive at the end
- Response time increases with search complexity and context size