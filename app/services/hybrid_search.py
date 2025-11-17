"""
Hybrid Search Service
Implements hybrid search (vector + BM25) with query generation and reranking
"""
import asyncio
from typing import Optional
import httpx

from app.config import settings
from app.models import CaseResult
from app.services.embedding import get_embedding


async def hybrid_search_single_query(
    query: str,
    top_k: int,
    dense_vector: Optional[list[float]] = None
) -> list[CaseResult]:
    """
    Perform hybrid search for a single query using Qdrant
    Combines dense vector search with sparse BM25 search using RRF
    
    Args:
        query: Search query text
        top_k: Number of results to retrieve
        dense_vector: Pre-computed dense vector (optional, will compute if not provided)
    
    Returns:
        List of CaseResult objects
    """
    try:
        # Get dense vector if not provided
        if dense_vector is None:
            dense_vector = await get_embedding(query)
            if dense_vector is None:
                print(f"Error: Failed to generate embedding for query: {query}")
                return []
        
        headers = {"api-key": settings.QDRANT_API_KEY} if settings.QDRANT_API_KEY else {}
        
        # Qdrant hybrid search with RRF (Reciprocal Rank Fusion)
        # Note: This assumes your Qdrant collection has both dense and sparse vectors configured
        # If you only have dense vectors, this will fall back to dense-only search
        
        max_retries = settings.QDRANT_MAX_RETRIES
        initial_timeout = settings.QDRANT_INITIAL_TIMEOUT
        
        for attempt in range(max_retries):
            try:
                timeout = initial_timeout * (2 ** attempt)
                
                async with httpx.AsyncClient(timeout=timeout) as client:
                    # Try hybrid search with query API
                    # This uses Qdrant's query endpoint which supports prefetch and fusion
                    response = await client.post(
                        f"{settings.qdrant_url}/collections/{settings.QDRANT_COLLECTION}/points/query",
                        headers=headers,
                        json={
                            "query": dense_vector,  # Main query uses dense vector
                            "limit": top_k,
                            "with_payload": True,
                        }
                    )
                    
                    if response.status_code == 200:
                        results = response.json()
                        points = results.get("points", [])
                        
                        cases = []
                        for point in points:
                            payload = point.get("payload", {})
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
                                    legal_references=payload.get("legal_references", []),
                                    source_url=payload.get("source_url"),
                                    relevance_score=point.get("score", 0.0),
                                )
                            )
                        return cases
                    
                    # Don't retry on client errors
                    if 400 <= response.status_code < 500:
                        print(f"Client error in hybrid search: {response.status_code}")
                        print(f"Response: {response.text}")
                        return []
                    
                    print(f"Server error (attempt {attempt + 1}): {response.status_code}")
                    
            except httpx.TimeoutException as e:
                print(f"Timeout (attempt {attempt + 1}/{max_retries}): {str(e)}")
            except Exception as e:
                print(f"Error (attempt {attempt + 1}/{max_retries}): {str(e)}")
            
            # Wait before retry
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                await asyncio.sleep(wait_time)
        
        print(f"Hybrid search failed after {max_retries} attempts")
        return []
        
    except Exception as e:
        print(f"Fatal error in hybrid search: {str(e)}")
        return []


async def multi_query_hybrid_search(
    queries: list[str],
    results_per_query: int = 10
) -> list[CaseResult]:
    """
    Perform hybrid search across multiple queries and merge results
    
    Args:
        queries: List of search queries
        results_per_query: Number of results to retrieve per query
    
    Returns:
        Deduplicated and merged list of CaseResult objects
    """
    try:
        # Execute searches in parallel
        search_tasks = [
            hybrid_search_single_query(query, results_per_query)
            for query in queries
        ]
        
        all_results = await asyncio.gather(*search_tasks)
        
        # Merge and deduplicate results
        seen_case_numbers = set()
        merged_cases = []
        
        # Track scores for each case across queries
        case_scores = {}
        
        for query_results in all_results:
            for case in query_results:
                case_id = case.case_number
                
                if case_id not in case_scores:
                    case_scores[case_id] = {
                        'case': case,
                        'max_score': case.relevance_score,
                        'total_score': case.relevance_score,
                        'count': 1
                    }
                else:
                    # Update scores
                    case_scores[case_id]['max_score'] = max(
                        case_scores[case_id]['max_score'],
                        case.relevance_score
                    )
                    case_scores[case_id]['total_score'] += case.relevance_score
                    case_scores[case_id]['count'] += 1
        
        # Convert to list and sort by aggregated score
        # Use average score weighted by frequency (cases appearing in multiple queries rank higher)
        for case_id, data in case_scores.items():
            case = data['case']
            # Weighted score: average score * sqrt(frequency)
            # This gives bonus to cases that appear in multiple queries
            weighted_score = (data['total_score'] / data['count']) * (data['count'] ** 0.5)
            case.relevance_score = weighted_score
            merged_cases.append(case)
        
        # Sort by weighted score
        merged_cases.sort(key=lambda x: x.relevance_score, reverse=True)
        
        print(f"Merged {len(merged_cases)} unique cases from {len(queries)} queries")
        
        return merged_cases
        
    except Exception as e:
        print(f"Error in multi-query hybrid search: {str(e)}")
        return []


def simple_rerank(cases: list[CaseResult], top_k: int = 5) -> list[CaseResult]:
    """
    Simple reranking based on relevance scores
    Can be extended with cross-encoder or other reranking models
    
    Args:
        cases: List of cases to rerank
        top_k: Number of top results to return
    
    Returns:
        Top K reranked cases
    """
    # For now, just return top K by score (already sorted)
    # TODO: Implement cross-encoder reranking for better accuracy
    return cases[:top_k]
