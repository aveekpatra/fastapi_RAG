"""
Law Search Router - e-Sbírka API Integration
Quick search for Czech legal acts
"""
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
import logging
import traceback

from app.services.esbirka_client import esbirka_client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/law", tags=["law-search"])


class LawSearchResult(BaseModel):
    iri: str
    citace: str
    nazev: str
    typ: Optional[str] = None
    verze_od: Optional[str] = None
    verze_do: Optional[str] = None
    popis: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    count: int
    results: List[LawSearchResult]
    timestamp: str


@router.get("/search", response_model=SearchResponse)
async def search_laws(
    query: str = Query(..., min_length=2, description="Search term in Czech"),
    full_text: bool = Query(True, description="Search in law content"),
    limit: int = Query(20, ge=1, le=50, description="Max results"),
    legal_act_type: Optional[str] = Query(
        None, description="Filter by type: zákon, nařízení, vyhláška"
    ),
    year_from: Optional[int] = Query(None, ge=1945, description="From year"),
    year_to: Optional[int] = Query(None, le=2030, description="To year"),
):
    """
    Quick search for Czech laws via e-Sbírka API.

    Examples:
    - GET /api/law/search?query=pracovní%20právo
    - GET /api/law/search?query=kupní%20smlouva&limit=10
    - GET /api/law/search?query=zákoník&legal_act_type=zákon

    Response includes:
    - iri: Unique law identifier
    - citace: Official citation (e.g., "262/2006 Sb.")
    - nazev: Law title
    - typ: Type of legal act
    - verze_od: Effective from date
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


@router.get("/{law_id}")
async def get_law_details(
    law_id: str,
    date: Optional[str] = Query(
        None,
        regex=r"^\d{4}-\d{2}-\d{2}$",
        description="Version date (YYYY-MM-DD)",
    ),
):
    """
    Retrieve complete law with full text and sections.

    Examples:
    - GET /api/law/262-2006
    - GET /api/law/262-2006?date=2015-01-01
    """
    try:
        logger.info(f"Law details: {law_id} (date={date})")

        # Normalize citation format
        if not law_id.startswith("eli"):
            law_id_normalized = law_id.replace("-", "/")
            law_id_normalized = f"eli/cz/sb/{law_id_normalized}"
        else:
            law_id_normalized = law_id

        law_data = await esbirka_client.get_law(law_id_normalized, date)

        return JSONResponse(
            {
                "iri": law_id_normalized,
                "citace": law_data.get("citation", ""),
                "nazev": law_data.get("title", ""),
                "popis": law_data.get("description", ""),
                "typ": law_data.get("type", ""),
                "verze_od": law_data.get("effective_from", ""),
                "verze_do": law_data.get("effective_to", ""),
                "plny_text": law_data.get("full_text", ""),
            }
        )

    except Exception as e:
        logger.error(f"Law details error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{law_id}/fragments")
async def get_law_fragments(
    law_id: str,
    limit: int = Query(50, ge=1, le=200, description="Max fragments"),
):
    """
    Get law sections/articles/paragraphs.

    Returns structured breakdown of the law.
    """
    try:
        logger.info(f"Law fragments: {law_id}")

        if not law_id.startswith("eli"):
            law_id = law_id.replace("-", "/")
            law_id = f"eli/cz/sb/{law_id}"

        fragments = await esbirka_client.get_law_fragments(law_id)

        return JSONResponse(
            {
                "law_id": law_id,
                "total": len(fragments),
                "fragmenty": fragments[:limit],
            }
        )

    except Exception as e:
        logger.error(f"Fragments error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
