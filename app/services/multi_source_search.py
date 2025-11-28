"""
Multi-Source Search Service
Supports multiple Qdrant collections with different embedding models
Allows frontend to toggle between data sources
"""
import asyncio
from typing import List, Optional, Dict, Any, Literal
from enum import Enum
from dataclasses import dataclass
import httpx
from sentence_transformers import SentenceTransformer

from app.config import settings
from app.models import CaseResult


class DataSource(str, Enum):
    """Available data sources for legal search"""
    # Original collection - uses paraphrase-multilingual-MiniLM-L12-v2 (384 dim)
    GENERAL_COURTS = "general_courts"
    
    # New collections - use Seznam/retromae-small-cs (256 dim)
    CONSTITUTIONAL_COURT = "constitutional_court"
    SUPREME_COURT = "supreme_court"
    SUPREME_ADMIN_COURT = "supreme_admin_court"
    
    # Search all sources
    ALL = "all"


@dataclass
class CollectionConfig:
    """Configuration for a Qdrant collection"""
    name: str
    embedding_model: str
    vector_size: int
    display_name: str
    description: str
    # Payload field mappings (different collections may have different field names)
    case_number_field: str = "case_number"
    text_field: str = "subject"  # Main text field for context
    court_field: str = "court"
    date_field: str = "date_issued"
    # Whether this collection uses chunking
    uses_chunking: bool = False
    chunk_text_field: str = "chunk_text"
    full_text_field: str = "full_text"


def get_collection_configs() -> Dict[DataSource, CollectionConfig]:
    """
    Get collection configurations using settings values
    This is a function to ensure settings are loaded before accessing
    """
    return {
        DataSource.GENERAL_COURTS: CollectionConfig(
            name=settings.QDRANT_COLLECTION,  # Original collection from env
            embedding_model=settings.EMBEDDING_MODEL,
            vector_size=384,
            display_name="Obecné soudy",
            description="Rozhodnutí obecných soudů ČR",
            case_number_field="case_number",
            text_field="subject",
            court_field="court",
            date_field="date_issued",
            uses_chunking=False,
        ),
        DataSource.CONSTITUTIONAL_COURT: CollectionConfig(
            name=settings.QDRANT_CONSTITUTIONAL_COURT,
            embedding_model=settings.SEZNAM_EMBEDDING_MODEL,
            vector_size=settings.SEZNAM_VECTOR_SIZE,
            display_name="Ústavní soud",
            description="Nálezy a usnesení Ústavního soudu ČR",
            case_number_field="case_number",
            text_field="chunk_text",
            court_field="court",
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
            case_number_field="case_number",
            text_field="chunk_text",
            court_field="court",
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
            case_number_field="case_number",
            text_field="chunk_text",
            court_field="court",
            date_field="date",
            uses_chunking=True,
            chunk_text_field="chunk_text",
            full_text_field="full_text",
        ),
    }


# Lazy-loaded collection configs
COLLECTION_CONFIGS: Optional[Dict[DataSource, CollectionConfig]] = None


def get_configs() -> Dict[DataSource, CollectionConfig]:
    """Get or initialize collection configs"""
    global COLLECTION_CONFIGS
    if COLLECTION_CONFIGS is None:
        COLLECTION_CONFIGS = get_collection_configs()
    return COLLECTION_CONFIGS


class EmbeddingModelManager:
    """
    Manages multiple embedding models for different collections
    Lazy loads models to save memory
    """
    
    def __init__(self):
        self._models: Dict[str, SentenceTransformer] = {}
    
    def get_model(self, model_name: str) -> SentenceTransformer:
        """Get or load an embedding model"""
        if model_name not in self._models:
            print(f"🧠 Loading embedding model: {model_name}")
            self._models[model_name] = SentenceTransformer(model_name, device="cpu")
            print(f"✅ Model loaded: {model_name}")
        return self._models[model_name]
    
    def get_embedding(self, text: str, model_name: str) -> List[float]:
        """Generate embedding for text using specified model"""
        model = self.get_model(model_name)
        # Seznam model uses normalized embeddings
        normalize = "retromae" in model_name.lower()
        embedding = model.encode(text, normalize_embeddings=normalize)
        return embedding.tolist()
    
    def get_embeddings_batch(self, texts: List[str], model_name: str) -> List[List[float]]:
        """Generate embeddings for multiple texts"""
        model = self.get_model(model_name)
        normalize = "retromae" in model_name.lower()
        embeddings = model.encode(texts, normalize_embeddings=normalize)
        return [e.tolist() for e in embeddings]


