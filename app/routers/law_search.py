"""
Law Search Router - e-Sbírka API Integration
Full-featured search for Czech legal acts using official e-Sbírka REST API
"""
from fastapi import APIRouter, Query, HTTPException, Path
from fastapi.responses import JSONResponse
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
import logging
import traceback
from urllib.parse import unquote

from app.services.esbirka_client import esbirka_client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/law", tags=["law-search"])


# === Response Models ===

class LawSearchResult(BaseModel):
    iri: str
    citace: str
    nazev: str
    typ: Optional[str] = None
    verze_od: Optional[str] = None
    verze_do: Optional[str] = None
    popis: Optional[str] = None
    status: Optional[str] = None
    staleUrl: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    count: int
    results: List[LawSearchResult]
    timestamp: str


class LawFragment(BaseModel):
    id: Optional[int] = None
    full_citation: str
    short_citation: str
    text: str
    is_effective: bool = True


class LawDetailResponse(BaseModel):
    iri: str
    citace: str
    nazev: str
    popis: Optional[str] = None
    typ: Optional[str] = None
    verze_od: Optional[str] = None
    verze_do: Optional[str] = None
    status: Optional[str] = None
    plny_text: Optional[str] = None
    fragment_count: Optional[int] = None


class LawFullTextResponse(BaseModel):
    iri: str
    citace: str
    nazev: str
    typ: Optional[str] = None
    verze_od: Optional[str] = None
    verze_do: Optional[str] = None
    plny_text: str
    fragment_count: int
    fragmenty: List[LawFragment]


# === Search Endpoints ===

