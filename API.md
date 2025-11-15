# Czech Legal Assistant API Documentation

## Overview
This API provides AI-powered legal search capabilities using:
- **Web Search**: Perplexity Sonar for general legal information
- **Case Search**: Czech court cases via Qdrant vector database
- **Combined Search**: Both web and case-based answers

## Authentication
All endpoints require API key authentication (except `/health`).

### Method 1: Bearer Token (Recommended)
```
Authorization: Bearer YOUR_API_KEY
```

### Method 2: Query Parameter
```
api_key=YOUR_API_KEY
```

## Endpoints

### 1. Health Check
```
GET /health
```
**Response:**
```json
{
  "status": "ok",
  "timestamp": "2024-01-01T12:00:00.000Z"
}
```

---

### 2. Web Search (Sonar Only)

#### Standard (Non-Streaming)
```
POST /web-search
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
  "answer": "Legal answer...",
  "source": "Perplexity Sonar via OpenRouter",
  "citations": ["https://example.com/law1", "https://example.com/law2"]
}
```

#### Streaming
```
GET /web-search-stream?question=QUERY&api_key=KEY
```
**Event Stream Format:**
```
data: {"type": "web_search_start"}

data: {"type": "web_answer_chunk", "content": "L"}
data: {"type": "web_answer_chunk", "content": "e"}
data: {"type": "web_answer_chunk", "content": "g"}
...

data: {"type": "web_citations", "citations": ["https://example.com/law1"]}

data: {"type": "web_search_end"}
```

---

### 3. Case Search (Qdrant + GPT)

#### Standard (Non-Streaming)
```
POST /case-search
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
  "answer": "Case-based legal answer...",
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

#### Streaming
```
GET /case-search-stream?question=QUERY&top_k=5&api_key=KEY
```
**Event Stream Format:**
```
data: {"type": "case_search_start"}

data: {"type": "cases_fetching"}

data: {"type": "gpt_answer_start"}

data: {"type": "case_answer_chunk", "content": "C"}
data: {"type": "case_answer_chunk", "content": "a"}
...

data: {"type": "gpt_answer_end"}

data: {"type": "cases_start"}

data: {"type": "case", "case_number": "20 C 123/2023", ...}

data: {"type": "case_search_end"}
```

---

### 4. Combined Search (Web + Cases)

#### Standard (Non-Streaming)
```
POST /combined-search
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
  "web_answer": "Web search answer...",
  "web_source": "Perplexity Sonar via OpenRouter",
  "web_citations": ["https://example.com/law1"],
  "case_answer": "Case-based answer...",
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

#### Streaming
```
GET /combined-search-stream?question=QUERY&top_k=5&api_key=KEY
```
**Event Stream Format:**
```
data: {"type": "web_search_start"}

data: {"type": "web_answer_chunk", "content": "L"}
...

data: {"type": "web_citations", "citations": ["https://example.com/law1"]}

data: {"type": "web_search_end"}

data: {"type": "case_search_start"}

data: {"type": "cases_fetching"}

data: {"type": "gpt_answer_start"}

data: {"type": "case_answer_chunk", "content": "C"}
...

data: {"type": "gpt_answer_end"}

data: {"type": "cases_start"}

data: {"type": "case", ...}

data: {"type": "combined_search_end"}
```

---

### 5. Direct Case Search

#### Standard (Non-Streaming)
```
GET /search-cases?question=QUERY&top_k=5&api_key=KEY
```
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
      "relevance_score": 0.9123
    }
  ]
}
```

#### Streaming
```
GET /search-cases-stream?question=QUERY&top_k=5&api_key=KEY
```
**Event Stream Format:**
```
data: {"type": "search_start"}

data: {"type": "search_info", "query": "...", "total_results": 3}

data: {"type": "case_result", "index": 1, ...}
data: {"type": "case_result", "index": 2, ...}

