"""
Multi-Source Search Service - Optimized for Quality
Focus: Get the BEST results, not the fastest

Pipeline:
1. Extract legal entities (case numbers, statutes, courts)
2. Generate multiple search queries (5-7 variants)
3. Vector search across all collections (get MORE results)
4. Apply entity-based boosting for exact matches
5. Cross-encoder reranking for precision
6. Return top results with full text
"""
import asyncio
from typing import List, Optional, Dict, Any
from enum import Enum
from dataclasses import dataclass
import httpx
from sentence_transformers import SentenceTransformer, CrossEncoder

from app.config import settings
from app.models import CaseResult
from app.services.legal_entity_extractor import (
    extract_entities,
    calculate_boost,
    build_keyword_filters,
    has_searchable_entities,
    ExtractedEntities,
)


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
        1. Extract legal entities (case numbers, statutes, courts)
        2. Search all courts with all queries (get LOTS of candidates)
        3. Apply entity-based boosting for exact matches
        4. Cross-encoder rerank for precision
        5. Fetch full_text from chunk 0 for final results
        6. Return top results with complete text
        """
        print(f"\n🔍 Quality Search: {len(queries)} queries")
        
        # Step 1: Extract legal entities from original query (fail-safe)
        original_query = queries[0] if queries else ""
        entities = extract_entities(original_query)
        if entities.has_entities():
            print(f"📋 {entities}")
        
        # Determine courts - use entity hint if available and source is ALL_COURTS
        if source == DataSource.ALL_COURTS:
            if entities.preferred_source and entities.preferred_source != 'general_courts':
                # User mentioned a specific court, prioritize it but still search others
                preferred = DataSource(entities.preferred_source)
                courts = [preferred]  # Search preferred court first
                other_courts = [
                    DataSource.CONSTITUTIONAL_COURT,
                    DataSource.SUPREME_COURT,
                    DataSource.SUPREME_ADMIN_COURT,
                ]
                courts.extend([c for c in other_courts if c != preferred])
                print(f"   🏛️ Prioritizing {preferred.value} based on query")
            else:
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
        
        # === HYBRID SEARCH: Keyword + Vector ===
        all_cases: Dict[str, CaseResult] = {}
        
        # Step 2a: Keyword search for exact matches (if entities found)
        if has_searchable_entities(entities):
            print(f"🔑 Running keyword search for extracted entities...")
            keyword_tasks = [self._keyword_search_court(court, entities) for court in courts]
            keyword_results = await asyncio.gather(*keyword_tasks, return_exceptions=True)
            
            keyword_count = 0
            for result in keyword_results:
                if isinstance(result, Exception):
                    continue
                for case in result:
                    key = case.case_number
                    if key not in all_cases or case.relevance_score > all_cases[key].relevance_score:
                        all_cases[key] = case
                        keyword_count += 1
            
            if keyword_count > 0:
                print(f"   🔑 Found {keyword_count} keyword matches")
        
        # Step 2b: Vector search for semantic similarity
        results_per_query = 30  # Get more candidates
        tasks = []
        for vector in vectors:
            for court in courts:
                tasks.append(self._search_court(court, vector, results_per_query))
        
        print(f"🔍 Executing {len(tasks)} vector searches...")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Merge vector results with keyword results
        for result in results:
            if isinstance(result, Exception):
                print(f"⚠️ Search error: {result}")
                continue
            for case in result:
                key = case.case_number
                # Only add if not already found by keyword search (keyword has priority)
                if key not in all_cases or case.relevance_score > all_cases[key].relevance_score:
                    all_cases[key] = case
        
        print(f"📊 Found {len(all_cases)} unique cases (hybrid)")
        
        if not all_cases:
            return []
        
        # Step 3: Apply entity-based boosting (fail-safe)
        if entities.has_entities():
            print(f"🎯 Applying entity boosting...")
            for case in all_cases.values():
                boost = calculate_boost(case, entities)
                if boost > 1.0:
                    case.relevance_score *= boost
        
        # Sort by (boosted) vector score
        candidates = sorted(all_cases.values(), key=lambda x: x.relevance_score, reverse=True)
        
        # Take top candidates for cross-encoder reranking
        top_candidates = candidates[:50]  # Rerank top 50
        
        # Step 4: Cross-encoder reranking for precision
        print(f"🎯 Cross-encoder reranking {len(top_candidates)} candidates...")
        reranked = cross_encoder_manager.rerank(original_query, top_candidates, top_k=limit)
        
        # CRITICAL: Fetch full_text from chunk 0 for chunked collections
        print(f"📄 Fetching full text for {len(reranked)} final cases...")
        enriched = await self._fetch_full_texts(reranked)
        
        # Summary logging
        print(f"\n{'─'*50}")
        print(f"✅ SEARCH COMPLETE: {len(enriched)} results")
        for i, case in enumerate(enriched, 1):
            text_len = len(case.subject or "")
            print(f"   [{i}] {case.case_number} ({case.court}) - {text_len:,} chars, score: {case.relevance_score:.3f}")
        print(f"{'─'*50}\n")
        
        return enriched
    
    async def _keyword_search_court(
        self, court: DataSource, entities: ExtractedEntities, limit: int = 20
    ) -> List[CaseResult]:
        """
        Keyword-based search using Qdrant filters.
        Searches for exact matches on case_number and legal_references.
        
        This is fail-safe - returns empty list on any error.
        """
        config = get_configs().get(court)
        if not config:
            return []
        
        cases = []
        
        try:
            filters = build_keyword_filters(entities)
            if not filters:
                return []
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                for filter_info in filters:
                    try:
                        # Use scroll with filter for keyword search
                        response = await client.post(
                            f"{self.qdrant_url}/collections/{config.name}/points/scroll",
                            headers=self.headers,
                            json={
                                "filter": {
                                    "should": [filter_info["condition"]]
                                },
                                "limit": limit,
                                "with_payload": True,
                            },
                        )
                        
                        if response.status_code != 200:
                            continue
                        
                        result = response.json().get('result', {})
                        points = result.get('points', [])
                        
                        for point in points:
                            payload = point.get("payload", {})
                            
                            # Get text
                            text = (
                                payload.get("full_text") or
                                payload.get("chunk_text") or
                                payload.get("subject") or
                                ""
                            )
                            
                            # High score for keyword matches
                            score = 0.95 if filter_info["type"] == "case_number" else 0.85
                            
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
                    
                    except Exception as e:
                        print(f"   ⚠️ Keyword filter error: {e}")
                        continue
            
            # Deduplicate - keep best score per case
            seen: Dict[str, CaseResult] = {}
            for case in cases:
                if case.case_number not in seen or case.relevance_score > seen[case.case_number].relevance_score:
                    seen[case.case_number] = case
            
            return list(seen.values())
            
        except Exception as e:
            print(f"⚠️ Keyword search error (non-fatal): {e}")
            return []
    
    async def _search_court(
        self, court: DataSource, vector: List[float], limit: int
    ) -> List[CaseResult]:
        """Search a single court using vector similarity"""
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
    
    async def _fetch_full_texts(self, cases: List[CaseResult]) -> List[CaseResult]:
        """
        Fetch full_text from chunk 0 for chunked collections.
        
        Data structure:
        - Chunked collections (3 courts): full_text is ONLY in chunk 0
        - Legacy collection (general_courts): full_text is directly in payload
        """
        if not cases:
            return []
        
        # Group cases by collection type
        chunked_cases = []
        legacy_cases = []
        
        for case in cases:
            source = DataSource(case.data_source) if case.data_source else DataSource.SUPREME_COURT
            config = get_configs().get(source)
            
            if config and config.uses_chunking:
                chunked_cases.append((case, config))
            else:
                # Legacy collection already has full_text in subject
                legacy_cases.append(case)
        
        # Legacy cases are already complete
        enriched = list(legacy_cases)
        
        # Fetch full_text for chunked cases from chunk 0
        if chunked_cases:
            # Debug: show which collections we're fetching from
            collections_used = set(config.name for _, config in chunked_cases)
            print(f"   📄 Fetching full_text from chunk 0 for {len(chunked_cases)} cases from {collections_used}...")
            tasks = [self._fetch_chunk0_full_text(case, config) for case, config in chunked_cases]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    # On exception, still include the case with its original chunk_text
                    original_case, _ = chunked_cases[i]
                    print(f"   ⚠️ {original_case.case_number}: Fetch error, using original chunk ({len(original_case.subject or ''):,} chars)")
                    enriched.append(original_case)
                elif result:
                    enriched.append(result)
        
        # Maintain original order by relevance score
        case_order = {case.case_number: i for i, case in enumerate(cases)}
        enriched.sort(key=lambda x: case_order.get(x.case_number, 999))
        
        return enriched
    
    async def _fetch_chunk0_full_text(self, case: CaseResult, config: CollectionConfig) -> CaseResult:
        """
        Fetch full_text from chunk 0 for a single case.
        ALWAYS returns the case - with full_text if found, or original chunk_text as fallback.
        
        Strategy:
        1. Search for any chunk of this case that has full_text
        2. If not found, keep original text
        """
        original_text_len = len(case.subject or "")
        case_number = case.case_number.strip()
        
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                # Strategy: Find any chunk for this case and look for full_text
                # Use "text" match for more flexible matching (handles tokenization)
                request_body = {
                    "filter": {
                        "should": [
                            # Try exact match first
                            {"key": "case_number", "match": {"value": case_number}},
                            # Also try text match for flexibility
                            {"key": "case_number", "match": {"text": case_number}},
                        ]
                    },
                    "limit": 20,  # Get multiple chunks
                    "with_payload": True,
                }
                
                url = f"{self.qdrant_url}/collections/{config.name}/points/scroll"
                
                response = await client.post(
                    url,
                    headers=self.headers,
                    json=request_body,
                )
                
                if response.status_code != 200:
                    error_text = response.text[:200] if response.text else "No error text"
                    print(f"   ❌ {case_number}: HTTP {response.status_code} - {error_text}")
                    return case
                
                result = response.json().get('result', {})
                points = result.get('points', [])
                
                if not points:
                    # Debug: Try to understand why no points found
                    print(f"   ⚠️ {case_number}: No chunks found in {config.name}, trying text search...")
                    
                    # Try a text-based search as fallback
                    text_search_body = {
                        "filter": {
                            "must": [
                                {"key": "case_number", "match": {"text": case_number}},
                            ]
                        },
                        "limit": 5,
                        "with_payload": True,
                    }
                    
                    text_response = await client.post(url, headers=self.headers, json=text_search_body)
                    if text_response.status_code == 200:
                        text_result = text_response.json().get('result', {})
                        points = text_result.get('points', [])
                        if points:
                            print(f"   🔍 {case_number}: Found {len(points)} via text search")
                    
                    if not points:
                        return case
                
                # Look through all chunks for full_text
                best_full_text = ""
                chunk_0_text = ""
                any_chunk_text = ""
                debug_info = []
                
                for point in points:
                    payload = point.get("payload", {})
                    chunk_idx = payload.get("chunk_index", -1)
                    full_text = payload.get("full_text", "")
                    chunk_text = payload.get("chunk_text", "")
                    has_full = payload.get("has_full_text", False)
                    
                    debug_info.append(f"chunk_{chunk_idx}:ft={len(full_text)},ct={len(chunk_text)},hf={has_full}")
                    
                    # Prioritize full_text
                    if full_text and len(full_text) > len(best_full_text):
                        best_full_text = full_text
                    
                    # Track chunk 0 text
                    if chunk_idx == 0 and chunk_text:
                        chunk_0_text = chunk_text
                    
                    # Track any chunk text as fallback
                    if chunk_text and len(chunk_text) > len(any_chunk_text):
                        any_chunk_text = chunk_text
                
                # Use best available text
                if best_full_text and len(best_full_text) > original_text_len:
                    case.subject = best_full_text
                    print(f"   ✅ {case_number}: Found full_text {len(best_full_text):,} chars (was {original_text_len:,})")
                elif chunk_0_text and len(chunk_0_text) > original_text_len:
                    case.subject = chunk_0_text
                    print(f"   📝 {case_number}: Using chunk_0 {len(chunk_0_text):,} chars (was {original_text_len:,})")
                elif any_chunk_text and len(any_chunk_text) > original_text_len:
                    case.subject = any_chunk_text
                    print(f"   📝 {case_number}: Using best chunk {len(any_chunk_text):,} chars (was {original_text_len:,})")
                else:
                    # Debug output
                    print(f"   ⚠️ {case_number}: {len(points)} chunks, no better text. Debug: {debug_info[:3]}")
                
                return case
                
        except httpx.TimeoutException:
            print(f"   ❌ {case_number}: Timeout fetching from Qdrant (60s)")
            return case
        except httpx.ConnectError as e:
            print(f"   ❌ {case_number}: Connection error: {str(e)[:100]}")
            return case
        except Exception as e:
            import traceback
            error_msg = str(e) if str(e) else type(e).__name__
            print(f"   ❌ {case_number}: {type(e).__name__}: {error_msg}")
            traceback.print_exc()
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
