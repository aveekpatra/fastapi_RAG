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


@router.get("/debug/test-search")
async def debug_test_search(
    question: str = Query("rozvod", description="Test question"),
    top_k: int = Query(5, description="Number of cases"),
    api_key_valid: bool = Depends(verify_api_key),
):
    """
    Debug endpoint to test case search with detailed logging
    """
    from app.config import settings
    
    debug_info = {
        "question": question,
        "top_k": top_k,
        "qdrant_url": settings.qdrant_url,
        "qdrant_collection": settings.QDRANT_COLLECTION,
        "qdrant_host": settings.QDRANT_HOST,
        "qdrant_port": settings.QDRANT_PORT,
        "qdrant_https": settings.QDRANT_HTTPS,
        "has_api_key": bool(settings.QDRANT_API_KEY),
    }
    
    try:
        cases = await get_cases_from_qdrant(question, top_k)
        debug_info["cases_found"] = len(cases)
        debug_info["cases"] = [
            {
                "case_number": c.case_number,
                "court": c.court,
                "relevance_score": c.relevance_score,
            }
            for c in cases
        ]
        debug_info["status"] = "success"
    except Exception as e:
        debug_info["status"] = "error"
        debug_info["error"] = str(e)
        import traceback
        debug_info["traceback"] = traceback.format_exc()
    
    return debug_info


@router.get("/debug/qdrant-full")
async def debug_qdrant_full(api_key_valid: bool = Depends(verify_api_key)):
    """
    Comprehensive Qdrant diagnostic endpoint
    Tests connection, collection info, and sample search
    """
    import httpx
    from app.config import settings
    from app.services.embedding import get_embedding
    
    results = {
        "config": {
            "qdrant_url": settings.qdrant_url,
            "qdrant_host": settings.QDRANT_HOST,
            "qdrant_port": settings.QDRANT_PORT,
            "qdrant_https": settings.QDRANT_HTTPS,
            "qdrant_collection": settings.QDRANT_COLLECTION,
            "has_api_key": bool(settings.QDRANT_API_KEY),
        },
        "tests": {}
    }
    
    headers = {"api-key": settings.QDRANT_API_KEY} if settings.QDRANT_API_KEY else {}
    
    # Test 1: Connection
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{settings.qdrant_url}/collections", headers=headers)
            
            if response.status_code == 200:
                collections_data = response.json()
                results["tests"]["connection"] = {
                    "status": "success",
                    "collections": collections_data.get("result", {}).get("collections", [])
                }
            else:
                results["tests"]["connection"] = {
                    "status": "failed",
                    "status_code": response.status_code,
                    "response": response.text[:500]
                }
                return results
    except Exception as e:
        results["tests"]["connection"] = {
            "status": "error",
            "error": str(e)
        }
        return results
    
    # Test 2: Collection Info
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{settings.qdrant_url}/collections/{settings.QDRANT_COLLECTION}",
                headers=headers
            )
            
            if response.status_code == 200:
                info = response.json()
                result = info.get('result', {})
                
                vectors_count = result.get('vectors_count') or result.get('points_count', 0)
                config = result.get('config', {})
                params = config.get('params', {})
                vectors_config = params.get('vectors', {})
                
                collection_info = {
                    "status": "success",
                    "points_count": vectors_count,
                    "status_info": result.get('status'),
                }
                
                if isinstance(vectors_config, dict):
                    collection_info["vector_size"] = vectors_config.get('size')
                    collection_info["distance_metric"] = vectors_config.get('distance')
                
                if vectors_count == 0:
                    collection_info["warning"] = "Collection is EMPTY! No data to search."
                
                results["tests"]["collection"] = collection_info
            else:
                results["tests"]["collection"] = {
                    "status": "failed",
                    "status_code": response.status_code,
                    "response": response.text[:500]
                }
                return results
    except Exception as e:
        results["tests"]["collection"] = {
            "status": "error",
            "error": str(e)
        }
        return results
    
    # Test 3: Sample Search
    try:
        test_query = "rozvod manželství"
        vector = await get_embedding(test_query)
        
        if vector is None:
            results["tests"]["search"] = {
                "status": "error",
                "error": "Failed to generate embedding"
            }
            return results
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.qdrant_url}/collections/{settings.QDRANT_COLLECTION}/points/search",
                headers=headers,
                json={
                    "vector": vector,
                    "limit": 5,
                    "with_payload": True,
                }
            )
            
            if response.status_code == 200:
                search_results = response.json()
                result_list = search_results.get('result', [])
                
                search_info = {
                    "status": "success",
                    "query": test_query,
                    "vector_dimension": len(vector),
                    "results_found": len(result_list),
                }
                
                if len(result_list) == 0:
                    search_info["warning"] = "Search returned 0 results! Collection might be empty or query doesn't match."
                else:
                    search_info["top_results"] = [
                        {
                            "case_number": r.get('payload', {}).get('case_number', 'N/A'),
                            "court": r.get('payload', {}).get('court', 'N/A'),
                            "score": round(r.get('score', 0), 4)
                        }
                        for r in result_list[:3]
                    ]
                
                results["tests"]["search"] = search_info
            else:
                results["tests"]["search"] = {
                    "status": "failed",
                    "status_code": response.status_code,
                    "response": response.text[:500]
                }
    except Exception as e:
        results["tests"]["search"] = {
            "status": "error",
            "error": str(e)
        }
        import traceback
        results["tests"]["search"]["traceback"] = traceback.format_exc()
    
    # Summary
    all_success = all(
        test.get("status") == "success" 
        for test in results["tests"].values()
    )
    
    results["summary"] = {
        "all_tests_passed": all_success,
        "recommendation": (
            "All tests passed! Qdrant is working correctly." 
            if all_success 
            else "Some tests failed. Check the details above."
        )
    }
    
    return results
