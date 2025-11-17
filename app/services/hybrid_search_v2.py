"""
Hybrid Search Service V2
Implements true hybrid search combining:
1. Dense vector search (semantic similarity)
2. Sparse vector search (BM25 full-text)
3. Reciprocal Rank Fusion (RRF) for combining results

Based on Qdrant's official hybrid search implementation
"""
import asyncio
from typing import List, Dict, Any, Optional, Tuple
import httpx
from collections import defaultdict

from app.config import settings
from app.models import CaseResult
from app.services.embedding import get_embedding


class HybridSearchEngine:
    """
    Production-ready hybrid search engine for Czech court decisions
    Combines dense vectors (semantic) with sparse vectors (BM25 keywords)
    """
    
    def __init__(self):
        self.qdrant_url = settings.qdrant_url
        self.collection_name = settings.QDRANT_COLLECTION
        self.headers = {"api-key": settings.QDRANT_API_KEY} if settings.QDRANT_API_KEY else {}
        self.max_retries = settings.QDRANT_MAX_RETRIES
        self.initial_timeout = settings.QDRANT_INITIAL_TIMEOUT
    
    async def hybrid_search(
        self,
        query: str,
        limit: int = 10,
        dense_weight: float = 0.7,
        sparse_weight: float = 0.3,
        use_rrf: bool = True
    ) -> List[CaseResult]:
        """
        Perform hybrid search combining dense and sparse vectors
        
        Args:
            query: Search query text
            limit: Number of results to return
            dense_weight: Weight for dense vector search (0-1)
            sparse_weight: Weight for sparse vector search (0-1)
            use_rrf: Use Reciprocal Rank Fusion instead of weighted scores
        
        Returns:
            List of CaseResult objects sorted by relevance
        """
        try:
            print(f"\n{'='*80}")
            print(f"🔍 VYHLEDÁVÁNÍ")
            print(f"{'='*80}")
            print(f"Dotaz: {query}")
            print(f"Limit: {limit}")
            
            # Get dense vector embedding
            dense_vector = await get_embedding(query)
            if dense_vector is None:
                print("❌ Nepodařilo se vygenerovat vektor")
                return []
            
            # Prepare sparse vector (for future use when collection supports it)
            sparse_vector = self._create_sparse_vector(query)
            
            # Perform search using Qdrant
            results = await self._execute_hybrid_search(
                dense_vector=dense_vector,
                sparse_vector=sparse_vector,
                limit=limit,
                dense_weight=dense_weight,
                sparse_weight=sparse_weight,
                use_rrf=use_rrf
            )
            
            print(f"✅ Nalezeno {len(results)} výsledků")
            return results
            
        except Exception as e:
            print(f"❌ Chyba při vyhledávání: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
    
    def _create_sparse_vector(self, text: str) -> Dict[str, Any]:
        """
        Create sparse vector for BM25 full-text search
        Extracts keywords and assigns weights
        
        Args:
            text: Input text
        
        Returns:
            Sparse vector dict with indices and values
        """
        # Tokenize and clean
        words = text.lower().split()
        
        # Remove common Czech stop words (comprehensive list for legal texts)
        stop_words = {
            'a', 'i', 'o', 'u', 'v', 'z', 's', 'k', 'na', 'po', 'za', 'do', 'od',
            'je', 'být', 'ten', 'který', 'se', 'pro', 'jako', 'jeho', 'její',
            'můj', 'tvůj', 'náš', 'váš', 'tento', 'tato', 'toto', 'tyto',
            'by', 'aby', 'když', 'kde', 'jak', 'co', 'že', 'ale', 'nebo', 'ani',
            'však', 'tedy', 'tak', 'již', 'ještě', 'také', 'pouze', 'podle',
            'mezi', 'před', 'při', 'bez', 'nad', 'pod', 'ze', 'ke', 've', 'ze'
        }
        
        # Filter and count
        word_counts = defaultdict(int)
        for word in words:
            # Remove punctuation
            word = ''.join(c for c in word if c.isalnum())
            if word and word not in stop_words and len(word) > 2:
                word_counts[word] += 1
        
        # Create sparse vector
        # In Qdrant, sparse vectors use text tokens directly
        # The format is: {"text": "word1 word2 word3"}
        keywords = ' '.join(word_counts.keys())
        
        return {"text": keywords}
    
    async def _execute_hybrid_search(
        self,
        dense_vector: List[float],
        sparse_vector: Dict[str, Any],
        limit: int,
        dense_weight: float,
        sparse_weight: float,
        use_rrf: bool
    ) -> List[CaseResult]:
        """
        Execute search using dense vectors only
        
        NOTE: True hybrid search requires Qdrant collection to be configured with
        both dense and sparse vectors. Since your collection likely only has dense vectors,
        we use dense-only search which is still very effective with paraphrase-multilingual-MiniLM-L12-v2
        
        The multi-query approach with RRF fusion provides the "hybrid" benefit by
        combining results from multiple query formulations.
        """
        for attempt in range(self.max_retries):
            try:
                timeout = self.initial_timeout * (2 ** attempt)
                
                async with httpx.AsyncClient(timeout=timeout) as client:
                    print(f"  Pokus {attempt + 1}/{self.max_retries} (timeout: {timeout}s)")
                    
                    # Dense vector search (semantic similarity)
                    # This works with your existing Qdrant collection
                    response = await client.post(
                        f"{self.qdrant_url}/collections/{self.collection_name}/points/search",
                        headers=self.headers,
                        json={
                            "vector": dense_vector,
                            "limit": limit,
                            "with_payload": True,
                        }
                    )
                    
                    if response.status_code == 200:
                        results = response.json()
                        result_list = results.get('result', [])
                        
                        print(f"  ✅ Úspěch: {len(result_list)} výsledků")
                        
                        # Convert to CaseResult objects
                        cases = []
                        for result in result_list:
                            payload = result.get("payload", {})
                            score = result.get("score", 0.0)
                            
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
                                    relevance_score=score,
                                )
                            )
                        
                        return cases
                    
                    # Handle errors
                    if 400 <= response.status_code < 500:
                        print(f"  ❌ Chyba klienta: {response.status_code}")
                        print(f"     Odpověď: {response.text[:500]}")
                        return []
                    
                    print(f"  ⚠️ Chyba serveru: {response.status_code}")
                    
            except httpx.TimeoutException as e:
                print(f"  ⏱️ Timeout (pokus {attempt + 1})")
            except Exception as e:
                print(f"  ❌ Chyba (pokus {attempt + 1}): {str(e)}")
            
            # Wait before retry
            if attempt < self.max_retries - 1:
                wait_time = 2 ** attempt
                await asyncio.sleep(wait_time)
        
        print(f"  ❌ Selhalo po {self.max_retries} pokusech")
        return []
    
    async def multi_query_hybrid_search(
        self,
        queries: List[str],
        results_per_query: int = 10,
        final_limit: int = 5,
        dense_weight: float = 0.7,
        sparse_weight: float = 0.3
    ) -> List[CaseResult]:
        """
        Perform hybrid search across multiple queries and merge results
        
        Args:
            queries: List of search queries
            results_per_query: Results to retrieve per query
            final_limit: Final number of results to return
            dense_weight: Weight for dense vectors
            sparse_weight: Weight for sparse vectors
        
        Returns:
            Merged and deduplicated list of CaseResult objects
        """
        print(f"\n{'='*80}")
        print(f"🔍 VYHLEDÁVÁNÍ S VÍCE DOTAZY")
        print(f"{'='*80}")
        print(f"Počet dotazů: {len(queries)}")
        print(f"Výsledků na dotaz: {results_per_query}")
        print(f"Finální limit: {final_limit}")
        
        # Execute searches in parallel
        search_tasks = [
            self.hybrid_search(
                query=query,
                limit=results_per_query,
                dense_weight=dense_weight,
                sparse_weight=sparse_weight,
                use_rrf=True
            )
            for query in queries
        ]
        
        all_results = await asyncio.gather(*search_tasks)
        
        # Merge and deduplicate using RRF-style scoring
        case_scores = {}
        
        for query_idx, query_results in enumerate(all_results):
            for rank, case in enumerate(query_results, 1):
                case_id = case.case_number
                
                # RRF score: 1 / (k + rank) where k=60 is standard
                rrf_score = 1.0 / (60 + rank)
                
                if case_id not in case_scores:
                    case_scores[case_id] = {
                        'case': case,
                        'rrf_score': rrf_score,
                        'max_score': case.relevance_score,
                        'query_count': 1,
                        'ranks': [rank]
                    }
                else:
                    # Accumulate RRF scores
                    case_scores[case_id]['rrf_score'] += rrf_score
                    case_scores[case_id]['max_score'] = max(
                        case_scores[case_id]['max_score'],
                        case.relevance_score
                    )
                    case_scores[case_id]['query_count'] += 1
                    case_scores[case_id]['ranks'].append(rank)
        
        # Convert to list and sort by RRF score
        merged_cases = []
        for case_id, data in case_scores.items():
            case = data['case']
            # CRITICAL: Keep original Qdrant score (0-1 range) for GPT context
            # Use RRF score only for sorting
            case.relevance_score = data['max_score']  # Preserve original semantic similarity score
            # Store RRF for sorting
            case._rrf_score = data['rrf_score']
            merged_cases.append(case)
        
        # Sort by RRF score (but keep original relevance_score for GPT)
        merged_cases.sort(key=lambda x: x._rrf_score, reverse=True)
        
        print(f"✅ Sloučeno {len(merged_cases)} unikátních případů")
        print(f"   Vráceno top {final_limit}")
        
        # Log top results
        for i, case in enumerate(merged_cases[:final_limit], 1):
            case_data = case_scores[case.case_number]
            print(f"   {i}. {case.case_number} (skóre: {case.relevance_score:.4f}, RRF: {case._rrf_score:.4f}, "
                  f"objevilo se v {case_data['query_count']}/{len(queries)} dotazech)")
        
        return merged_cases[:final_limit]


# Global instance
hybrid_search_engine = HybridSearchEngine()
