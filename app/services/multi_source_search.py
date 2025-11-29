"""
Multi-Source Search Service with Advanced Orchestration
Supports multiple Qdrant collections with reranking and quality optimization
Default: All 3 court collections (Seznam/retromae-small-cs)

Enhanced with:
- Legal Entity Extraction (case numbers, statutes, courts)
- Query Expansion with Czech legal synonyms
- Document-Level Aggregation (multi-chunk scoring)
- Two-Stage Retrieval (broad recall → precise reranking)
"""
import asyncio
import math
import re
from typing import List, Optional, Dict, Any, Set, Tuple
from enum import Enum
from dataclasses import dataclass, field
import httpx
from sentence_transformers import SentenceTransformer, CrossEncoder

from app.config import settings
from app.models import CaseResult


# =============================================================================
# LEGAL ENTITY EXTRACTION
# =============================================================================

@dataclass
class LegalEntities:
    """Extracted legal entities from a query"""
    statutes: List[str] = field(default_factory=list)      # § 123 zákona č. 89/2012 Sb.
    case_numbers: List[str] = field(default_factory=list)  # 21 Cdo 1234/2020
    courts: List[str] = field(default_factory=list)        # Ústavní soud, Nejvyšší soud
    legal_concepts: List[str] = field(default_factory=list) # náhrada škody, bezdůvodné obohacení


def extract_legal_entities(query: str) -> LegalEntities:
    """
    Extract legal entities from query for filtering and boosting
    
    Extracts:
    - Statute references: § 123, § 123 odst. 1, zákona č. 89/2012 Sb.
    - Case numbers: 21 Cdo 1234/2020, I. ÚS 123/20
    - Court names: Ústavní soud, Nejvyšší soud, NSS
    - Legal concepts: náhrada škody, bezdůvodné obohacení
    """
    entities = LegalEntities()
    query_lower = query.lower()
    
    # Extract statute references (§ with optional paragraph and law number)
    statute_patterns = [
        r'§\s*\d+[a-z]?(?:\s*odst\.\s*\d+)?(?:\s*(?:písm\.|písmeno)\s*[a-z]\))?',
        r'zákon[a-z]*\s*č\.\s*\d+/\d+\s*Sb\.',
        r'vyhlášk[a-z]*\s*č\.\s*\d+/\d+\s*Sb\.',
        r'nařízení\s*(?:vlády\s*)?č\.\s*\d+/\d+\s*Sb\.',
    ]
    for pattern in statute_patterns:
        matches = re.findall(pattern, query, re.IGNORECASE)
        entities.statutes.extend(matches)
    
    # Extract case numbers (various Czech court formats)
    case_patterns = [
        r'\d+\s*[A-Za-z]+\s*\d+/\d{2,4}',           # 21 Cdo 1234/2020
        r'[IVX]+\.\s*ÚS\s*\d+/\d{2,4}',             # I. ÚS 123/20
        r'Pl\.\s*ÚS\s*\d+/\d{2,4}',                 # Pl. ÚS 1/20
        r'\d+\s*(?:Ads?|Afs?|As|Azs|Ars)\s*\d+/\d{2,4}',  # NSS formats
        r'sp\.\s*zn\.\s*[\w\s\./]+',                # sp. zn. reference
    ]
    for pattern in case_patterns:
        matches = re.findall(pattern, query, re.IGNORECASE)
        entities.case_numbers.extend(matches)
    
    # Extract court names
    court_keywords = {
        'ústavní soud': 'Ústavní soud',
        'ústavního soudu': 'Ústavní soud',
        'nejvyšší soud': 'Nejvyšší soud',
        'nejvyššího soudu': 'Nejvyšší soud',
        'nejvyšší správní': 'Nejvyšší správní soud',
        'nss': 'Nejvyšší správní soud',
        'krajský soud': 'Krajský soud',
        'okresní soud': 'Okresní soud',
        'vrchní soud': 'Vrchní soud',
    }
    for keyword, court_name in court_keywords.items():
        if keyword in query_lower:
            entities.courts.append(court_name)
    
    # Extract common legal concepts
    legal_concepts = [
        'náhrada škody', 'náhrada újmy', 'odškodnění', 'kompenzace',
        'bezdůvodné obohacení', 'neplatnost smlouvy', 'odstoupení od smlouvy',
        'výpověď', 'okamžité zrušení', 'pracovní poměr', 'pracovní smlouva',
        'nájem', 'nájemní smlouva', 'výpověď z nájmu', 'náhrada mzdy',
        'úroky z prodlení', 'smluvní pokuta', 'promlčení', 'prekluze',
        'vlastnické právo', 'věcné břemeno', 'zástavní právo', 'exekuce',
        'insolvence', 'konkurs', 'oddlužení', 'pohledávka', 'dluh',
        'trestný čin', 'přestupek', 'správní delikt', 'přečin', 'zločin',
        'důkaz', 'svědek', 'znalecký posudek', 'listina', 'výslech',
        'odvolání', 'dovolání', 'kasační stížnost', 'ústavní stížnost',
        'předběžné opatření', 'zajištění', 'vazba', 'trest odnětí svobody',
    ]
    for concept in legal_concepts:
        if concept in query_lower:
            entities.legal_concepts.append(concept)
    
    # Deduplicate
    entities.statutes = list(set(entities.statutes))
    entities.case_numbers = list(set(entities.case_numbers))
    entities.courts = list(set(entities.courts))
    entities.legal_concepts = list(set(entities.legal_concepts))
    
    return entities


