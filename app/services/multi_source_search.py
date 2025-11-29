"""
Multi-Source Search Service - Simplified Pipeline
1. Generate legal search queries
2. Vector search across all collections
3. Quick relevance filtering
4. Fetch full text from chunk 0
5. Return relevant cases with full text
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
    uses_chunking: bool = False


def get_collection_configs() -> Dict[DataSource, CollectionConfig]:
    return {
        DataSource.CONSTITUTIONAL_COURT: CollectionConfig(
            name=settings.QDRANT_CONSTITUTIONAL_COURT,
            embedding_model=settings.SEZNAM_EMBEDDING_MODEL,
            vector_size=settings.SEZNAM_VECTOR_SIZE,
            display_name="Ústavní soud",
            uses_chunking=True,
        ),
        DataSource.SUPREME_COURT: CollectionConfig(
            name=settings.QDRANT_SUPREME_COURT,
            embedding_model=settings.SEZNAM_EMBEDDING_MODEL,
            vector_size=settings.SEZNAM_VECTOR_SIZE,
            display_name="Nejvyšší soud",
            uses_chunking=True,
        ),
        DataSource.SUPREME_ADMIN_COURT: CollectionConfig(
            name=settings.QDRANT_SUPREME_ADMIN_COURT,
            embedding_model=settings.SEZNAM_EMBEDDING_MODEL,
            vector_size=settings.SEZNAM_VECTOR_SIZE,
            display_name="Nejvyšší správní soud",
            uses_chunking=True,
        ),
        DataSource.GENERAL_COURTS: CollectionConfig(
            name=settings.QDRANT_COLLECTION,
            embedding_model=settings.EMBEDDING_MODEL,
            vector_size=384,
            display_name="Obecné soudy",
            uses_chunking=False,
        ),
    }


_CONFIGS: Optional[Dict[DataSource, CollectionConfig]] = None


def get_configs() -> Dict[DataSource, CollectionConfig]:
    global _CONFIGS
    if _CONFIGS is None:
        _CONFIGS = get_collection_configs()
    return _CONFIGS


class EmbeddingManager:
    """Simple embedding model manager"""
    
    def __init__(self):
        self._models: Dict[str, SentenceTransformer] = {}
    
    def get_embedding(self, text: str, model_name: str) -> List[float]:
        if model_name not in self._models:
            print(f"🧠 Loading: {model_name}")
            self._models[model_name] = SentenceTransformer(model_name, device="cpu")
        
        model = self._models[model_name]
        normalize = "retromae" in model_name.lower()
        return model.encode(text, normalize_embeddings=normalize).tolist()


embedding_manager = EmbeddingManager()


class MultiSourceSearchEngine:
    """
    Simplified search engine:
    1. Vector search
    2. Fetch full text
    3. Return results
    """
    
    def __init__(self):
        self.qdrant_url = settings.qdrant_url
        self.headers = {"api-key": settings.QDRANT_API_KEY} if settings.QDRANT_API_KEY else {}
        self.timeout = settings.QDRANT_INITIAL_TIMEOUT
    
    async def search(
        self,
        queries: List[str],
        source: DataSource = DataSource.ALL_COURTS,
        limit: int = 10,
    ) -> List[CaseResult]:
        """
        Simple search pipeline:
        1. Search all courts with all queries
        2. Deduplicate
        3. Fetch full text
        4. Return top results
        """
        print(f"\n🔍 Search: {len(queries)} queries")
        
        # Determine which courts to search
        if source == DataSource.ALL_COURTS:
            courts = [
                DataSource.CONSTITUTIONAL_COURT,
                DataSource.SUPREME_COURT,
                DataSource.SUPREME_ADMIN_COURT,
            ]
        else:
            courts = [source]
        
        # Generate embeddings for all queries
        config = get_configs()[courts[0]]
        vectors = [embedding_manager.get_embedding(q, config.embedding_model) for q in queries]
        
        # Search all courts with all queries in parallel
        tasks = []
        for vector in vectors:
            for court in courts:
                tasks.append(self._search_court(court, vector, limit))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Merge and deduplicate
        all_cases: Dict[str, CaseResult] = {}
        for result in results:
            if isinstance(result, Exception):
                continue
            for case in result:
                key = case.case_number
                if key not in all_cases or case.relevance_score > all_cases[key].relevance_score:
                    all_cases[key] = case
        
        # Sort by score
        sorted_cases = sorted(all_cases.values(), key=lambda x: x.relevance_score, reverse=True)
        top_cases = sorted_cases[:limit]
        
        print(f"📊 Found {len(all_cases)} unique cases, returning top {len(top_cases)}")
        
        # Fetch full text for top cases
        enriched = await self._fetch_full_texts(top_cases)
        
        return enriched
    
    async def _search_court(
        self, court: DataSource, vector: List[float], limit: int
    ) -> List[CaseResult]:
        """Search a single court"""
        config = get_configs().get(court)
        if not config:
            return []
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.qdrant_url}/collections/{config.name}/points/search",
                    headers=self.headers,
                    json={
                        "vector": vector,
                        "limit": limit * 2,
                        "with_payload": True,
                    },
                )
                
                if response.status_code != 200:
                    print(f"⚠️ {config.display_name}: HTTP {response.status_code}")
                    return []
                
                results = response.json().get('result', [])
                cases = []
                
                for r in results:
                    payload = r.get("payload", {})
                    score = r.get("score", 0.0)
                    
                    # Get text - prefer full_text, fallback to chunk_text
                    text = payload.get("full_text") or payload.get("chunk_text") or payload.get("subject", "")
                    
                    cases.append(CaseResult(
                        case_number=payload.get("case_number", "N/A"),
                        court=config.display_name,
                        judge=payload.get("judge"),
                        subject=text,
                        date_issued=payload.get("date") or payload.get("date_issued"),
                        ecli=payload.get("ecli"),
                        keywords=payload.get("keywords", []),
                        legal_references=payload.get("legal_references", []),
                        source_url=payload.get("source_url"),
                        relevance_score=score,
                        data_source=court.value,
                    ))
                
                # Deduplicate chunks - keep best per case
                seen: Dict[str, CaseResult] = {}
                for case in cases:
                    if case.case_number not in seen or case.relevance_score > seen[case.case_number].relevance_score:
                        seen[case.case_number] = case
                
                return list(seen.values())[:limit]
                
        except Exception as e:
            print(f"⚠️ {config.display_name}: {e}")
            return []
    
    async def _fetch_full_texts(self, cases: List[CaseResult]) -> List[CaseResult]:
        """Fetch full text from chunk 0 for each case"""
        print(f"📄 Fetching full text for {len(cases)} cases...")
        
        tasks = [self._fetch_full_text(case) for case in cases]
        results = await asyncio.gather(*tasks)
        
        return [r for r in results if r is not None]
    
    async def _fetch_full_text(self, case: CaseResult) -> Optional[CaseResult]:
        """Fetch full text for a single case from chunk 0"""
        # Skip if already has full text (legacy collection)
        if case.subject and len(case.subject) > 1000:
            return case
        
        # Determine collection
        source = DataSource(case.data_source) if case.data_source else DataSource.SUPREME_COURT
        config = get_configs().get(source)
        
        if not config or not config.uses_chunking:
            return case
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.qdrant_url}/collections/{config.name}/points/scroll",
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
                )
                
                if response.status_code == 200:
                    points = response.json().get('result', {}).get('points', [])
                    if points:
                        payload = points[0].get("payload", {})
                        full_text = payload.get("full_text", "")
                        if full_text:
                            case.subject = full_text
                            print(f"   ✓ {case.case_number}")
                
                return case
                
        except Exception as e:
            print(f"   ⚠️ {case.case_number}: {e}")
            return case
    
    # Backward compatibility
    async def multi_query_search(
        self,
        queries: List[str],
        source: DataSource = DataSource.ALL_COURTS,
        results_per_query: int = 10,
        final_limit: int = 5,
        original_query: str = None,
    ) -> List[CaseResult]:
        return await self.search(queries, source, final_limit)
    
    async def orchestrated_search(
        self,
        query: str,
        source: DataSource = DataSource.ALL_COURTS,
        limit: int = 10,
        rerank: bool = True,
    ) -> List[CaseResult]:
        return await self.search([query], source, limit)
    
    async def get_available_sources(self) -> List[Dict[str, Any]]:
        """Get available sources"""
        sources = []
        for source, config in get_configs().items():
            sources.append({
                "id": source.value,
                "name": config.display_name,
                "collection": config.name,
                "status": "available",
            })
        return sources


# Global instance
multi_source_engine = MultiSourceSearchEngine()
