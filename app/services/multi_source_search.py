"""
Multi-Source Search Service with Robust Orchestration
Supports multiple Qdrant collections with reranking and quality optimization
Default: All 3 court collections (Seznam/retromae-small-cs)

Optimized for:
- Reliability (graceful fallbacks)
- Speed (parallel searches, connection pooling)
- Quality (entity boosting, document aggregation)
"""
import asyncio
import math
import re
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum
from dataclasses import dataclass, field
import httpx
from sentence_transformers import SentenceTransformer

from app.config import settings
from app.models import CaseResult


# =============================================================================
# LEGAL ENTITY EXTRACTION (lightweight, no external deps)
# =============================================================================

@dataclass
class LegalEntities:
    """Extracted legal entities from a query"""
    statutes: List[str] = field(default_factory=list)
    case_numbers: List[str] = field(default_factory=list)
    courts: List[str] = field(default_factory=list)


def extract_legal_entities(query: str) -> LegalEntities:
    """Extract legal entities from query for boosting (fast, regex-based)"""
    entities = LegalEntities()
    query_lower = query.lower()
    
    # Extract statute references
    statute_pattern = r'§\s*\d+[a-z]?(?:\s*odst\.\s*\d+)?'
    entities.statutes = re.findall(statute_pattern, query, re.IGNORECASE)
    
    # Extract case numbers
    case_pattern = r'\d+\s*[A-Za-z]+\s*\d+/\d{2,4}'
    entities.case_numbers = re.findall(case_pattern, query, re.IGNORECASE)
    
    # Extract court names
    court_keywords = {
        'ústavní soud': 'Ústavní soud',
        'nejvyšší soud': 'Nejvyšší soud',
        'nejvyšší správní': 'Nejvyšší správní soud',
    }
    for keyword, court_name in court_keywords.items():
        if keyword in query_lower:
            entities.courts.append(court_name)
    
    return entities


def boost_by_entity_match(cases: List[CaseResult], entities: LegalEntities) -> List[CaseResult]:
    """Boost cases matching extracted entities"""
    if not entities.case_numbers and not entities.courts and not entities.statutes:
        return cases
    
    for case in cases:
        boost = 1.0
        case_text = f"{case.case_number} {case.subject or ''} {case.court or ''}".lower()
        
        for case_num in entities.case_numbers:
            if case_num.lower() in case.case_number.lower():
                boost *= 2.0
                break
        
        for court in entities.courts:
            if court.lower() in (case.court or '').lower():
                boost *= 1.2
                break
        
        for statute in entities.statutes:
            if statute.lower() in case_text:
                boost *= 1.1
                break
        
        case.relevance_score *= boost
    
    cases.sort(key=lambda x: x.relevance_score, reverse=True)
    return cases


# =============================================================================
# DATA SOURCE CONFIGURATION
# =============================================================================

class DataSource(str, Enum):
    CONSTITUTIONAL_COURT = "constitutional_court"
    SUPREME_COURT = "supreme_court"
    SUPREME_ADMIN_COURT = "supreme_admin_court"
    ALL_COURTS = "all_courts"
    GENERAL_COURTS = "general_courts"


@dataclass
class CollectionConfig:
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
    return {
        DataSource.CONSTITUTIONAL_COURT: CollectionConfig(
            name=settings.QDRANT_CONSTITUTIONAL_COURT,
            embedding_model=settings.SEZNAM_EMBEDDING_MODEL,
            vector_size=settings.SEZNAM_VECTOR_SIZE,
            display_name="Ústavní soud",
            description="Nálezy a usnesení Ústavního soudu ČR",
            text_field="chunk_text",
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
            description="Rozhodnutí Nejvyššího soudu ČR",
            text_field="chunk_text",
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
            description="Rozhodnutí Nejvyššího správního soudu ČR",
            text_field="chunk_text",
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
            uses_chunking=False,
        ),
    }