# =============================================================================
# QUERY EXPANSION WITH LEGAL SYNONYMS
# =============================================================================

# Czech legal synonyms for query expansion
LEGAL_SYNONYMS: Dict[str, List[str]] = {
    # Damage and compensation
    'náhrada škody': ['odškodnění', 'kompenzace', 'náhrada újmy', 'reparace'],
    'škoda': ['újma', 'ztráta', 'poškození'],
    'nemajetková újma': ['morální újma', 'nemajetková škoda', 'imateriální újma'],
    
    # Contracts
    'smlouva': ['kontrakt', 'dohoda', 'ujednání', 'smluvní vztah'],
    'neplatnost': ['absolutní neplatnost', 'relativní neplatnost', 'nicotnost'],
    'odstoupení': ['odstoupení od smlouvy', 'zrušení smlouvy', 'ukončení smlouvy'],
    'výpověď': ['ukončení', 'rozvázání', 'skončení'],
    
    # Employment
    'pracovní poměr': ['zaměstnání', 'pracovněprávní vztah', 'pracovní vztah'],
    'zaměstnanec': ['pracovník', 'zaměstnaný'],
    'zaměstnavatel': ['firma', 'podnik', 'organizace'],
    'mzda': ['plat', 'odměna za práci', 'výdělek'],
    'výpověď z pracovního poměru': ['rozvázání pracovního poměru', 'skončení pracovního poměru'],
    
    # Property
    'vlastnictví': ['vlastnické právo', 'majetek', 'vlastní'],
    'nemovitost': ['pozemek', 'stavba', 'budova', 'byt', 'dům'],
    'nájem': ['pronájem', 'nájemní vztah', 'pacht'],
    'nájemce': ['nájemník', 'pachtýř'],
    
    # Obligations
    'pohledávka': ['nárok', 'právo na plnění', 'dlužná částka'],
    'dluh': ['závazek', 'povinnost plnit', 'dlužná částka'],
    'úrok': ['úrok z prodlení', 'zákonný úrok', 'smluvní úrok'],
    'smluvní pokuta': ['penále', 'sankce', 'pokuta'],
    
    # Procedure
    'žaloba': ['návrh', 'podání', 'žalobní návrh'],
    'žalobce': ['navrhovatel', 'stěžovatel'],
    'žalovaný': ['odpůrce', 'dlužník'],
    'odvolání': ['opravný prostředek', 'řádný opravný prostředek'],
    'dovolání': ['mimořádný opravný prostředek'],
    
    # Criminal
    'trestný čin': ['delikt', 'protiprávní jednání', 'čin'],
    'pachatel': ['obviněný', 'obžalovaný', 'odsouzený'],
    'trest': ['sankce', 'opatření'],
    
    # Insolvency
    'insolvence': ['úpadek', 'platební neschopnost', 'předlužení'],
    'konkurs': ['konkurzní řízení', 'likvidace'],
    'oddlužení': ['osobní bankrot', 'sanace'],
}


