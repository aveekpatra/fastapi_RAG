# Setup Guide: Improved RAG Pipeline

## Quick Start

### 1. Update Environment Variables

Add these to your `.env` file:

```bash
# Enable improved RAG pipeline
USE_IMPROVED_RAG=true

# Query generation settings
NUM_GENERATED_QUERIES=3
RESULTS_PER_QUERY=10
FINAL_TOP_K=5
```

### 2. No New Dependencies Required

The improved RAG pipeline uses existing dependencies:
- `openai` - For query generation (already installed)
- `httpx` - For Qdrant API calls (already installed)
- `sentence-transformers` - For embeddings (already installed)

### 3. Restart Your Server

```bash
cd fastapi_rag
uvicorn app.main:app --reload
```

### 4. Test the Implementation

```bash
# Test with Python script
python test_improved_rag.py

# Or test with cURL
curl -X POST "http://localhost:8000/case-search?use_improved_rag=true" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"question": "Jaké jsou podmínky pro výpověď zaměstnance?", "top_k": 5}'
```

## Configuration Options

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_IMPROVED_RAG` | `false` | Enable/disable improved RAG globally |
| `NUM_GENERATED_QUERIES` | `3` | Number of queries to generate (2-3 recommended) |
| `RESULTS_PER_QUERY` | `10` | Results to fetch per query (8-15 recommended) |
| `FINAL_TOP_K` | `5` | Final number of results to return |

### API Parameter Override

You can override the global setting per request:

```bash
# Force improved RAG for this request
?use_improved_rag=true

# Force basic RAG for this request
?use_improved_rag=false

# Use global config setting
# (omit parameter)
```

## Qdrant Collection Requirements

### Current Implementation (Dense Vectors Only)

The current implementation works with your existing Qdrant collection that has dense vectors. It performs:
- Dense vector search using your existing embeddings
- Multi-query execution with result merging

### Future: True Hybrid Search (Dense + Sparse)

To enable true hybrid search with BM25, you'll need to:

1. **Update your Qdrant collection to include sparse vectors:**

```python
from qdrant_client import QdrantClient, models

client = QdrantClient(url="your-qdrant-url", api_key="your-api-key")

# Update collection with sparse vectors
client.update_collection(
    collection_name="your-collection-name",
    sparse_vectors_config={
        "bm25": models.SparseVectorParams(
            modifier=models.Modifier.IDF  # Enable Inverse Document Frequency
        )
    }
)
```

2. **Re-index your documents with BM25 embeddings:**

```python
from fastembed import SparseTextEmbedding

# Initialize BM25 model
bm25_model = SparseTextEmbedding(model_name="Qdrant/bm25")

# For each document
for doc in documents:
    # Generate sparse embedding
    sparse_embedding = list(bm25_model.embed([doc.text]))[0]
    
    # Update point with sparse vector
    client.set_payload(
        collection_name="your-collection-name",
        points=[doc.id],
        payload={
            "sparse_vector": {
                "indices": sparse_embedding.indices.tolist(),
                "values": sparse_embedding.values.tolist()
            }
        }
    )
```

3. **Update `hybrid_search.py` to use RRF:**

```python
# In hybrid_search_single_query function
response = await client.post(
    f"{settings.qdrant_url}/collections/{settings.QDRANT_COLLECTION}/points/query",
    headers=headers,
    json={
        "prefetch": [
            {
                "query": dense_vector,
                "using": "dense",
                "limit": top_k * 2
            },
            {
                "query": {
                    "indices": sparse_vector.indices,
                    "values": sparse_vector.values
                },
                "using": "bm25",
                "limit": top_k * 2
            }
        ],
        "query": {"fusion": "rrf"},
        "limit": top_k,
        "with_payload": True,
    }
)
```

## Testing & Validation

### 1. Run Test Script

```bash
cd fastapi_rag
python test_improved_rag.py
```

This will:
- Test both basic and improved RAG
- Compare results and timing
- Show case overlap and differences

### 2. Manual Testing

**Test Basic RAG:**
```bash
curl -X POST "http://localhost:8000/case-search?use_improved_rag=false" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "question": "Může zaměstnavatel propustit zaměstnance bez udání důvodu?",
    "top_k": 5
  }'
```

**Test Improved RAG:**
```bash
curl -X POST "http://localhost:8000/case-search?use_improved_rag=true" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "question": "Může zaměstnavatel propustit zaměstnance bez udání důvodu?",
    "top_k": 5
  }'
