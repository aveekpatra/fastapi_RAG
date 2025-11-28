"""
Search Router - Debug and direct search endpoints
"""
import json

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.config import settings
from app.security import verify_api_key, verify_api_key_query
from app.services.embedding import get_embedding
from app.services.multi_source_search import DataSource, multi_source_engine

router = APIRouter(tags=["search"])


@router.get("/search-cases")
async def search_cases(
    question: str = Query(..., description="Legal question to search"),
    top_k: int = Query(5, description="Number of cases to retrieve"),
    api_key_valid: bool = Depends(verify_api_key),
):
    """Direct vector search in Qdrant without AI processing"""
    try:
        cases = await multi_source_engine.search_collection(
            query=question, source=DataSource.GENERAL_COURTS, limit=top_k
        )

        return {
            "query": question,
            "total_results": len(cases),
            "cases": [
                {
                    "case_number": c.case_number,
                    "court": c.court,
                    "subject": c.subject,
                    "date_issued": c.date_issued,
                    "relevance_score": round(c.relevance_score, 4),
                }
                for c in cases
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search-cases-stream")
async def search_cases_stream(
    question: str = Query(...),
    top_k: int = Query(5),
    api_key_valid: bool = Depends(verify_api_key_query),
):
    """Streaming vector search results"""

    async def generate():
        try:
            yield 'data: {"type": "search_start"}\n\n'

            cases = await multi_source_engine.search_collection(
                query=question, source=DataSource.GENERAL_COURTS, limit=top_k
            )

            yield f"data: {json.dumps({'type': 'search_info', 'query': question, 'total_results': len(cases)})}\n\n"

            for i, case in enumerate(cases):
                yield f"data: {json.dumps({'type': 'case_result', 'index': i + 1, 'case_number': case.case_number, 'court': case.court, 'relevance_score': round(case.relevance_score, 4)})}\n\n"

            yield 'data: {"type": "done"}\n\n'
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/debug/qdrant")
async def debug_qdrant(api_key_valid: bool = Depends(verify_api_key)):
    """Debug endpoint to verify Qdrant connection"""
    headers = {"api-key": settings.QDRANT_API_KEY} if settings.QDRANT_API_KEY else {}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{settings.qdrant_url}/collections", headers=headers)
            return {
                "status": response.status_code,
                "url": settings.qdrant_url,
                "collections": response.json() if response.status_code == 200 else response.text[:500],
            }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get("/debug/test-search")
async def debug_test_search(
    question: str = Query("rozvod"),
    top_k: int = Query(5),
    api_key_valid: bool = Depends(verify_api_key),
):
    """Debug endpoint to test case search"""
    debug_info = {
        "question": question,
        "qdrant_url": settings.qdrant_url,
        "collection": settings.QDRANT_COLLECTION,
    }

    try:
        cases = await multi_source_engine.search_collection(
            query=question, source=DataSource.GENERAL_COURTS, limit=top_k
        )
        debug_info["cases_found"] = len(cases)
        debug_info["cases"] = [{"case_number": c.case_number, "score": c.relevance_score} for c in cases]
        debug_info["status"] = "success"
    except Exception as e:
        debug_info["status"] = "error"
        debug_info["error"] = str(e)

    return debug_info


@router.get("/debug/qdrant-full")
async def debug_qdrant_full(api_key_valid: bool = Depends(verify_api_key)):
    """Comprehensive Qdrant diagnostic endpoint"""
    headers = {"api-key": settings.QDRANT_API_KEY} if settings.QDRANT_API_KEY else {}
    results = {"config": {"qdrant_url": settings.qdrant_url, "collection": settings.QDRANT_COLLECTION}, "tests": {}}

    # Test connection
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{settings.qdrant_url}/collections", headers=headers)
            results["tests"]["connection"] = {"status": "success" if response.status_code == 200 else "failed"}
    except Exception as e:
        results["tests"]["connection"] = {"status": "error", "error": str(e)}

    # Test collection
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{settings.qdrant_url}/collections/{settings.QDRANT_COLLECTION}", headers=headers
            )
            if response.status_code == 200:
                info = response.json().get("result", {})
                results["tests"]["collection"] = {
                    "status": "success",
                    "points_count": info.get("points_count", 0),
                }
            else:
                results["tests"]["collection"] = {"status": "failed"}
    except Exception as e:
        results["tests"]["collection"] = {"status": "error", "error": str(e)}

    # Test search
    try:
        vector = await get_embedding("rozvod manželství")
        if vector:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{settings.qdrant_url}/collections/{settings.QDRANT_COLLECTION}/points/search",
                    headers=headers,
                    json={"vector": vector, "limit": 3, "with_payload": True},
                )
                if response.status_code == 200:
                    result_list = response.json().get("result", [])
                    results["tests"]["search"] = {"status": "success", "results_found": len(result_list)}
                else:
                    results["tests"]["search"] = {"status": "failed"}
    except Exception as e:
        results["tests"]["search"] = {"status": "error", "error": str(e)}

    results["summary"] = {"all_passed": all(t.get("status") == "success" for t in results["tests"].values())}
    return results