def expand_query_with_synonyms(query: str, max_expansions: int = 3) -> List[str]:
    """
    Expand query with Czech legal synonyms
    
    Returns list of expanded queries (original + synonym variants)
    """
    expanded = [query]
    query_lower = query.lower()
    
    expansions_added = 0
    for term, synonyms in LEGAL_SYNONYMS.items():
        if term in query_lower and expansions_added < max_expansions:
            # Add queries with each synonym
            for syn in synonyms[:2]:  # Max 2 synonyms per term
                expanded_query = query_lower.replace(term, syn)
                if expanded_query != query_lower:
                    expanded.append(expanded_query)
                    expansions_added += 1
                    if expansions_added >= max_expansions:
                        break
    
    return expanded


# =============================================================================
# IN-MEMORY BM25 FOR HYBRID SEARCH
# =============================================================================

try:
    from rank_bm25 import BM25Okapi
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False
    print("⚠️ rank_bm25 not installed. BM25 hybrid search disabled.")


def tokenize_czech(text: str) -> List[str]:
    """
    Simple Czech tokenizer for BM25
    
    - Lowercases text
    - Removes punctuation
    - Splits on whitespace
    - Removes short tokens (< 2 chars)
    - Handles Czech diacritics
    """
    if not text:
        return []
    
    # Lowercase and remove punctuation (keep Czech diacritics)
    text = text.lower()
    text = re.sub(r'[^\w\sáčďéěíňóřšťúůýž]', ' ', text)
    
    # Split and filter short tokens
    tokens = [t for t in text.split() if len(t) >= 2]
    
    return tokens


class InMemoryBM25:
    """
    In-memory BM25 index for hybrid search
    
    Builds BM25 index from vector search results on-the-fly.
    No pre-indexing required - works with any Qdrant results.
    
    Usage:
        bm25 = InMemoryBM25()
        bm25.index_cases(cases)  # Index vector search results
        bm25_scores = bm25.score(query)  # Get BM25 scores
    """
    
    def __init__(self):
        self._bm25: Optional[Any] = None
        self._case_numbers: List[str] = []
        self._indexed = False
    
    def index_cases(self, cases: List[CaseResult]) -> bool:
        """
        Build BM25 index from case results
        
        Indexes the subject/text field of each case.
        Returns True if indexing successful.
        """
        if not BM25_AVAILABLE:
            return False
        
        if not cases:
            return False
        
        # Tokenize all case texts
        corpus = []
        self._case_numbers = []
        
        for case in cases:
            text = case.subject or ""
            # Also include case number for exact matching
            text = f"{case.case_number} {text}"
            tokens = tokenize_czech(text)
            corpus.append(tokens)
            self._case_numbers.append(case.case_number)
        
        if not corpus:
            return False
        
        # Build BM25 index
        self._bm25 = BM25Okapi(corpus)
        self._indexed = True
        
        return True
    
    def score(self, query: str) -> Dict[str, float]:
        """
        Get BM25 scores for all indexed cases
        
        Returns dict mapping case_number -> BM25 score
        """
        if not self._indexed or not self._bm25:
            return {}
        
        query_tokens = tokenize_czech(query)
        if not query_tokens:
            return {}
        
        scores = self._bm25.get_scores(query_tokens)
        
        # Map scores to case numbers
        result = {}
        for i, case_num in enumerate(self._case_numbers):
            if i < len(scores):
                result[case_num] = float(scores[i])
        
        return result
    
    def get_top_k(self, query: str, k: int = 10) -> List[Tuple[str, float]]:
        """
        Get top-k cases by BM25 score
        
        Returns list of (case_number, score) tuples
        """
        scores = self.score(query)
        if not scores:
            return []
        
        # Sort by score descending
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_scores[:k]


