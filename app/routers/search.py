import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.security import verify_api_key, verify_api_key_query
from app.services.qdrant import debug_qdrant_connection, get_cases_from_qdrant

router = APIRouter(tags=["search"])


@router.get("/search-cases")
async def search_cases(
    question: str = Query(..., description="Legal question to search"),
    top_k: int = Query(5, description="Number of cases to retrieve"),
    api_key_valid: bool = Depends(verify_api_key),
):
    """
    Direct vector search in Qdrant without AI processing
    Returns matching cases with relevance scores
    """
    try:
        cases = await get_cases_from_qdrant(question, top_k)

        if not cases:
            return {
                "query": question,
                "total_results": 0,
                "cases": [],
                "message": "Žádné příslušné případy nebyly nalezeny",
            }

        return {
            "query": question,
            "total_results": len(cases),
            "cases": [
                {
                    "case_number": case.case_number,
                    "court": case.court,
                    "judge": case.judge,
                    "subject": case.subject,
                    "date_issued": case.date_issued,
                    "date_published": case.date_published,
                    "ecli": case.ecli,
                    "keywords": case.keywords,
                    "legal_references": case.legal_references,
                    "source_url": case.source_url,
                    "relevance_score": round(case.relevance_score, 4),
                }
                for case in cases
            ],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search-cases-stream")
async def search_cases_stream(
    question: str = Query(..., description="Legal question to search"),
    top_k: int = Query(5, description="Number of cases to retrieve"),
    api_key_valid: bool = Depends(verify_api_key_query),
):
    """
    Streaming vector search results
    """

    async def generate():
        try:
            yield 'data: {"type": "search_start"}\n\n'

            cases = await get_cases_from_qdrant(question, top_k)

            yield f"data: {
                json.dumps(
                    {
                        'type': 'search_info',
                        'query': question,
                        'total_results': len(cases),
                    }
                )
            }\n\n"

            for i, case in enumerate(cases):
                case_data = {
                    "type": "case_result",
                    "index": i + 1,
                    "case_number": case.case_number,
                    "court": case.court,
                    "judge": case.judge,
                    "subject": case.subject,
                    "date_issued": case.date_issued,
                    "date_published": case.date_published,
                    "ecli": case.ecli,
                    "keywords": case.keywords,
                    "legal_references": case.legal_references,
                    "source_url": case.source_url,
                    "relevance_score": round(case.relevance_score, 4),
                }
                yield f"data: {json.dumps(case_data)}\n\n"

            yield 'data: {"type": "done"}\n\n'

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/debug/qdrant")
async def debug_qdrant(api_key_valid: bool = Depends(verify_api_key)):
    """
    Debug endpoint to verify Qdrant connection
    """
    return await debug_qdrant_connection()
