"""
Multi-Source Search Service with Advanced Orchestration
Supports multiple Qdrant collections with reranking and quality optimization
Default: All 3 court collections (Seznam/retromae-small-cs)
"""
import asyncio
from typing import List, Optional, Dict, Any
from enum import Enum
from dataclasses import dataclass
import httpx
from sentence_transformers import SentenceTransformer

from app.config import settings
from app.models import CaseResult


class DataSource(str, Enum):
    """Available data sources - 3 court collections use Seznam model"""
    # New collections - Seznam/retromae-small-cs (256 dim)
    CONSTITUTIONAL_COURT = "constitutional_court"
    SUPREME_COURT = "supreme_court"
    SUPREME_ADMIN_COURT = "supreme_admin_court"
    
    # Search all 3 court sources (DEFAULT)
    ALL_COURTS = "all_courts"
    
    # Legacy: Original collection - paraphrase-multilingual (384 dim)
    GENERAL_COURTS = "general_courts"


@dataclass
class CollectionConfig:
    """Configuration for a Qdrant collection"""
    name: str
    embedding_model: str
    vector_size: int
    display_name: str
    description: str
    case_number_field: str = "case_number"
    text_field: str = "subject"
    court_field: str = "court"
    date_field: str = "date_issued"
    uses_chunking: bool = False
    chunk_text_field: str = "chunk_text"
    full_text_field: str = "full_text"


def get_collection_configs() -> Dict[DataSource, CollectionConfig]:
    """
    Get collection configurations - 3 main courts use Seznam model
    
    Data structure from vectorize scripts:
    - case_number: case identifier
    - date: date field
    - chunk_text: chunk content
    - full_text: full text (only on chunk_index=0)
    - chunk_index, total_chunks, filename
    - source: only in supreme_court (e.g., "SupCo")
    - NO court field in payload - use display_name
    """
    return {
        DataSource.CONSTITUTIONAL_COURT: CollectionConfig(
            name=settings.QDRANT_CONSTITUTIONAL_COURT,
            embedding_model=settings.SEZNAM_EMBEDDING_MODEL,
            vector_size=settings.SEZNAM_VECTOR_SIZE,
            display_name="Ústavní soud",
            description="Nálezy a usnesení Ústavního soudu ČR (510k+ dokumentů)",
            case_number_field="case_number",
            text_field="chunk_text",
            court_field="court",  # Not in payload, will use display_name
            date_field="date",
            uses_chunking=True,
            chunk_text_field="chunk_text",
            full_text_field="full_text",
        ),
        DataSource.SUPREME_COURT: CollectionConfig(
            name=settings.QDRANT_SUPREME_COURT,
            embedding_model=settings.SEZNAM_EMBEDDING_MODEL,
            vector_size=settings.SEZNAM_VECTOR_SIZE,
            display_name="Nejvyšší soud",
            description="Rozhodnutí Nejvyššího soudu ČR (1.1M+ dokumentů)",
            case_number_field="case_number",
            text_field="chunk_text",
            court_field="source",  # Supreme court has 'source' field
            date_field="date",
            uses_chunking=True,
            chunk_text_field="chunk_text",
            full_text_field="full_text",
        ),
        DataSource.SUPREME_ADMIN_COURT: CollectionConfig(
            name=settings.QDRANT_SUPREME_ADMIN_COURT,
            embedding_model=settings.SEZNAM_EMBEDDING_MODEL,
            vector_size=settings.SEZNAM_VECTOR_SIZE,
            display_name="Nejvyšší správní soud",
            description="Rozhodnutí Nejvyššího správního soudu ČR (695k+ dokumentů)",
            case_number_field="case_number",
            text_field="chunk_text",
            court_field="court",  # Not in payload, will use display_name
            date_field="date",
            uses_chunking=True,
            chunk_text_field="chunk_text",
            full_text_field="full_text",
        ),
        DataSource.GENERAL_COURTS: CollectionConfig(
            name=settings.QDRANT_COLLECTION,
            embedding_model=settings.EMBEDDING_MODEL,
            vector_size=384,
            display_name="Obecné soudy (legacy)",
            description="Starší kolekce rozhodnutí obecných soudů",
            case_number_field="case_number",
            text_field="subject",
            court_field="court",
            date_field="date_issued",
            uses_chunking=False,
        ),
    }