def rrf_fusion(
    vector_results: List[CaseResult],
    bm25_scores: Dict[str, float],
    vector_weight: float = 0.5,
    bm25_weight: float = 0.5,
    k: int = 60,
) -> List[CaseResult]:
    """
    Reciprocal Rank Fusion (RRF) to combine vector and BM25 results
    
    Formula: RRF(d) = Σ (weight / (k + rank(d)))
    
    Args:
        vector_results: Cases from vector search (already ranked)
        bm25_scores: Dict of case_number -> BM25 score
        vector_weight: Weight for vector search (default 0.5)
        bm25_weight: Weight for BM25 search (default 0.5)
        k: RRF constant (default 60, standard value)
    
    Returns:
        Re-ranked list of CaseResult with combined scores
    """
    if not vector_results:
        return []
    
    # Build case lookup
    case_lookup: Dict[str, CaseResult] = {c.case_number: c for c in vector_results}
    
    # Calculate RRF scores
    rrf_scores: Dict[str, float] = {}
    
    # Vector search contribution (by rank)
    for rank, case in enumerate(vector_results, 1):
        key = case.case_number
        rrf_scores[key] = vector_weight / (k + rank)
    
    # BM25 contribution (by rank)
    if bm25_scores:
        # Sort BM25 scores to get ranks
        sorted_bm25 = sorted(bm25_scores.items(), key=lambda x: x[1], reverse=True)
        for rank, (case_num, _) in enumerate(sorted_bm25, 1):
            if case_num in rrf_scores:
                rrf_scores[case_num] += bm25_weight / (k + rank)
    
    # Sort by RRF score
    sorted_cases = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    
    # Build result list
    results = []
    for case_num, rrf_score in sorted_cases:
        if case_num in case_lookup:
            case = case_lookup[case_num]
            # Store original vector score, update with RRF for ranking
            case.relevance_score = rrf_score
            results.append(case)
    
    return results


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
            court_field="court",  # Not in payload, use display_name (ignore 'source' field)
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


# =============================================================================
# DOCUMENT-LEVEL AGGREGATION
# =============================================================================

def aggregate_chunk_scores(cases: List[CaseResult], top_k: int = 20) -> List[CaseResult]:
    """
    Aggregate chunk scores to document level
    
    Cases with multiple relevant chunks get boosted score.
    Formula: final_score = max_score * log(chunk_count + 1)
    
    This rewards documents that have multiple relevant passages,
    indicating broader relevance to the query.
    """
    doc_scores: Dict[str, Dict[str, Any]] = {}
    
    for case in cases:
        key = case.case_number
        if key not in doc_scores:
            doc_scores[key] = {
                'case': case,
                'max_score': case.relevance_score,
                'chunk_count': 1,
                'total_score': case.relevance_score,
                'courts': {case.court} if case.court else set(),
            }
        else:
            # Update with better chunk if found
            if case.relevance_score > doc_scores[key]['max_score']:
                doc_scores[key]['case'] = case  # Keep best chunk's content
                doc_scores[key]['max_score'] = case.relevance_score
            doc_scores[key]['chunk_count'] += 1
            doc_scores[key]['total_score'] += case.relevance_score
            if case.court:
                doc_scores[key]['courts'].add(case.court)
    
    # Calculate final scores with chunk count boost
    results = []
    for key, data in doc_scores.items():
        case = data['case']
        # Boost score based on number of relevant chunks (logarithmic)
        chunk_boost = math.log(data['chunk_count'] + 1)
        case.relevance_score = data['max_score'] * chunk_boost
        results.append(case)
    
    # Sort by final score
    results.sort(key=lambda x: x.relevance_score, reverse=True)
    
    return results[:top_k]