```

### 3. Check Logs

Look for these log messages:

```
# Query generation
Generated 3 search queries:
  1. výpověď bez udání důvodu pracovní právo
  2. okamžité zrušení pracovního poměru zaměstnavatelem
  3. ochrana zaměstnance před neodůvodněným propuštěním

# Pipeline execution
Using IMPROVED RAG pipeline (query generation + hybrid search)
Merged 12 unique cases from 3 queries
Improved RAG pipeline returned 5 cases
```

## Performance Tuning

### For Faster Response (Lower Latency)

```bash
# Reduce number of queries
NUM_GENERATED_QUERIES=2

# Reduce results per query
RESULTS_PER_QUERY=8

# Use basic RAG for simple queries
USE_IMPROVED_RAG=false
```

### For Better Accuracy (Higher Quality)

```bash
# More queries for better coverage
NUM_GENERATED_QUERIES=3

# More results per query
RESULTS_PER_QUERY=15

# Always use improved RAG
USE_IMPROVED_RAG=true
```

### Adaptive Approach

Use API parameter to decide per request:

```python
def should_use_improved_rag(question: str) -> bool:
    """Decide based on question complexity"""
    # Simple heuristic: use improved RAG for complex questions
    word_count = len(question.split())
    has_legal_terms = any(term in question.lower() for term in [
        'zákon', 'paragraf', 'soud', 'rozsudek', 'právní'
    ])
    
    return word_count > 10 or has_legal_terms

# Use in request
use_improved = should_use_improved_rag(user_question)
response = requests.post(
    f"http://localhost:8000/case-search?use_improved_rag={str(use_improved).lower()}",
    json={"question": user_question, "top_k": 5}
)
```

## Monitoring

### Key Metrics to Track

1. **Latency**
   - Basic RAG: ~1-2s
   - Improved RAG: ~2-4s

2. **Result Quality**
   - Relevance scores
   - User feedback
   - Case overlap between approaches

3. **Error Rates**
   - Query generation failures
   - Qdrant timeouts
   - Fallback frequency

### Log Analysis

```bash
# Count improved RAG usage
grep "Using IMPROVED RAG pipeline" logs.txt | wc -l

# Count fallbacks to basic
grep "Falling back to basic search" logs.txt | wc -l

# Average cases merged
grep "Merged.*unique cases" logs.txt
```

## Troubleshooting

### Issue: "Error generating queries"

**Cause:** OpenAI API issue or rate limit

**Solution:**
- Check OpenRouter API key
- Check rate limits
- System will fallback to basic search automatically

### Issue: "Hybrid search failed after 3 attempts"

**Cause:** Qdrant connection timeout

**Solution:**
- Check Qdrant URL and API key
- Increase timeout: `QDRANT_INITIAL_TIMEOUT=60`
- Check Qdrant server status

### Issue: Results are worse than basic RAG

**Cause:** Query generation not optimal for your domain

**Solution:**
- Adjust prompt in `query_generation.py`
- Reduce `NUM_GENERATED_QUERIES` to 2
- Fine-tune scoring weights in `hybrid_search.py`

### Issue: Too slow for production

**Cause:** Too many queries or results

**Solution:**
- Reduce `NUM_GENERATED_QUERIES` to 2
- Reduce `RESULTS_PER_QUERY` to 8
- Use improved RAG only for complex queries
- Add caching layer

## Frontend Integration

### No Changes Required

The API response format remains the same, so your frontend should work without modifications.

### Optional: Show RAG Mode to Users

You can add a badge or indicator:

```typescript
// In your frontend
const response = await fetch('/case-search?use_improved_rag=true', {
  method: 'POST',
  body: JSON.stringify({ question, top_k: 5 })
});

// Show indicator
<Badge>Enhanced Search</Badge>
```

### Optional: Let Users Choose

```typescript
<Toggle 
  label="Use enhanced search (slower but more accurate)"
  checked={useImprovedRag}
  onChange={setUseImprovedRag}
/>
```

## Next Steps

1. **Test with your data** - Run test script with real queries
2. **Monitor performance** - Track latency and quality metrics
3. **Tune parameters** - Adjust based on your use case
4. **Consider hybrid search** - Add BM25 for even better results
5. **Add cross-encoder** - Implement better reranking
6. **Add caching** - Cache generated queries and results

## Support

For issues or questions:
1. Check logs for error messages
2. Review documentation in `IMPROVED_RAG_PIPELINE.md`
3. Test with `test_improved_rag.py`
4. Verify Qdrant collection configuration