data: {"type": "done"}
```

---

### 6. Debug
#### Standard (Non-Streaming)
```
GET /debug/qdrant?api_key=KEY
```
**Response:**
```json
{
  "status": 200,
  "url": "https://your-qdrant-host.com",
  "text": "...",
  "headers": {...},
  "attempts": 1
}
```

## Implementation Examples

### Next.js API Routes

```javascript
// pages/api/legal-search.js
import { NextApiRequest, NextApiResponse } from 'next';

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  const { question, top_k = 5 } = req.query;
  
  if (req.method === 'POST') {
    // Standard combined search
    const response = await fetch('https://fastapi-production-fccd.up.railway.app/combined-search', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${process.env.API_KEY}`
      },
      body: JSON.stringify({ question, top_k: parseInt(top_k) })
    });
    
    const data = await response.json();
    return res.status(200).json(data);
  }
  
  if (req.method === 'GET') {
    // Streaming combined search
    const response = await fetch(
      `https://fastapi-production-fccd.up.railway.app/combined-search-stream?question=${encodeURIComponent(question)}&top_k=${top_k}`,
      {
        headers: {
          'Authorization': `Bearer ${process.env.API_KEY}`
        }
      }
    );
    
    // Set up streaming response
    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive'
    });
    
    // Pipe the stream
    const reader = response.body.getReader();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      res.write(value);
    }
    
    return res.end();
  }
  
  return res.status(405).json({ error: 'Method not allowed' });
}
```

### React Component Example

```javascript
import { useState, useCallback } from 'react';

function LegalSearch() {
  const [question, setQuestion] = useState('');
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  
  const handleSearch = useCallback(async () => {
    if (!question.trim()) return;
    
    setLoading(true);
    
    try {
      // Use streaming for better UX
      const response = await fetch(
        `https://fastapi-production-fccd.up.railway.app/combined-search-stream?question=${encodeURIComponent(question)}`,
        {
          headers: {
            'Authorization': `Bearer ${process.env.NEXT_PUBLIC_API_KEY}`
          }
        }
      );
      
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
            }
          }
        }
      }
      
      setResults({ webAnswer, caseAnswer, cases });
    } catch (error) {
      console.error('Search error:', error);
    } finally {
      setLoading(false);
    }
  }, [question]);
  
  return (
    <div>
      <input
        type="text"
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        placeholder="Enter legal question..."
      />
      <button onClick={handleSearch} disabled={loading}>
        {loading ? 'Searching...' : 'Search'}
      </button>
      
      {results && (
        <div>
          <h2>Web Search Result</h2>
          <p>{results.webAnswer}</p>
          
          <h2>Case Search Result</h2>
          <p>{results.caseAnswer}</p>
          
          <h3>Supporting Cases</h3>
          {results.cases.map((case, i) => (
            <div key={i}>
              <h4>{case.case_number}</h4>
              <p><strong>Court:</strong> {case.court}</p>
              <p><strong>Subject:</strong> {case.subject}</p>
              <p><strong>Relevance:</strong> {case.relevance_score}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

### Python/Fetch Example

```python
import requests
import json

def legal_search(question, api_key, top_k=5):
    """Make a combined search request"""
    url = "https://fastapi-production-fccd.up.railway.app/combined-search"
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
        print(f"Error: {response.status_code} - {response.text}")
        return None

# Usage
result = legal_search(
    "Jaké jsou právní důsledky neplacení nájmu?",
    "your_api_key_here"
)

if result:
    print(f"Web Answer: {result['web_answer']}")
    print(f"Case Answer: {result['case_answer']}")
    for case in result['supporting_cases']:
        print(f"Case: {case['case_number']} - {case['subject']}")
```

## Configuration

### Environment Variables
```
API_KEY=your_secure_api_key_here
OPENROUTER_API_KEY=your_openrouter_api_key_here
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_API_KEY=your_qdrant_api_key_here
QDRANT_HTTPS=False
QDRANT_COLLECTION=your_collection_name
QDRANT_MAX_RETRIES=3
QDRANT_INITIAL_TIMEOUT=30
ALLOWED_ORIGINS=http://localhost:3000,https://yourdomain.com
```

### Error Handling

Common error responses:
```json
{
  "detail": "Invalid or missing API key"
}
```
```json
{
  "detail": "Internal server error"
}
```
```json
{
  "type": "error",
  "message": "Error description"
}
```

## Rate Limits
- Standard endpoints: No explicit rate limiting (server-side recommended)
- Streaming endpoints: May implement client-side rate limiting
- Qdrant retries: Automatic retry with exponential backoff for serverless cold starts

## Notes
- All question parameters should be URL-encoded when using GET requests
- Czech characters work correctly with proper encoding
- Streaming endpoints provide real-time responses as they are generated
- Case search uses Czech court case database with sentence transformer embeddings
- Web search endpoints now properly include citations in both streaming and non-streaming modes