def boost_by_entity_match(
    cases: List[CaseResult], 
    entities: LegalEntities,
    boost_factor: float = 1.3
) -> List[CaseResult]:
    """
    Boost cases that match extracted legal entities
    
    Cases matching:
    - Exact case number: 2x boost
    - Court name: 1.3x boost
    - Statute reference: 1.2x boost
    """
    if not entities.case_numbers and not entities.courts and not entities.statutes:
        return cases
    
    for case in cases:
        boost = 1.0
        case_text = f"{case.case_number} {case.subject or ''} {case.court or ''}".lower()
        
        # Exact case number match - highest boost
        for case_num in entities.case_numbers:
            if case_num.lower() in case.case_number.lower():
                boost *= 2.0
                break
        
        # Court match
        for court in entities.courts:
            if court.lower() in (case.court or '').lower():
                boost *= 1.3
                break
        
        # Statute reference in text
        for statute in entities.statutes:
            if statute.lower() in case_text:
                boost *= 1.2
                break
        
        case.relevance_score *= boost
    
    # Re-sort after boosting
    cases.sort(key=lambda x: x.relevance_score, reverse=True)
    return cases


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
        # Reusable HTTP client with connection pooling
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create a reusable HTTP client with generous timeouts"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    timeout=self.initial_timeout,  # Total timeout
                    connect=30.0,  # Connection timeout
                    read=self.initial_timeout,  # Read timeout
                    write=30.0,  # Write timeout
                ),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    async def orchestrated_search(
        self,
        query: str,
        source: DataSource = DataSource.ALL_COURTS,
        limit: int = 10,
        rerank: bool = True,
        use_hybrid: bool = True,
    ) -> List[CaseResult]:
        """
        Main orchestrated search with quality optimization
        
        Enhanced Pipeline:
        1. Extract legal entities (case numbers, statutes, courts)
        2. Expand query with legal synonyms
        3. Search specified source(s) - default ALL_COURTS (3 collections)
        4. Apply BM25 hybrid search (keyword + vector fusion)
        5. Aggregate chunk scores to document level
        6. Boost by entity matches
        7. Filter by minimum relevance
        8. Rerank using GPT-5-nano for quality
        9. Return top results
        """
        print(f"\n{'='*70}")
        print(f"🎯 ORCHESTRATED SEARCH (Hybrid Pipeline)")
        print(f"   Source: {source.value}")
        print(f"   Query: {query[:80]}...")
        print(f"   Hybrid BM25: {'enabled' if use_hybrid and BM25_AVAILABLE else 'disabled'}")
        print(f"{'='*70}")
        
        # Step 1: Extract legal entities for boosting
        entities = extract_legal_entities(query)
        if entities.case_numbers or entities.statutes or entities.courts or entities.legal_concepts:
            print(f"📋 Extracted entities:")
            if entities.case_numbers:
                print(f"   Case numbers: {entities.case_numbers}")
            if entities.statutes:
                print(f"   Statutes: {entities.statutes}")
            if entities.courts:
                print(f"   Courts: {entities.courts}")
            if entities.legal_concepts:
                print(f"   Legal concepts: {entities.legal_concepts[:5]}...")
        
        # Step 2: Expand query with synonyms
        expanded_queries = expand_query_with_synonyms(query, max_expansions=2)
        if len(expanded_queries) > 1:
            print(f"🔄 Query expansion: {len(expanded_queries)} variants")
            for eq in expanded_queries[1:]:
                print(f"   + {eq[:60]}...")
        
        # Step 3: Get raw results (search with all query variants)
        all_raw_results = []
        
        # Primary search with original query (get more for BM25 reranking)
        search_limit = limit * 4 if use_hybrid and BM25_AVAILABLE else limit * 3
        if source == DataSource.ALL_COURTS:
            raw_results = await self._search_all_courts(query, search_limit)
        else:
            raw_results = await self._search_single_source(query, source, search_limit)
        all_raw_results.extend(raw_results)
        
        # Additional searches with expanded queries (if any)
        if len(expanded_queries) > 1:
            for exp_query in expanded_queries[1:2]:  # Max 1 expansion search
                if source == DataSource.ALL_COURTS:
                    exp_results = await self._search_all_courts(exp_query, limit)
                else:
                    exp_results = await self._search_single_source(exp_query, source, limit)
                all_raw_results.extend(exp_results)
        
        if not all_raw_results:
            print("⚠️ No results found")
            return []
        
        print(f"📊 Raw vector results: {len(all_raw_results)}")
        
        # Step 4: Apply BM25 hybrid search
        if use_hybrid and BM25_AVAILABLE and len(all_raw_results) > 5:
            bm25 = InMemoryBM25()
            if bm25.index_cases(all_raw_results):
                bm25_scores = bm25.score(query)
                
                # Also score with expanded queries for better recall
                for exp_query in expanded_queries[1:2]:
                    exp_scores = bm25.score(exp_query)
                    for case_num, score in exp_scores.items():
                        if case_num in bm25_scores:
                            bm25_scores[case_num] = max(bm25_scores[case_num], score)
                        else:
                            bm25_scores[case_num] = score
                
                # RRF fusion: combine vector (semantic) + BM25 (keyword)
                # Weight vector slightly higher for legal semantic understanding
                hybrid_results = rrf_fusion(
                    all_raw_results, 
                    bm25_scores,
                    vector_weight=settings.HYBRID_VECTOR_WEIGHT,
                    bm25_weight=settings.HYBRID_BM25_WEIGHT,
                )
                print(f"📊 After BM25 hybrid fusion: {len(hybrid_results)}")
                all_raw_results = hybrid_results
            else:
                print("⚠️ BM25 indexing failed, using vector-only results")
        
        # Step 5: Aggregate chunk scores to document level
        aggregated = aggregate_chunk_scores(all_raw_results, top_k=limit * 4)
        print(f"📊 After aggregation: {len(aggregated)}")
        
        # Step 6: Boost by entity matches
        boosted = boost_by_entity_match(aggregated, entities)
        
        # Step 7: Filter by minimum relevance
        filtered = [r for r in boosted if r.relevance_score >= settings.MIN_RELEVANCE_SCORE]
        print(f"📊 After filter (>{settings.MIN_RELEVANCE_SCORE}): {len(filtered)}")
        
        if not filtered:
            filtered = boosted[:limit]  # Fallback to top results
        
        # Step 8: Rerank with GPT-5-nano (fast and accurate)
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
        """Execute search with pre-computed vector using connection pool"""
        configs = get_configs()
        config = configs.get(source)
        if not config:
            return []
        
        client = await self._get_client()
        
        for attempt in range(self.max_retries):
            try:
                # Use longer timeout for each retry attempt
                timeout = self.initial_timeout + (attempt * 60)  # Add 60s per retry
                
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
                    print(f"❌ Client error {response.status_code}: {response.text[:100]}")
                    return []
                
                # Server error - retry
                print(f"⚠️ Server error {response.status_code} for {config.display_name}, retrying...")
                    
            except httpx.TimeoutException:
                print(f"⏱️ Timeout {config.display_name} ({timeout}s) attempt {attempt + 1}/{self.max_retries}")
            except httpx.ConnectError as e:
                print(f"🔌 Connection error {config.display_name}: {e}")
            except Exception as e:
                print(f"❌ Error {config.display_name} attempt {attempt + 1}: {type(e).__name__}: {e}")
            
            if attempt < self.max_retries - 1:
                await asyncio.sleep(2)  # Wait before retry
        
        print(f"⚠️ All retries failed for {config.display_name}")
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
        original_query: str = None,
        use_hybrid: bool = True,
    ) -> List[CaseResult]:
        """
        Multi-query search with RRF (Reciprocal Rank Fusion)
        Default: searches all 3 courts
        
        Enhanced with:
        - Legal entity extraction and boosting
        - Query expansion with synonyms
        - BM25 hybrid search (keyword + vector)
        - Document-level aggregation
        - RRF fusion across queries
        
        Optimized: Pre-compute all embeddings, then search in parallel
        """
        print(f"\n🔍 Multi-query search: {len(queries)} queries → {source.value}")
        print(f"   Hybrid BM25: {'enabled' if use_hybrid and BM25_AVAILABLE else 'disabled'}")
        
        # Extract entities from original query for boosting
        base_query = original_query or queries[0]
        entities = extract_legal_entities(base_query)
        if entities.case_numbers or entities.statutes or entities.courts:
            print(f"📋 Entities for boosting: cases={entities.case_numbers}, statutes={len(entities.statutes)}, courts={entities.courts}")
        
        # Expand queries with synonyms (add 1-2 synonym variants)
        expanded_queries = list(queries)  # Start with original queries
        for q in queries[:2]:  # Expand first 2 queries
            synonyms = expand_query_with_synonyms(q, max_expansions=1)
            for syn in synonyms[1:]:  # Skip original
                if syn not in expanded_queries:
                    expanded_queries.append(syn)
        
        if len(expanded_queries) > len(queries):
            print(f"🔄 Expanded to {len(expanded_queries)} queries (+{len(expanded_queries) - len(queries)} synonyms)")
        
        # Pre-compute all embeddings at once (faster than doing it per-query)
        config = get_configs()[DataSource.CONSTITUTIONAL_COURT]
        print(f"🧠 Computing embeddings for {len(expanded_queries)} queries...")
        vectors = [
            embedding_manager.get_embedding(q, config.embedding_model)
            for q in expanded_queries
        ]
        print(f"✅ Embeddings computed")
        
        # Determine which courts to search
        if source == DataSource.ALL_COURTS:
            court_sources = [
                DataSource.CONSTITUTIONAL_COURT,
                DataSource.SUPREME_COURT,
                DataSource.SUPREME_ADMIN_COURT,
            ]
        else:
            court_sources = [source]
        
        # Execute ALL searches in parallel (queries × courts)
        # Use semaphore to limit concurrent requests to avoid overwhelming Qdrant
        total_searches = len(expanded_queries) * len(court_sources)
        print(f"🔍 Searching {len(expanded_queries)} queries × {len(court_sources)} courts = {total_searches} searches...")
        
        semaphore = asyncio.Semaphore(3)  # Max 3 concurrent searches to reduce load
        
        async def limited_search(court: DataSource, vector: List[float]) -> List[CaseResult]:
            async with semaphore:
                return await self._execute_search_with_vector(court, vector, results_per_query)
        
        tasks = []
        for vector in vectors:
            for court in court_sources:
                tasks.append(limited_search(court, vector))
        
        all_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successes and failures
        successes = sum(1 for r in all_results if not isinstance(r, Exception) and r)
        failures = sum(1 for r in all_results if isinstance(r, Exception))
        empty = sum(1 for r in all_results if not isinstance(r, Exception) and not r)
        print(f"📊 Search results: {successes} success, {failures} failed, {empty} empty")
        
        # Group results by query
        results_per_query_list = []
        idx = 0
        for q_idx, _ in enumerate(expanded_queries):
            query_results = []
            for court in court_sources:
                result = all_results[idx]
                if isinstance(result, Exception):
                    print(f"   ⚠️ Query {q_idx+1}, {court.value}: {result}")
                elif result:
                    # Tag with data source
                    for r in result:
                        r.data_source = court.value
                    query_results.extend(result)
                idx += 1
            # Sort by score and deduplicate
            query_results.sort(key=lambda x: x.relevance_score, reverse=True)
            query_results = self._deduplicate_results(query_results)
            results_per_query_list.append(query_results)
        
        all_results = results_per_query_list
        
        # Flatten all results for BM25 indexing
        all_cases_flat = []
        for query_results in all_results:
            all_cases_flat.extend(query_results)
        
        # Apply BM25 hybrid scoring if enabled
        bm25_scores: Dict[str, float] = {}
        if use_hybrid and BM25_AVAILABLE and len(all_cases_flat) > 5:
            bm25 = InMemoryBM25()
            if bm25.index_cases(all_cases_flat):
                # Score with original query
                bm25_scores = bm25.score(base_query)
                # Also score with generated queries
                for q in queries[:3]:
                    q_scores = bm25.score(q)
                    for case_num, score in q_scores.items():
                        if case_num in bm25_scores:
                            bm25_scores[case_num] = max(bm25_scores[case_num], score)
                        else:
                            bm25_scores[case_num] = score
                print(f"📊 BM25 scored {len(bm25_scores)} cases")
        
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
                        'chunk_count': 1,
                    }
                else:
                    case_scores[key]['rrf_score'] += rrf_score
                    case_scores[key]['max_score'] = max(
                        case_scores[key]['max_score'],
                        case.relevance_score
                    )
                    case_scores[key]['query_hits'] += 1
                    case_scores[key]['chunk_count'] += 1
        
        # Add BM25 contribution to RRF scores
        if bm25_scores:
            # Sort BM25 scores to get ranks
            sorted_bm25 = sorted(bm25_scores.items(), key=lambda x: x[1], reverse=True)
            for rank, (case_num, _) in enumerate(sorted_bm25, 1):
                if case_num in case_scores:
                    # Add BM25 RRF contribution (weighted)
                    case_scores[case_num]['rrf_score'] += settings.HYBRID_BM25_WEIGHT / (60 + rank)
        
        # Apply document-level aggregation boost
        for key, data in case_scores.items():
            # Boost by chunk count (documents with multiple relevant chunks)
            chunk_boost = math.log(data['chunk_count'] + 1)
            data['rrf_score'] *= chunk_boost
        
        # Sort by RRF score (cases appearing in multiple queries rank higher)
        merged = []
        for data in case_scores.values():
            case = data['case']
            case.relevance_score = data['max_score']
            merged.append((data['rrf_score'], data['query_hits'], case))
        
        # Sort by RRF, then by query hits
        merged.sort(key=lambda x: (x[0], x[1]), reverse=True)
        
        # Extract cases and apply entity boosting
        final_cases = [case for _, _, case in merged[:final_limit * 2]]
        boosted = boost_by_entity_match(final_cases, entities)
        
        print(f"✅ RRF merged: {len(merged)} unique cases → {len(boosted[:final_limit])} final")
        return boosted[:final_limit]
    
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
