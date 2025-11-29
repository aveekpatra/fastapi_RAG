"""
Legal Search Router - Legacy endpoints (backward compatible)
Uses general_courts collection by default
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.models import CaseSearchResponse, CombinedSearchResponse, QueryRequest, WebSearchResponse
from app.security import verify_api_key, verify_api_key_query
from app.services.llm import llm_service
from app.services.multi_source_search import DataSource, multi_source_engine

router = APIRouter(tags=["search"])


@router.post("/web-search", response_model=WebSearchResponse)
async def web_search(request: QueryRequest, api_key_valid: bool = Depends(verify_api_key)):
    """Web search using Perplexity Sonar"""
    try:
        answer, citations = await llm_service.get_sonar_answer(request.question)
        return WebSearchResponse(answer=answer, source="Perplexity Sonar", citations=citations)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/web-search-stream")
async def web_search_stream(
    question: str = Query(...),
    api_key_valid: bool = Depends(verify_api_key_query),
):
    """Streaming web search"""

    async def generate():
        try:
            yield 'data: {"type": "web_search_start"}\n\n'
            async for chunk, final, citations in llm_service.get_sonar_answer_stream(question):
                if chunk:
                    yield f"data: {json.dumps({'type': 'web_answer_chunk', 'content': chunk})}\n\n"
                elif final is not None:
                    if citations:
                        yield f"data: {json.dumps({'type': 'web_citations', 'citations': citations})}\n\n"
                    break
            yield 'data: {"type": "web_search_end"}\n\n'
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/case-search", response_model=CaseSearchResponse)
async def case_search(request: QueryRequest, api_key_valid: bool = Depends(verify_api_key)):
    """Case search using legacy collection"""
    try:
        queries = await llm_service.generate_search_queries(request.question, num_queries=2)
        cases = await multi_source_engine.search(queries, DataSource.GENERAL_COURTS, limit=10)
        relevant = await llm_service.filter_relevant_cases(request.question, cases, max_cases=request.top_k)
        answer = await llm_service.answer_based_on_cases(request.question, relevant)
        
        return CaseSearchResponse(answer=answer, supporting_cases=relevant)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/case-search-stream")
async def case_search_stream(
    question: str = Query(..., min_length=3, max_length=5000),
    top_k: int = Query(5, ge=1, le=20),
    api_key_valid: bool = Depends(verify_api_key_query),
):
    """Streaming case search"""

    async def generate():
        try:
            yield 'data: {"type": "case_search_start"}\n\n'
            
            queries = await llm_service.generate_search_queries(question, num_queries=2)
            cases = await multi_source_engine.search(queries, DataSource.GENERAL_COURTS, limit=10)
            relevant = await llm_service.filter_relevant_cases(question, cases, max_cases=top_k)
            
            yield 'data: {"type": "gpt_answer_start"}\n\n'
            
            full_answer = ""
            if relevant:
                async for chunk in llm_service.answer_based_on_cases_stream(question, relevant):
                    full_answer += chunk
                    yield f"data: {json.dumps({'type': 'case_answer_chunk', 'content': chunk})}\n\n"
            else:
                no_answer = "Nemám odpověď na tuto otázku."
                yield f"data: {json.dumps({'type': 'case_answer_chunk', 'content': no_answer})}\n\n"
            
            yield 'data: {"type": "gpt_answer_end"}\n\n'
            
            yield 'data: {"type": "cases_start"}\n\n'
            for case in relevant:
                yield f"data: {json.dumps({'type': 'case', 'case_number': case.case_number, 'court': case.court, 'subject': case.subject, 'date_issued': case.date_issued, 'relevance_score': round(case.relevance_score, 3), 'source_url': case.source_url})}\n\n"
            
            yield 'data: {"type": "case_search_end"}\n\n'
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/combined-search", response_model=CombinedSearchResponse)
async def combined_search(request: QueryRequest, api_key_valid: bool = Depends(verify_api_key)):
    """Combined web + case search"""
    try:
        web_answer, web_citations = await llm_service.get_sonar_answer(request.question)
        
        queries = await llm_service.generate_search_queries(request.question, num_queries=2)
        cases = await multi_source_engine.search(queries, DataSource.GENERAL_COURTS, limit=10)
        relevant = await llm_service.filter_relevant_cases(request.question, cases, max_cases=request.top_k)
        case_answer = await llm_service.answer_based_on_cases(request.question, relevant)
        
        return CombinedSearchResponse(
            web_answer=web_answer,
            web_source="Perplexity Sonar",
            web_citations=web_citations,
            case_answer=case_answer,
            supporting_cases=relevant,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/combined-search-stream")
async def combined_search_stream(
    question: str = Query(...),
    top_k: int = Query(5),
    api_key_valid: bool = Depends(verify_api_key_query),
):
    """Streaming combined search"""

    async def generate():
        try:
            # Web search
            yield 'data: {"type": "web_search_start"}\n\n'
            web_full = ""
            async for chunk, final, citations in llm_service.get_sonar_answer_stream(question):
                if chunk:
                    web_full += chunk
                    yield f"data: {json.dumps({'type': 'web_answer_chunk', 'content': chunk})}\n\n"
                elif final is not None:
                    web_full = final
                    if citations:
                        yield f"data: {json.dumps({'type': 'web_citations', 'citations': citations})}\n\n"
                    break
            yield 'data: {"type": "web_search_end"}\n\n'
            
            # Case search
            yield 'data: {"type": "case_search_start"}\n\n'
            queries = await llm_service.generate_search_queries(question, num_queries=2)
            cases = await multi_source_engine.search(queries, DataSource.GENERAL_COURTS, limit=10)
            relevant = await llm_service.filter_relevant_cases(question, cases, max_cases=top_k)
            
            yield 'data: {"type": "gpt_answer_start"}\n\n'
            case_full = ""
            if relevant:
                async for chunk in llm_service.answer_based_on_cases_stream(question, relevant):
                    case_full += chunk
                    yield f"data: {json.dumps({'type': 'case_answer_chunk', 'content': chunk})}\n\n"
            yield 'data: {"type": "gpt_answer_end"}\n\n'
            
            yield 'data: {"type": "cases_start"}\n\n'
            for case in relevant:
                yield f"data: {json.dumps({'type': 'case', 'case_number': case.case_number, 'court': case.court, 'relevance_score': round(case.relevance_score, 3)})}\n\n"
            yield 'data: {"type": "case_search_end"}\n\n'
            
            # Summary
            if web_full and case_full:
                yield 'data: {"type": "summary_start"}\n\n'
                async for chunk in llm_service.generate_summary_stream(question, web_full, case_full):
                    yield f"data: {json.dumps({'type': 'summary_chunk', 'content': chunk})}\n\n"
                yield 'data: {"type": "summary_end"}\n\n'
            
            yield 'data: {"type": "combined_search_end"}\n\n'
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