_COLLECTION_CONFIGS: Optional[Dict[DataSource, CollectionConfig]] = None


def get_configs() -> Dict[DataSource, CollectionConfig]:
    global _COLLECTION_CONFIGS
    if _COLLECTION_CONFIGS is None:
        _COLLECTION_CONFIGS = get_collection_configs()
    return _COLLECTION_CONFIGS


# =============================================================================
# EMBEDDING MODEL MANAGER
# =============================================================================

class EmbeddingModelManager:
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


# =============================================================================
# DOCUMENT AGGREGATION
# =============================================================================

def aggregate_chunk_scores(cases: List[CaseResult], top_k: int = 20) -> List[CaseResult]:
    """Aggregate chunk scores - cases with multiple relevant chunks get boosted"""
    doc_scores: Dict[str, Dict[str, Any]] = {}
    
    for case in cases:
        key = case.case_number
        if key not in doc_scores:
            doc_scores[key] = {
                'case': case,
                'max_score': case.relevance_score,
                'chunk_count': 1,
            }
        else:
            if case.relevance_score > doc_scores[key]['max_score']:
                doc_scores[key]['case'] = case
                doc_scores[key]['max_score'] = case.relevance_score
            doc_scores[key]['chunk_count'] += 1
    
    results = []
    for data in doc_scores.values():
        case = data['case']
        chunk_boost = math.log(data['chunk_count'] + 1)
        case.relevance_score = data['max_score'] * chunk_boost
        results.append(case)
    
    results.sort(key=lambda x: x.relevance_score, reverse=True)
    return results[:top_k]


# =============================================================================
# MAIN SEARCH ENGINE - ROBUST & OPTIMIZED
# =============================================================================