# Global embedding manager
embedding_manager = EmbeddingModelManager()


class MultiSourceSearchEngine:
    """
    Search engine that supports multiple Qdrant collections
    with different embedding models
    """
    
    def __init__(self):
        self.qdrant_url = settings.qdrant_url
        self.headers = {"api-key": settings.QDRANT_API_KEY} if settings.QDRANT_API_KEY else {}
        self.max_retries = settings.QDRANT_MAX_RETRIES
        self.initial_timeout = settings.QDRANT_INITIAL_TIMEOUT

    async def search_collection(
        self,
        query: str,
        source: DataSource,
        limit: int = 10,
    ) -> List[CaseResult]:
        """
        Search a specific collection
        
        Args:
            query: Search query text
            source: Data source to search
            limit: Number of results to return
        
        Returns:
            List of CaseResult objects
        """
        if source == DataSource.ALL:
            return await self.search_all_sources(query, limit)
        
        configs = get_configs()
        config = configs.get(source)
        if not config:
            print(f"❌ Unknown data source: {source}")
            return []
        
        try:
            print(f"\n{'='*60}")
            print(f"🔍 Searching: {config.display_name}")
            print(f"   Collection: {config.name}")
            print(f"   Model: {config.embedding_model}")
            print(f"   Query: {query[:100]}...")
            
            # Generate embedding with the correct model
            vector = embedding_manager.get_embedding(query, config.embedding_model)
            print(f"   Vector size: {len(vector)}")
            
            # Execute search
            results = await self._execute_search(config, vector, limit)
            
            print(f"✅ Found {len(results)} results from {config.display_name}")
            return results
            
        except Exception as e:
            print(f"❌ Error searching {config.display_name}: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    async def search_all_sources(
        self,
        query: str,
        limit_per_source: int = 5,
    ) -> List[CaseResult]:
        """
        Search all available sources and merge results
        
        Args:
            query: Search query text
            limit_per_source: Results per source
        
        Returns:
            Merged list of CaseResult objects
        """
        print(f"\n{'='*60}")
        print(f"🔍 Searching ALL sources")
        print(f"{'='*60}")
        
        # Search all sources in parallel
        sources = [s for s in DataSource if s != DataSource.ALL]
        
        tasks = [
            self.search_collection(query, source, limit_per_source)
            for source in sources
        ]
        
        all_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Merge results
        merged = []
        for source, results in zip(sources, all_results):
            if isinstance(results, Exception):
                print(f"⚠️ Error from {source}: {results}")
                continue
            if results:
                # Tag results with source
                configs = get_configs()
                for r in results:
                    # Add source info to court field if not already there
                    config = configs.get(source)
                    if config and config.display_name not in r.court:
                        r.court = f"{r.court} ({config.display_name})"
                merged.extend(results)
        
        # Sort by relevance score
        merged.sort(key=lambda x: x.relevance_score, reverse=True)
        
        print(f"✅ Total merged results: {len(merged)}")
        return merged
    
    async def _execute_search(
        self,
        config: CollectionConfig,
        vector: List[float],
        limit: int,
    ) -> List[CaseResult]:
        """Execute search against a specific collection"""
        
        for attempt in range(self.max_retries):
            try:
                timeout = self.initial_timeout * (2 ** attempt)
                
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        f"{self.qdrant_url}/collections/{config.name}/points/search",
                        headers=self.headers,
                        json={
                            "vector": vector,
                            "limit": limit * 2 if config.uses_chunking else limit,  # Get more for dedup
                            "with_payload": True,
                        }
                    )
                    
                    if response.status_code == 200:
                        results = response.json()
                        result_list = results.get('result', [])
                        
                        # Convert to CaseResult objects
                        cases = self._convert_results(result_list, config)
                        
                        # Deduplicate if chunked (same case may appear multiple times)
                        if config.uses_chunking:
                            cases = self._deduplicate_chunked_results(cases, limit)
                        
                        return cases[:limit]
                    
                    if 400 <= response.status_code < 500:
                        print(f"  ❌ Client error: {response.status_code} - {response.text[:200]}")
                        return []
                    
                    print(f"  ⚠️ Server error: {response.status_code}")
                    
            except httpx.TimeoutException:
                print(f"  ⏱️ Timeout (attempt {attempt + 1})")
            except Exception as e:
                print(f"  ❌ Error (attempt {attempt + 1}): {e}")
            
            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)
        
        return []
    
    def _convert_results(
        self,
        results: List[Dict],
        config: CollectionConfig,
    ) -> List[CaseResult]:
        """Convert Qdrant results to CaseResult objects"""
        cases = []
        
        for result in results:
            payload = result.get("payload", {})
            score = result.get("score", 0.0)
            
            # Get text content based on collection type
            if config.uses_chunking:
                # For chunked collections, prefer full_text if available (chunk 0)
                subject = payload.get(config.full_text_field) or payload.get(config.chunk_text_field, "")
            else:
                subject = payload.get(config.text_field, "")
            
            # Build CaseResult with flexible field mapping
            case = CaseResult(
                case_number=payload.get(config.case_number_field, "N/A"),
                court=payload.get(config.court_field, config.display_name),
                judge=payload.get("judge"),
                subject=subject,
                date_issued=payload.get(config.date_field),
                date_published=payload.get("date_published"),
                ecli=payload.get("ecli"),
                keywords=payload.get("keywords", []),
                legal_references=payload.get("legal_references", []),
                source_url=payload.get("source_url"),
                relevance_score=score,
            )
            cases.append(case)
        
        return cases
    
    def _deduplicate_chunked_results(
        self,
        cases: List[CaseResult],
        limit: int,
    ) -> List[CaseResult]:
        """
        Deduplicate results from chunked collections
        Keep the highest scoring chunk for each case
        """
        seen_cases: Dict[str, CaseResult] = {}
        
        for case in cases:
            case_id = case.case_number
            if case_id not in seen_cases:
                seen_cases[case_id] = case
            elif case.relevance_score > seen_cases[case_id].relevance_score:
                seen_cases[case_id] = case
        
        # Sort by score and return
        deduped = list(seen_cases.values())
        deduped.sort(key=lambda x: x.relevance_score, reverse=True)
        return deduped[:limit]
    
    async def multi_query_search(
        self,
        queries: List[str],
        source: DataSource,
        results_per_query: int = 10,
        final_limit: int = 5,
    ) -> List[CaseResult]:
        """
        Multi-query search with RRF fusion for a specific source
        
        Args:
            queries: List of search queries
            source: Data source to search
            results_per_query: Results per query
            final_limit: Final number of results
        
        Returns:
            Merged and ranked results
        """
        print(f"\n{'='*60}")
        print(f"🔍 Multi-query search: {source.value}")
        print(f"   Queries: {len(queries)}")
        print(f"{'='*60}")
        
        # Execute searches in parallel
        tasks = [
            self.search_collection(query, source, results_per_query)
            for query in queries
        ]
        
        all_results = await asyncio.gather(*tasks)
        
        # RRF fusion
        case_scores: Dict[str, Dict[str, Any]] = {}
        
        for query_idx, query_results in enumerate(all_results):
            for rank, case in enumerate(query_results, 1):
                case_id = case.case_number
                rrf_score = 1.0 / (60 + rank)
                
                if case_id not in case_scores:
                    case_scores[case_id] = {
                        'case': case,
                        'rrf_score': rrf_score,
                        'max_score': case.relevance_score,
                        'query_count': 1,
                    }
                else:
                    case_scores[case_id]['rrf_score'] += rrf_score
                    case_scores[case_id]['max_score'] = max(
                        case_scores[case_id]['max_score'],
                        case.relevance_score
                    )
                    case_scores[case_id]['query_count'] += 1
        
        # Sort by RRF score
        merged = []
        for case_id, data in case_scores.items():
            case = data['case']
            case.relevance_score = data['max_score']
            setattr(case, '_rrf_score', data['rrf_score'])
            merged.append(case)
        
        merged.sort(key=lambda x: getattr(x, '_rrf_score', 0), reverse=True)
        
        print(f"✅ Merged {len(merged)} unique cases, returning top {final_limit}")
        return merged[:final_limit]
    
    async def get_available_sources(self) -> List[Dict[str, Any]]:
        """
        Get list of available data sources with their status
        
        Returns:
            List of source info dictionaries
        """
        sources = []
        configs = get_configs()
        
        for source, config in configs.items():
            if source == DataSource.ALL:
                continue
            
            # Check if collection exists and get stats
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
                "uses_chunking": config.uses_chunking,
            })
        
        return sources


# Global instance
multi_source_engine = MultiSourceSearchEngine()