@router.get("/search", response_model=SearchResponse)
async def search_laws(
    query: str = Query(..., min_length=2, description="Search term in Czech"),
    full_text: bool = Query(True, description="Search in law content"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    legal_act_type: Optional[str] = Query(
        None, description="Filter by type: zákon, nařízení, vyhláška"
    ),
    year_from: Optional[int] = Query(None, ge=1945, description="From year"),
    year_to: Optional[int] = Query(None, le=2030, description="To year"),
):
    """
    Search Czech laws via official e-Sbírka API.

    Examples:
    - GET /api/law/search?query=pracovní%20právo
    - GET /api/law/search?query=kupní%20smlouva&limit=10
    - GET /api/law/search?query=zákoník&legal_act_type=zákon
    - GET /api/law/search?query=daň&year_from=2020&year_to=2024

    Response includes:
    - iri: Unique law identifier (staleUrl)
    - citace: Official citation (e.g., "262/2006 Sb.")
    - nazev: Law title
    - typ: Type of legal act
    - verze_od: Effective from date
    - status: Current status (AKTUALNE_PLATNY, ZRUSENY, etc.)
    """
    try:
        logger.info(f"=== LAW SEARCH REQUEST ===")
        logger.info(f"Query: '{query}'")
        logger.info(f"Params: full_text={full_text}, limit={limit}, type={legal_act_type}")

        results = await esbirka_client.search_laws(
            query=query,
            full_text=full_text,
            limit=limit,
            legal_act_type=legal_act_type,
            year_from=year_from,
            year_to=year_to,
        )

        logger.info(f"Raw results count: {len(results)}")

        # Format results
        formatted = []
        for r in results:
            formatted.append(
                LawSearchResult(
                    iri=r.get("iri", ""),
                    citace=r.get("citation", r.get("citace", "")),
                    nazev=r.get("title", r.get("nazev", "")),
                    typ=r.get("type", r.get("typ", "")),
                    verze_od=r.get("effective_from", r.get("verze_od", "")),
                    verze_do=r.get("effective_to", r.get("verze_do", "")),
                    popis=r.get("description", r.get("popis", "")),
                    status=r.get("status", ""),
                    staleUrl=r.get("staleUrl", r.get("iri", "")),
                )
            )

        logger.info(f"Returning {len(formatted)} formatted results")

        return SearchResponse(
            query=query,
            count=len(formatted),
            results=formatted,
            timestamp=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"=== LAW SEARCH ERROR ===")
        logger.error(f"Query: '{query}'")
        logger.error(f"Error: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


# === Law Detail Endpoints ===

@router.get("/detail")
async def get_law_by_url(
    stale_url: str = Query(..., description="Law staleUrl from search results (e.g., /sb/2006/262/2025-06-01)"),
):
    """
    Retrieve law details by staleUrl.
    
    Use the staleUrl/iri from search results.
    
    Example:
    - GET /api/law/detail?stale_url=/sb/2006/262/2025-06-01
    """
    try:
        logger.info(f"Law detail by URL: {stale_url}")
        
        law_data = await esbirka_client.get_law(stale_url)

        return JSONResponse({
            "iri": stale_url,
            "citace": law_data.get("citation", ""),
            "nazev": law_data.get("title", ""),
            "popis": law_data.get("description", ""),
            "typ": law_data.get("type", ""),
            "verze_od": law_data.get("effective_from", ""),
            "verze_do": law_data.get("effective_to", ""),
            "status": law_data.get("status", ""),
            "full_citation": law_data.get("full_citation", ""),
            "short_citation": law_data.get("short_citation", ""),
            "amendments_count": len(law_data.get("amendments", [])),
        })

    except Exception as e:
        logger.error(f"Law detail error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/full-text")
async def get_law_full_text(
    stale_url: str = Query(..., description="Law staleUrl from search results"),
):
    """
    Get complete law with full text and all sections.
    
    Returns the law with assembled full text from all fragments.
    
    Example:
    - GET /api/law/full-text?stale_url=/sb/2006/262/2025-06-01
    """
    try:
        logger.info(f"Law full text: {stale_url}")
        
        law_data = await esbirka_client.get_law_full_text(stale_url)
        
        # Format fragments
        fragments = []
        for frag in law_data.get("fragments", []):
            fragments.append(LawFragment(
                id=frag.get("id"),
                full_citation=frag.get("full_citation", ""),
                short_citation=frag.get("short_citation", ""),
                text=frag.get("text", ""),
                is_effective=frag.get("is_effective", True),
            ))

        return JSONResponse({
            "iri": stale_url,
            "citace": law_data.get("citation", ""),
            "nazev": law_data.get("title", ""),
            "typ": law_data.get("type", ""),
            "verze_od": law_data.get("effective_from", ""),
            "verze_do": law_data.get("effective_to", ""),
            "plny_text": law_data.get("full_text", ""),
            "fragment_count": law_data.get("fragment_count", 0),
            "fragmenty": [f.model_dump() for f in fragments[:100]],  # Limit to 100 fragments
        })

    except Exception as e:
        logger.error(f"Full text error: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fragments")
async def get_fragments_by_url(
    stale_url: str = Query(..., description="Law staleUrl from search results"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=200, description="Max fragments per page"),
):
    """
    Get law sections/articles/paragraphs.
    
    Returns structured breakdown of the law with pagination.
    
    Example:
    - GET /api/law/fragments?stale_url=/sb/2006/262/2025-06-01&page=1
    """
    try:
        logger.info(f"Law fragments: {stale_url} (page={page})")

        fragments = await esbirka_client.get_law_fragments(stale_url, page=page)

        return JSONResponse({
            "stale_url": stale_url,
            "page": page,
            "total": len(fragments),
            "fragmenty": fragments[:limit],
        })

    except Exception as e:
        logger.error(f"Fragments error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === History & Relationships ===

@router.get("/history")
async def get_law_history(
    stale_url: str = Query(..., description="Law staleUrl from search results"),
):
    """
    Get version history of a law.
    
    Shows all versions with effective dates.
    
    Example:
    - GET /api/law/history?stale_url=/sb/2006/262/2025-06-01
    """
    try:
        logger.info(f"Law history: {stale_url}")
        
        history = await esbirka_client.get_law_history(stale_url)
        
        return JSONResponse({
            "stale_url": stale_url,
            "versions": history.get("versions", []),
        })

    except Exception as e:
        logger.error(f"History error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/relationships")
async def get_law_relationships(
    stale_url: str = Query(..., description="Law staleUrl from search results"),
):
    """
    Get law relationships (amendments, derogations, implementations).
    
    Shows how this law relates to other laws.
    
    Example:
    - GET /api/law/relationships?stale_url=/sb/2006/262/2025-06-01
    """
    try:
        logger.info(f"Law relationships: {stale_url}")
        
        relationships = await esbirka_client.get_law_relationships(stale_url)
        
        return JSONResponse({
            "stale_url": stale_url,
            "relationships": relationships.get("relationships", []),
        })

    except Exception as e:
        logger.error(f"Relationships error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === Legacy endpoints for backward compatibility ===

@router.get("/{law_id}")
async def get_law_details_legacy(
    law_id: str = Path(..., description="Law ID (e.g., 262-2006)"),
    date: Optional[str] = Query(
        None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Version date (YYYY-MM-DD)",
    ),
):
    """
    Retrieve law by citation ID (legacy endpoint).
    
    For new integrations, use /api/law/detail with stale_url parameter.

    Examples:
    - GET /api/law/262-2006
    - GET /api/law/262-2006?date=2015-01-01
    """
    try:
        logger.info(f"Law details (legacy): {law_id} (date={date})")

        # Convert legacy format to staleUrl format
        # 262-2006 -> /sb/2006/262
        parts = law_id.replace("-", "/").split("/")
        if len(parts) == 2:
            # Format: number-year -> /sb/year/number
            stale_url = f"/sb/{parts[1]}/{parts[0]}"
        else:
            stale_url = f"/sb/{law_id}"
        
        if date:
            stale_url = f"{stale_url}/{date}"

        law_data = await esbirka_client.get_law(stale_url)

        return JSONResponse({
            "iri": stale_url,
            "citace": law_data.get("citation", ""),
            "nazev": law_data.get("title", ""),
            "popis": law_data.get("description", ""),
            "typ": law_data.get("type", ""),
            "verze_od": law_data.get("effective_from", ""),
            "verze_do": law_data.get("effective_to", ""),
            "plny_text": law_data.get("full_text", ""),
        })

    except Exception as e:
        logger.error(f"Law details error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{law_id}/fragments")
async def get_law_fragments_legacy(
    law_id: str = Path(..., description="Law ID (e.g., 262-2006)"),
    limit: int = Query(50, ge=1, le=200, description="Max fragments"),
):
    """
    Get law fragments by citation ID (legacy endpoint).
    
    For new integrations, use /api/law/fragments with stale_url parameter.
    """
    try:
        logger.info(f"Law fragments (legacy): {law_id}")

        # Convert legacy format
        parts = law_id.replace("-", "/").split("/")
        if len(parts) == 2:
            stale_url = f"/sb/{parts[1]}/{parts[0]}"
        else:
            stale_url = f"/sb/{law_id}"

        fragments = await esbirka_client.get_law_fragments(stale_url)

        return JSONResponse({
            "law_id": law_id,
            "stale_url": stale_url,
            "total": len(fragments),
            "fragmenty": fragments[:limit],
        })

    except Exception as e:
        logger.error(f"Fragments error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