class MultiSourceSearchEngine:
    """
    Robust search engine with graceful fallbacks
    - Connection pooling with proper timeouts
    - Parallel searches with error isolation
    - Graceful degradation on failures
    """
    
    def __init__(self):
        self.qdrant_url = settings.qdrant_url
        self.headers = {"api-key": settings.QDRANT_API_KEY} if settings.QDRANT_API_KEY else {}
        self.max_retries = settings.QDRANT_MAX_RETRIES
        self.initial_timeout = settings.QDRANT_INITIAL_TIMEOUT
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with robust settings"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    timeout=self.initial_timeout,
                    connect=30.0,
                    read=self.initial_timeout,
                    write=30.0,
                ),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._client
    
    async def _close_client(self):
        """Close client to reset connections"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def orchestrated_search(
        self,
        query: str,
        source: DataSource = DataSource.ALL_COURTS,
        limit: int = 10,
        rerank: bool = True,
    ) -> List[CaseResult]:
        """
        Main search with robust error handling
        
        Pipeline:
        1. Vector search (parallel across courts)
        2. Deduplicate and aggregate
        3. Fetch full text from chunk 0 for each case
        4. Entity boosting
        5. LLM reranking (optional)
        """
        print(f"\n{'='*60}")
        print(f"🎯 SEARCH: {source.value}")
        print(f"   Query: {query[:80]}...")
        print(f"{'='*60}")
        
        # Extract entities for boosting
        entities = extract_legal_entities(query)
        
        # Get results
        if source == DataSource.ALL_COURTS:
            raw_results = await self._search_all_courts(query, limit * 2)
        else:
            raw_results = await self._search_single_source(query, source, limit * 2)
        
        if not raw_results:
            print("⚠️ No results found")
            return []
        
        print(f"📊 Raw results: {len(raw_results)}")
        
        # Aggregate chunks
        aggregated = aggregate_chunk_scores(raw_results, top_k=limit * 3)
        print(f"📊 After aggregation: {len(aggregated)}")
        
        # Fetch full text from chunk 0 for each case
        enriched = await self._enrich_with_full_text(aggregated, source)
        print(f"📊 After enrichment: {len(enriched)} cases with full text")
        
        # Entity boosting
        boosted = boost_by_entity_match(enriched, entities)
        
        # Filter by relevance
        filtered = [r for r in boosted if r.relevance_score >= settings.MIN_RELEVANCE_SCORE]
        if not filtered:
            filtered = boosted[:limit]
        
        print(f"📊 After filter: {len(filtered)}")
        
        # Rerank
        if rerank and len(filtered) > limit:
            try:
                reranked = await self._rerank_with_llm(query, filtered[:settings.RERANK_TOP_K])
                final = reranked[:limit]
            except Exception as e:
                print(f"⚠️ Reranking failed: {e}, using score-based ranking")
                final = filtered[:limit]
        else:
            final = filtered[:limit]
        
        print(f"✅ Final: {len(final)} results")
        return final
    
    async def _search_all_courts(self, query: str, limit: int) -> List[CaseResult]:
        """Search all 3 courts in parallel with error isolation"""
        court_sources = [
            DataSource.CONSTITUTIONAL_COURT,
            DataSource.SUPREME_COURT,
            DataSource.SUPREME_ADMIN_COURT,
        ]
        
        # Generate embedding once
        config = get_configs()[DataSource.CONSTITUTIONAL_COURT]
        vector = embedding_manager.get_embedding(query, config.embedding_model)
        
        print(f"🔍 Searching 3 courts in parallel...")
        
        # Search in parallel with individual error handling
        tasks = [
            self._safe_search(source, vector, limit // 3 + 5)
            for source in court_sources
        ]
        
        results = await asyncio.gather(*tasks)
        
        # Merge successful results
        merged = []
        for source, result in zip(court_sources, results):
            if result:
                config = get_configs()[source]
                for r in result:
                    r.data_source = source.value
                merged.extend(result)
                print(f"   ✓ {config.display_name}: {len(result)} results")
            else:
                config = get_configs()[source]
                print(f"   ✗ {config.display_name}: no results")
        
        merged.sort(key=lambda x: x.relevance_score, reverse=True)
        return merged
    
    async def _safe_search(
        self, source: DataSource, vector: List[float], limit: int
    ) -> List[CaseResult]:
        """Search with error isolation - never raises, returns empty on failure"""
        try:
            return await self._execute_search(source, vector, limit)
        except Exception as e:
            config = get_configs().get(source)
            name = config.display_name if config else source.value
            print(f"⚠️ Search failed for {name}: {e}")
            return []
    
    async def _search_single_source(
        self, query: str, source: DataSource, limit: int
    ) -> List[CaseResult]:
        """Search single collection"""
        config = get_configs().get(source)
        if not config:
            return []
        
        vector = embedding_manager.get_embedding(query, config.embedding_model)
        return await self._safe_search(source, vector, limit)
    
    async def _execute_search(
        self, source: DataSource, vector: List[float], limit: int
    ) -> List[CaseResult]:
        """Execute search with retries"""
        config = get_configs().get(source)
        if not config:
            return []
        
        client = await self._get_client()
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                timeout = self.initial_timeout + (attempt * 30)
                
                response = await client.post(
                    f"{self.qdrant_url}/collections/{config.name}/points/search",
                    headers=self.headers,
                    json={
                        "vector": vector,
                        "limit": limit * 2 if config.uses_chunking else limit,
                        "with_payload": True,
                    },
                    timeout=timeout,
                )
                
                if response.status_code == 200:
                    results = response.json().get('result', [])
                    cases = self._convert_results(results, config)
                    
                    if config.uses_chunking:
                        cases = self._deduplicate_chunks(cases, limit)
                    
                    return cases[:limit]
                
                if 400 <= response.status_code < 500:
                    print(f"❌ Client error {response.status_code}")
                    return []
                
                last_error = f"HTTP {response.status_code}"
                    
            except httpx.TimeoutException:
                last_error = f"Timeout ({timeout}s)"
                print(f"⏱️ {config.display_name}: {last_error}, attempt {attempt + 1}/{self.max_retries}")
            except httpx.ConnectError as e:
                last_error = f"Connection error"
                print(f"🔌 {config.display_name}: {last_error}")
                # Reset client on connection error
                await self._close_client()
            except Exception as e:
                last_error = str(e)
                print(f"❌ {config.display_name}: {last_error}")
            
            if attempt < self.max_retries - 1:
                await asyncio.sleep(1 + attempt)
        
        print(f"⚠️ {config.display_name}: All retries failed ({last_error})")
        return []
    
    def _convert_results(self, results: List[Dict], config: CollectionConfig) -> List[CaseResult]:
        """Convert Qdrant results to CaseResult"""
        cases = []
        for result in results:
            payload = result.get("payload", {})
            score = result.get("score", 0.0)
            
            if config.uses_chunking:
                subject = payload.get(config.full_text_field) or payload.get(config.chunk_text_field, "")
            else:
                subject = payload.get(config.text_field, "")
            
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
        """Keep best chunk per case"""
        seen: Dict[str, CaseResult] = {}
        for case in cases:
            key = case.case_number
            if key not in seen or case.relevance_score > seen[key].relevance_score:
                seen[key] = case
        
        result = list(seen.values())
        result.sort(key=lambda x: x.relevance_score, reverse=True)
        return result[:limit]
    
    async def _enrich_with_full_text(
        self, cases: List[CaseResult], source: DataSource
    ) -> List[CaseResult]:
        """
        Fetch full text for each case
        
        Handles two collection types:
        1. Chunked collections (3 courts): full_text is in chunk_index=0
        2. Legacy collection (czech_court_decisions_rag): full_text is in payload directly
        
        This ensures we have complete document text for better LLM analysis.
        """
        if source == DataSource.ALL_COURTS:
            # Group cases by source court
            cases_by_source: Dict[DataSource, List[CaseResult]] = {}
            for case in cases:
                src = DataSource(case.data_source) if case.data_source else DataSource.SUPREME_COURT
                if src not in cases_by_source:
                    cases_by_source[src] = []
                cases_by_source[src].append(case)
            
            # Enrich each group
            enriched = []
            for src, src_cases in cases_by_source.items():
                enriched.extend(await self._enrich_with_full_text(src_cases, src))
            return enriched
        
        config = get_configs().get(source)
        if not config:
            return cases
        
        # Legacy collection (czech_court_decisions_rag) - no chunking, already has full_text
        if not config.uses_chunking:
            return cases
        
        # Chunked collections - need to fetch chunk 0
        client = await self._get_client()
        enriched_cases = []
        
        for case in cases:
            try:
                # Query for chunk 0 of this case
                response = await client.post(
                    f"{self.qdrant_url}/collections/{config.name}/points/search",
                    headers=self.headers,
                    json={
                        "filter": {
                            "must": [
                                {"key": "case_number", "match": {"value": case.case_number}},
                                {"key": "chunk_index", "match": {"value": 0}},
                            ]
                        },
                        "limit": 1,
                        "with_payload": True,
                    },
                    timeout=30,
                )
                
                if response.status_code == 200:
                    results = response.json().get('result', [])
                    if results:
                        payload = results[0].get("payload", {})
                        full_text = payload.get(config.full_text_field, "")
                        if full_text:
                            case.subject = full_text
                            print(f"   ✓ Fetched full text for {case.case_number}")
                        else:
                            print(f"   ⚠️ No full_text in chunk 0 for {case.case_number}")
                    else:
                        print(f"   ⚠️ Chunk 0 not found for {case.case_number}")
                else:
                    print(f"   ⚠️ Failed to fetch chunk 0 for {case.case_number}")
            except Exception as e:
                print(f"   ⚠️ Error fetching full text for {case.case_number}: {e}")
            
            enriched_cases.append(case)
        
        return enriched_cases
    
    def _deduplicate_results(self, cases: List[CaseResult]) -> List[CaseResult]:
        """Deduplicate across sources"""
        seen: Dict[str, CaseResult] = {}
        for case in cases:
            key = case.case_number
            if key not in seen or case.relevance_score > seen[key].relevance_score:
                seen[key] = case
        
        result = list(seen.values())
        result.sort(key=lambda x: x.relevance_score, reverse=True)
        return result
    
    async def _rerank_with_llm(self, query: str, cases: List[CaseResult]) -> List[CaseResult]:
        """Rerank using LLM"""
        try:
            from app.services.llm import llm_service
            return await llm_service.rerank_cases(query, cases)
        except Exception as e:
            print(f"⚠️ Reranking failed: {e}")
            return cases
    
    async def search_collection(
        self, query: str, source: DataSource, limit: int = 10
    ) -> List[CaseResult]:
        """Backward compatible method"""
        return await self.orchestrated_search(query, source, limit, rerank=False)


    async def multi_query_search(
        self,
        queries: List[str],
        source: DataSource = DataSource.ALL_COURTS,
        results_per_query: int = 10,
        final_limit: int = 5,
        original_query: str = None,
    ) -> List[CaseResult]:
        """
        Multi-query search with RRF fusion
        Robust version with graceful error handling
        """
        print(f"\n🔍 Multi-query search: {len(queries)} queries → {source.value}")
        
        # Use first query or original for entity extraction
        base_query = original_query or queries[0]
        entities = extract_legal_entities(base_query)
        
        # Generate embedding once (all courts use same model)
        config = get_configs()[DataSource.CONSTITUTIONAL_COURT]
        print(f"🧠 Computing embeddings...")
        vectors = [
            embedding_manager.get_embedding(q, config.embedding_model)
            for q in queries
        ]
        
        # Determine courts to search
        if source == DataSource.ALL_COURTS:
            court_sources = [
                DataSource.CONSTITUTIONAL_COURT,
                DataSource.SUPREME_COURT,
                DataSource.SUPREME_ADMIN_COURT,
            ]
        else:
            court_sources = [source]
        
        # Search all combinations in parallel
        print(f"🔍 Searching {len(queries)} queries × {len(court_sources)} courts...")
        
        tasks = []
        for vector in vectors:
            for court in court_sources:
                tasks.append(self._safe_search(court, vector, results_per_query))
        
        all_results = await asyncio.gather(*tasks)
        
        # Count results
        total_results = sum(len(r) for r in all_results if r)
        print(f"📊 Got {total_results} total results")
        
        # RRF fusion
        case_scores: Dict[str, Dict[str, Any]] = {}
        
        idx = 0
        for q_idx, _ in enumerate(queries):
            for court in court_sources:
                results = all_results[idx]
                idx += 1
                
                if not results:
                    continue
                
                for rank, case in enumerate(results, 1):
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
        
        if not case_scores:
            print("⚠️ No results after fusion")
            return []
        
        # Sort by RRF score
        merged = []
        for data in case_scores.values():
            case = data['case']
            case.relevance_score = data['max_score']
            merged.append((data['rrf_score'], data['query_hits'], case))
        
        merged.sort(key=lambda x: (x[0], x[1]), reverse=True)
        
        # Extract cases and enrich with full text
        final_cases = [case for _, _, case in merged[:final_limit * 2]]
        enriched = await self._enrich_with_full_text(final_cases, source)
        
        # Apply entity boosting
        boosted = boost_by_entity_match(enriched, entities)
        
        print(f"✅ RRF merged: {len(case_scores)} unique → {len(boosted[:final_limit])} final")
        return boosted[:final_limit]
    
    async def get_available_sources(self) -> List[Dict[str, Any]]:
        """Get available sources with status"""
        sources = []
        configs = get_configs()
        
        for source, config in configs.items():
            try:
                client = await self._get_client()
                response = await client.get(
                    f"{self.qdrant_url}/collections/{config.name}",
                    headers=self.headers,
                    timeout=10,
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