# Lazy-loaded configs
_COLLECTION_CONFIGS: Optional[Dict[DataSource, CollectionConfig]] = None


def get_configs() -> Dict[DataSource, CollectionConfig]:
    global _COLLECTION_CONFIGS
    if _COLLECTION_CONFIGS is None:
        _COLLECTION_CONFIGS = get_collection_configs()
    return _COLLECTION_CONFIGS



class EmbeddingModelManager:
    """Manages multiple embedding models with lazy loading"""
    
    def __init__(self):
        self._models: Dict[str, SentenceTransformer] = {}
    
    def get_model(self, model_name: str) -> SentenceTransformer:
        if model_name not in self._models:
            print(f"🧠 Loading embedding model: {model_name}")
            self._models[model_name] = SentenceTransformer(model_name, device="cpu")
            print(f"✅ Model loaded: {model_name}")
        return self._models[model_name]
    
    def get_embedding(self, text: str, model_name: str) -> List[float]:
        model = self.get_model(model_name)
        normalize = "retromae" in model_name.lower()
        embedding = model.encode(text, normalize_embeddings=normalize)
        return embedding.tolist()


embedding_manager = EmbeddingModelManager()


class MultiSourceSearchEngine:
    """
    Advanced search engine with orchestration, reranking, and quality optimization
    Default: searches all 3 court collections (Seznam/retromae)
    """
    
    def __init__(self):
        self.qdrant_url = settings.qdrant_url
        self.headers = {"api-key": settings.QDRANT_API_KEY} if settings.QDRANT_API_KEY else {}
        self.max_retries = settings.QDRANT_MAX_RETRIES
        self.initial_timeout = settings.QDRANT_INITIAL_TIMEOUT

    async def orchestrated_search(
        self,
        query: str,
        source: DataSource = DataSource.ALL_COURTS,
        limit: int = 10,
        rerank: bool = True,
    ) -> List[CaseResult]:
        """
        Main orchestrated search with quality optimization
        
        Pipeline:
        1. Search specified source(s) - default ALL_COURTS (3 collections)
        2. Deduplicate results
        3. Filter by minimum relevance
        4. Rerank using GPT-5-nano for quality
        5. Return top results
        """
        print(f"\n{'='*70}")
        print(f"🎯 ORCHESTRATED SEARCH (GPT-5-mini pipeline)")
        print(f"   Source: {source.value}")
        print(f"   Query: {query[:80]}...")
        print(f"{'='*70}")
        
        # Step 1: Get raw results
        if source == DataSource.ALL_COURTS:
            raw_results = await self._search_all_courts(query, limit * 2)
        else:
            raw_results = await self._search_single_source(query, source, limit * 2)
        
        if not raw_results:
            print("⚠️ No results found")
            return []
        
        print(f"📊 Raw results: {len(raw_results)}")
        
        # Step 2: Deduplicate
        deduped = self._deduplicate_results(raw_results)
        print(f"📊 After dedup: {len(deduped)}")
        
        # Step 3: Filter by minimum relevance
        filtered = [r for r in deduped if r.relevance_score >= settings.MIN_RELEVANCE_SCORE]
        print(f"📊 After filter (>{settings.MIN_RELEVANCE_SCORE}): {len(filtered)}")
        
        if not filtered:
            filtered = deduped[:limit]  # Fallback to top results
        
        # Step 4: Rerank with GPT-5-nano (fast and accurate)
        if rerank and len(filtered) > limit:
            reranked = await self._rerank_with_llm(query, filtered[:settings.RERANK_TOP_K])
            final = reranked[:limit]
        else:
            final = filtered[:limit]
        
        print(f"✅ Final results: {len(final)}")
        return final
    
    async def _search_all_courts(self, query: str, limit: int) -> List[CaseResult]:
        """Search all 3 court collections in parallel (Seznam/retromae)"""
        court_sources = [
            DataSource.CONSTITUTIONAL_COURT,
            DataSource.SUPREME_COURT,
            DataSource.SUPREME_ADMIN_COURT,
        ]
        
        # All 3 use same embedding model (Seznam), generate once
        config = get_configs()[DataSource.CONSTITUTIONAL_COURT]
        vector = embedding_manager.get_embedding(query, config.embedding_model)
        
        print(f"🔍 Searching 3 courts in parallel...")
        
        # Search all in parallel
        tasks = [
            self._execute_search_with_vector(source, vector, limit // 3 + 5)
            for source in court_sources
        ]
        
        all_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Merge results
        merged = []
        for source, results in zip(court_sources, all_results):
            if isinstance(results, Exception):
                print(f"⚠️ Error from {source.value}: {results}")
                continue
            if results:
                source_config = get_configs()[source]
                for r in results:
                    # Tag with data source
                    r.data_source = source.value
                    # Court is already set from _convert_results (uses display_name)
                merged.extend(results)
                print(f"   ✓ {source_config.display_name}: {len(results)} results")
        
        # Sort by score
        merged.sort(key=lambda x: x.relevance_score, reverse=True)
        return merged
    
    async def _search_single_source(
        self, query: str, source: DataSource, limit: int
    ) -> List[CaseResult]:
        """Search a single collection"""
        configs = get_configs()
        config = configs.get(source)
        if not config:
            return []
        
        vector = embedding_manager.get_embedding(query, config.embedding_model)
        return await self._execute_search_with_vector(source, vector, limit)
    
    async def _execute_search_with_vector(
        self, source: DataSource, vector: List[float], limit: int
    ) -> List[CaseResult]:
        """Execute search with pre-computed vector"""
        configs = get_configs()
        config = configs.get(source)
        if not config:
            return []
        
        for attempt in range(self.max_retries):
            try:
                timeout = self.initial_timeout * (2 ** attempt)
                
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        f"{self.qdrant_url}/collections/{config.name}/points/search",
                        headers=self.headers,
                        json={
                            "vector": vector,
                            "limit": limit * 2 if config.uses_chunking else limit,
                            "with_payload": True,
                        }
                    )
                    
                    if response.status_code == 200:
                        results = response.json().get('result', [])
                        cases = self._convert_results(results, config)
                        
                        if config.uses_chunking:
                            cases = self._deduplicate_chunks(cases, limit)
                        
                        return cases[:limit]
                    
                    if 400 <= response.status_code < 500:
                        print(f"❌ Client error {response.status_code}: {response.text[:100]}")
                        return []
                    
            except httpx.TimeoutException:
                print(f"⏱️ Timeout attempt {attempt + 1}")
            except Exception as e:
                print(f"❌ Error attempt {attempt + 1}: {e}")
            
            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)
        
        return []
    
    def _convert_results(self, results: List[Dict], config: CollectionConfig) -> List[CaseResult]:
        """
        Convert Qdrant results to CaseResult
        
        Handles different payload structures:
        - New courts: case_number, date, chunk_text, full_text (no court field)
        - Supreme court: has 'source' field
        - Legacy: case_number, subject, court, date_issued
        """
        cases = []
        for result in results:
            payload = result.get("payload", {})
            score = result.get("score", 0.0)
            
            # Get text content
            if config.uses_chunking:
                # Prefer full_text if available (chunk_index=0), else chunk_text
                subject = payload.get(config.full_text_field) or payload.get(config.chunk_text_field, "")
            else:
                subject = payload.get(config.text_field, "")
            
            # Get court name - use display_name as fallback (new collections don't have court field)
            court = payload.get(config.court_field) or config.display_name
            
            cases.append(CaseResult(
                case_number=payload.get(config.case_number_field, "N/A"),
                court=court,
                judge=payload.get("judge"),
                subject=subject,
                date_issued=payload.get(config.date_field),
                date_published=payload.get("date_published"),
                ecli=payload.get("ecli"),
                keywords=payload.get("keywords", []),
                legal_references=payload.get("legal_references", []),
                source_url=payload.get("source_url"),
                relevance_score=score,
                data_source=None,
            ))
        return cases
    
    def _deduplicate_chunks(self, cases: List[CaseResult], limit: int) -> List[CaseResult]:
        """Deduplicate chunked results - keep best chunk per case"""
        seen: Dict[str, CaseResult] = {}
        for case in cases:
            key = case.case_number
            if key not in seen or case.relevance_score > seen[key].relevance_score:
                seen[key] = case
        
        result = list(seen.values())
        result.sort(key=lambda x: x.relevance_score, reverse=True)
        return result[:limit]
    
    def _deduplicate_results(self, cases: List[CaseResult]) -> List[CaseResult]:
        """Deduplicate across all sources"""
        seen: Dict[str, CaseResult] = {}
        for case in cases:
            key = case.case_number
            if key not in seen or case.relevance_score > seen[key].relevance_score:
                seen[key] = case
        
        result = list(seen.values())
        result.sort(key=lambda x: x.relevance_score, reverse=True)
        return result
    
    async def _rerank_with_llm(
        self, query: str, cases: List[CaseResult]
    ) -> List[CaseResult]:
        """Rerank using GPT-5-nano via LLM service"""
        try:
            from app.services.llm import llm_service
            return await llm_service.rerank_cases(query, cases)
        except Exception as e:
            print(f"⚠️ Reranking failed: {e}")
            return cases
    
    async def search_collection(
        self, query: str, source: DataSource, limit: int = 10
    ) -> List[CaseResult]:
        """Backward compatible search method"""
        return await self.orchestrated_search(query, source, limit, rerank=False)
    
    async def multi_query_search(
        self,
        queries: List[str],
        source: DataSource = DataSource.ALL_COURTS,
        results_per_query: int = 10,
        final_limit: int = 5,
    ) -> List[CaseResult]:
        """
        Multi-query search with RRF (Reciprocal Rank Fusion)
        Default: searches all 3 courts
        """
        print(f"\n🔍 Multi-query search: {len(queries)} queries → {source.value}")
        
        # Execute searches in parallel
        tasks = [
            self.orchestrated_search(q, source, results_per_query, rerank=False)
            for q in queries
        ]
        all_results = await asyncio.gather(*tasks)
        
        # RRF fusion (k=60 is standard)
        case_scores: Dict[str, Dict[str, Any]] = {}
        
        for query_results in all_results:
            for rank, case in enumerate(query_results, 1):
                key = case.case_number
                rrf_score = 1.0 / (60 + rank)
                
                if key not in case_scores:
                    case_scores[key] = {
                        'case': case,
                        'rrf_score': rrf_score,
                        'max_score': case.relevance_score,
                        'query_hits': 1,
                    }
                else:
                    case_scores[key]['rrf_score'] += rrf_score
                    case_scores[key]['max_score'] = max(
                        case_scores[key]['max_score'],
                        case.relevance_score
                    )
                    case_scores[key]['query_hits'] += 1
        
        # Sort by RRF score (cases appearing in multiple queries rank higher)
        merged = []
        for data in case_scores.values():
            case = data['case']
            case.relevance_score = data['max_score']
            merged.append((data['rrf_score'], data['query_hits'], case))
        
        # Sort by RRF, then by query hits
        merged.sort(key=lambda x: (x[0], x[1]), reverse=True)
        
        print(f"✅ RRF merged: {len(merged)} unique cases")
        return [case for _, _, case in merged[:final_limit]]
    
    async def get_available_sources(self) -> List[Dict[str, Any]]:
        """Get available sources with status"""
        sources = []
        configs = get_configs()
        
        for source, config in configs.items():
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.get(
                        f"{self.qdrant_url}/collections/{config.name}",
                        headers=self.headers,
                    )
                    if response.status_code == 200:
                        info = response.json().get('result', {})
                        points_count = info.get('points_count', 0)
                        status = "available"
                    else:
                        points_count = 0
                        status = "unavailable"
            except Exception:
                points_count = 0
                status = "error"
            
            sources.append({
                "id": source.value,
                "name": config.display_name,
                "description": config.description,
                "collection": config.name,
                "embedding_model": config.embedding_model,
                "vector_size": config.vector_size,
                "points_count": points_count,
                "status": status,
            })
        
        return sources


# Global instance
multi_source_engine = MultiSourceSearchEngine()
