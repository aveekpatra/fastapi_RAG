import asyncio

import httpx
from openai import OpenAI

from app.config import settings
from app.models import CaseResult
from app.services.embedding import get_embedding
from app.services.query_generation import generate_search_queries


async def get_cases_from_qdrant(
    question: str, 
    top_k: int, 
    use_improved_rag: bool = None,
    openai_client: OpenAI = None
) -> list[CaseResult]:
    """
    Search Qdrant for most relevant cases
    
    Args:
        question: User's question
        top_k: Number of final results to return
        use_improved_rag: Whether to use improved RAG pipeline (query generation + hybrid search)
                         If None, uses settings.USE_IMPROVED_RAG
        openai_client: OpenAI client for query generation (required if use_improved_rag=True)
    
    Returns:
        List of CaseResult objects
    
    Implements two approaches:
    1. Basic: Single vector search (original approach)
    2. Improved: Query generation + multi-query hybrid search + reranking
    """
    # Determine which approach to use
    if use_improved_rag is None:
        use_improved_rag = settings.USE_IMPROVED_RAG
    
    if use_improved_rag:
        print("Using IMPROVED RAG pipeline (query generation + hybrid search)")
        return await _get_cases_improved_rag(question, top_k, openai_client)
    else:
        print("Using BASIC RAG pipeline (single vector search)")
        return await _get_cases_basic(question, top_k)


async def _get_cases_basic(question: str, top_k: int) -> list[CaseResult]:
    """
    Original basic vector search approach
    Search Qdrant for most relevant cases using sentence transformers
    Implements retry logic with exponential backoff for serverless cold starts
    """
    max_retries = settings.QDRANT_MAX_RETRIES
    initial_timeout = settings.QDRANT_INITIAL_TIMEOUT

    try:
        print(f"=== QDRANT DEBUG ===")
        print(f"Question: {question}")
        print(f"Qdrant URL: {settings.qdrant_url}")
        print(f"Collection: {settings.QDRANT_COLLECTION}")
        print(f"Top K: {top_k}")
        
        vector = await get_embedding(question)

        if vector is None:
            print("Chyba: Nepodařilo se vygenerovat vektorové vyjádření")
            return []

        print(f"Vector generated successfully, length: {len(vector)}")

        headers = (
            {"api-key": settings.QDRANT_API_KEY} if settings.QDRANT_API_KEY else {}
        )
        print(f"Headers: {list(headers.keys())}")

        for attempt in range(max_retries):
            try:
                timeout = initial_timeout * (
                    2**attempt
                )  # Exponential backoff: 30, 60, 120 seconds

                async with httpx.AsyncClient(timeout=timeout) as client:
                    print(
                        f"Attempt {attempt + 1}/{max_retries} with timeout {timeout}s"
                    )

                    response = await client.post(
                        f"{settings.qdrant_url}/collections/{settings.QDRANT_COLLECTION}/points/search",
                        headers=headers,
                        json={
                            "vector": vector,
                            "limit": top_k,
                            "with_payload": True,
                        },
                    )

                    if response.status_code == 200:
                        results = response.json()
                        result_list = results.get('result', [])
                        print(f"✅ SUCCESS: Nalezeno {len(result_list)} případů")
                        
                        if len(result_list) == 0:
                            print("⚠️ WARNING: Qdrant returned 0 results!")
                            print(f"Full response: {results}")

                        cases = []
                        for result in result_list:
                            payload = result.get("payload", {})
                            score = result.get("score", 0.0)
                            print(f"  - Case: {payload.get('case_number', 'N/A')} (score: {score})")
                            cases.append(
                                CaseResult(
                                    case_number=payload.get("case_number", "N/A"),
                                    court=payload.get("court", "N/A"),
                                    judge=payload.get("judge"),
                                    subject=payload.get("subject", ""),
                                    date_issued=payload.get("date_issued"),
                                    date_published=payload.get("date_published"),
                                    ecli=payload.get("ecli"),
                                    keywords=payload.get("keywords", []),
                                    legal_references=payload.get(
                                        "legal_references", []
                                    ),
                                    source_url=payload.get("source_url"),
                                    relevance_score=result.get("score", 0.0),
                                )
                            )
                        return cases

                    # Don't retry on client errors (4xx)
                    if 400 <= response.status_code < 500:
                        print(f"Client error in Qdrant: {response.status_code}")
                        print(f"Response: {response.text}")
                        return []

                    # Log server error and continue to retry
                    print(
                        f"Server error in Qdrant (attempt {attempt + 1}): {response.status_code}"
                    )
                    print(f"Response: {response.text}")

            except httpx.TimeoutException as e:
                print(f"Timeout error (attempt {attempt + 1}/{max_retries}): {str(e)}")
            except httpx.ConnectError as e:
                print(
                    f"Connection error (attempt {attempt + 1}/{max_retries}): {str(e)}"
                )
            except Exception as e:
                print(
                    f"Unexpected error (attempt {attempt + 1}/{max_retries}): {str(e)}"
                )

            # If not the last attempt, wait before retrying
            if attempt < max_retries - 1:
                wait_time = 2**attempt  # 1s, 2s, 4s between retries
                print(f"Waiting {wait_time}s before retry...")
                await asyncio.sleep(wait_time)

        print(f"Failed after {max_retries} attempts")
        return []

    except Exception as e:
        print(f"Fatal error in Qdrant query: {str(e)}")
        return []


