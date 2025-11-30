"""
Multi-Source Search Service - Optimized for Quality
Focus: Get the BEST results, not the fastest

Pipeline:
1. Generate multiple search queries (5-7 variants)
2. Vector search across all collections (get MORE results)
3. Cross-encoder reranking for precision
4. Return top results with whatever text we have
"""
import asyncio
from typing import List, Optional, Dict, Any
from enum import Enum
from dataclasses import dataclass
import httpx
from sentence_transformers import SentenceTransformer, CrossEncoder

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


# =============================================================================
# MODEL MANAGERS
# =============================================================================

class EmbeddingManager:
    """Embedding model manager"""
    
    def __init__(self):
        self._models: Dict[str, SentenceTransformer] = {}
    
    def get_embedding(self, text: str, model_name: str) -> List[float]:
        if model_name not in self._models:
            print(f"🧠 Loading embedding: {model_name}")
            self._models[model_name] = SentenceTransformer(model_name, device="cpu")
        
        model = self._models[model_name]
        normalize = "retromae" in model_name.lower()
        return model.encode(text, normalize_embeddings=normalize).tolist()
    
    def get_embeddings_batch(self, texts: List[str], model_name: str) -> List[List[float]]:
        """Batch embedding for efficiency"""
        if model_name not in self._models:
            print(f"🧠 Loading embedding: {model_name}")
            self._models[model_name] = SentenceTransformer(model_name, device="cpu")
        
        model = self._models[model_name]
        normalize = "retromae" in model_name.lower()
        embeddings = model.encode(texts, normalize_embeddings=normalize, batch_size=32)
        return [e.tolist() for e in embeddings]


class CrossEncoderManager:
    """Cross-encoder for reranking - multilingual model for Czech"""
    
    def __init__(self):
        self._model: Optional[CrossEncoder] = None
        # Multilingual cross-encoder - better for Czech
        self._model_name = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
        # Max tokens for cross-encoder (model limit is 512 tokens)
        # Czech text is ~4-5 chars per token, so 2000 chars ≈ 400-500 tokens
        self._max_text_length = 2000
    
    def _get_model(self) -> CrossEncoder:
        if self._model is None:
            print(f"🎯 Loading multilingual cross-encoder: {self._model_name}")
            self._model = CrossEncoder(self._model_name, device="cpu", max_length=512)
        return self._model
    
    def rerank(self, query: str, cases: List[CaseResult], top_k: int = 10) -> List[CaseResult]:
        """Rerank cases using cross-encoder"""
        if not cases:
            return []
        
        model = self._get_model()
        
        # Create query-document pairs with proper truncation
        pairs = []
        for case in cases:
            text = case.subject or ""
            # Truncate with marker if needed
            if len(text) > self._max_text_length:
                text = text[:self._max_text_length] + " [...]"
            pairs.append([query, text])
        
        # Score all pairs
        print(f"   Scoring {len(pairs)} query-document pairs...")
        scores = model.predict(pairs, show_progress_bar=False)
        
        # Sort by cross-encoder score
        scored_cases = list(zip(cases, scores))
        scored_cases.sort(key=lambda x: x[1], reverse=True)
        
        # Log top scores for debugging
        print(f"   Top 3 scores: {[f'{s:.3f}' for _, s in scored_cases[:3]]}")
        
        # Update relevance scores and return top_k
        result = []
        for case, score in scored_cases[:top_k]:
            case.relevance_score = float(score)
            result.append(case)
        
        return result


embedding_manager = EmbeddingManager()
cross_encoder_manager = CrossEncoderManager()


# =============================================================================
# MAIN SEARCH ENGINE
# =============================================================================

class MultiSourceSearchEngine:
    """
    Optimized search engine focused on QUALITY
    
    Strategy:
    1. More queries = better recall
    2. More results per query = don't miss anything
    3. Cross-encoder reranking = precision
    4. Use whatever text we have (don't fail on chunk 0)
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
        Quality-focused search pipeline:
        1. Search all courts with all queries (get LOTS of candidates)
        2. Deduplicate by case number
        3. Cross-encoder rerank for precision
        4. Return top results
        """
        print(f"\n🔍 Quality Search: {len(queries)} queries")
        
        # Determine courts
        if source == DataSource.ALL_COURTS:
            courts = [
                DataSource.CONSTITUTIONAL_COURT,
                DataSource.SUPREME_COURT,
                DataSource.SUPREME_ADMIN_COURT,
            ]
        else:
            courts = [source]
        
        # Generate embeddings for all queries at once
        config = get_configs()[courts[0]]
        print(f"🧠 Generating {len(queries)} embeddings...")
        vectors = embedding_manager.get_embeddings_batch(queries, config.embedding_model)
        
        # Search all courts with all queries - get MORE results
        results_per_query = 30  # Get more candidates
        tasks = []
        for vector in vectors:
            for court in courts:
                tasks.append(self._search_court(court, vector, results_per_query))
        
        print(f"🔍 Executing {len(tasks)} searches...")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Merge and deduplicate - keep best score per case
        all_cases: Dict[str, CaseResult] = {}
        for result in results:
            if isinstance(result, Exception):
                print(f"⚠️ Search error: {result}")
                continue
            for case in result:
                key = case.case_number
                if key not in all_cases or case.relevance_score > all_cases[key].relevance_score:
                    all_cases[key] = case
        
        print(f"📊 Found {len(all_cases)} unique cases")
        
        if not all_cases:
            return []
        
        # Sort by vector score first
        candidates = sorted(all_cases.values(), key=lambda x: x.relevance_score, reverse=True)
        
        # Take top candidates for cross-encoder reranking
        top_candidates = candidates[:50]  # Rerank top 50
        
        # Cross-encoder reranking for precision
        print(f"🎯 Cross-encoder reranking {len(top_candidates)} candidates...")
        original_query = queries[0]  # Use original query for reranking
        reranked = cross_encoder_manager.rerank(original_query, top_candidates, top_k=limit)
        
        print(f"✅ Returning {len(reranked)} results")
        return reranked
    
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
                        "limit": limit,
                        "with_payload": True,
                    },
                )
                
                if response.status_code != 200:
                    return []
                
                results = response.json().get('result', [])
                cases = []
                
                for r in results:
                    payload = r.get("payload", {})
                    score = r.get("score", 0.0)
                    
                    # Get whatever text we have - don't fail
                    text = (
                        payload.get("full_text") or 
                        payload.get("chunk_text") or 
                        payload.get("subject") or 
                        ""
                    )
                    
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
                
                return list(seen.values())
                
        except Exception as e:
            print(f"⚠️ {config.display_name}: {e}")
            return []
    
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