async def debug_qdrant_connection() -> dict:
    """
    Debug Qdrant connection and return status
    Implements retry logic with exponential backoff
    """
    max_retries = settings.QDRANT_MAX_RETRIES
    initial_timeout = settings.QDRANT_INITIAL_TIMEOUT

    headers = {"api-key": settings.QDRANT_API_KEY} if settings.QDRANT_API_KEY else {}

    for attempt in range(max_retries):
        try:
            timeout = initial_timeout * (2**attempt)  # 30, 60, 120 seconds

            async with httpx.AsyncClient(timeout=timeout) as client:
                print(
                    f"Debug attempt {attempt + 1}/{max_retries} with timeout {timeout}s"
                )

                response = await client.get(
                    f"{settings.qdrant_url}/collections",
                    headers=headers,
                )

                return {
                    "status": response.status_code,
                    "url": settings.qdrant_url,
                    "text": response.text[:500],
                    "headers": dict(response.headers),
                    "attempts": attempt + 1,
                }

        except httpx.TimeoutException as e:
            print(f"Debug timeout (attempt {attempt + 1}/{max_retries}): {str(e)}")
        except httpx.ConnectError as e:
            print(
                f"Debug connection error (attempt {attempt + 1}/{max_retries}): {str(e)}"
            )
        except Exception as e:
            print(f"Debug error (attempt {attempt + 1}/{max_retries}): {str(e)}")

        # If not the last attempt, wait before retrying
        if attempt < max_retries - 1:
            wait_time = 2**attempt  # 1s, 2s, 4s between retries
            print(f"Waiting {wait_time}s before retry...")
            await asyncio.sleep(wait_time)

    return {
        "error": "Failed after all retry attempts",
        "url": settings.qdrant_url,
        "attempts": max_retries,
    }



async def _get_cases_improved_rag(
    question: str, 
    top_k: int,
    openai_client: OpenAI = None
) -> list[CaseResult]:
    """
    Improved RAG pipeline with query generation and HYBRID search
    
    Steps:
    1. Generate 2-3 optimized search queries that MAINTAIN ORIGINAL MEANING
    2. Perform HYBRID search (dense + sparse vectors) for each query
    3. Merge using Reciprocal Rank Fusion (RRF)
    4. Return final top K results with FULL CONTEXT (no truncation)
    
    Args:
        question: User's question
        top_k: Number of final results to return
        openai_client: OpenAI client for query generation
    
    Returns:
        List of CaseResult objects with complete information
    """
    try:
        print(f"\n{'='*80}")
        print(f"🚀 IMPROVED RAG PIPELINE WITH HYBRID SEARCH")
        print(f"{'='*80}")
        
        # Step 1: Generate search queries that maintain original meaning
        if openai_client is None:
            from app.services.llm import get_openai_client
            openai_client = get_openai_client()
        
        queries = await generate_search_queries(
            question, 
            openai_client, 
            num_queries=settings.NUM_GENERATED_QUERIES
        )
        
        print(f"\n📝 Generated {len(queries)} queries (including original)")
        
        # Step 2: Perform HYBRID search for each query
        from app.services.hybrid_search_v2 import hybrid_search_engine
        
        final_cases = await hybrid_search_engine.multi_query_hybrid_search(
            queries=queries,
            results_per_query=settings.RESULTS_PER_QUERY,
            final_limit=top_k,
            dense_weight=0.7,  # 70% semantic similarity
            sparse_weight=0.3   # 30% keyword matching
        )
        
        print(f"\n✅ Improved RAG pipeline returned {len(final_cases)} cases")
        print(f"   All cases include FULL CONTEXT (no truncation)")
        
        return final_cases
        
    except Exception as e:
        print(f"\n❌ Error in improved RAG pipeline: {str(e)}")
        import traceback
        traceback.print_exc()
        print("\n⚠️ Falling back to basic search")
        # Fallback to basic search
        return await _get_cases_basic(question, top_k)
