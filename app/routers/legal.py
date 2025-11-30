"""
Legal Search Router - Legacy endpoints (backward compatible)
Uses general_courts collection (czech_court_decisions_rag)
Same quality pipeline as v2
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
    """
    Case search using legacy collection (czech_court_decisions_rag)
    Same quality pipeline: queries → search → cross-encoder → answer
    """
    try:
        # Generate multiple queries for better recall
        queries = await llm_service.generate_search_queries(request.question, num_queries=5)
        
        # Search with cross-encoder reranking
        cases = await multi_source_engine.search(queries, DataSource.GENERAL_COURTS, limit=request.top_k)
        
        # Generate answer
        answer = await llm_service.answer_based_on_cases(request.question, cases)
        
        return CaseSearchResponse(answer=answer, supporting_cases=cases)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/case-search-stream")
async def case_search_stream(
    question: str = Query(..., min_length=3, max_length=5000),
    top_k: int = Query(5, ge=1, le=20),
    api_key_valid: bool = Depends(verify_api_key_query),
):
    """Streaming case search - legacy collection"""

    async def generate():
        try:
            print(f"\n{'='*60}")
            print(f"🎯 LEGACY SEARCH (czech_court_decisions_rag)")
            print(f"   Question: {question[:80]}...")
            print(f"{'='*60}")
            
            yield 'data: {"type": "case_search_start"}\n\n'
            
            # Generate queries
            queries = await llm_service.generate_search_queries(question, num_queries=5)
            
            # Search with cross-encoder
            yield 'data: {"type": "cases_fetching"}\n\n'
            cases = await multi_source_engine.search(queries, DataSource.GENERAL_COURTS, limit=top_k)
            
            # Stream answer
            yield 'data: {"type": "gpt_answer_start"}\n\n'
            
            full_answer = ""
            async for chunk in llm_service.answer_based_on_cases_stream(question, cases):
                full_answer += chunk
                yield f"data: {json.dumps({'type': 'case_answer_chunk', 'content': chunk})}\n\n"
            
            yield 'data: {"type": "gpt_answer_end"}\n\n'
            
            # Send cases with full text
            yield 'data: {"type": "cases_start"}\n\n'
            for case in cases:
                full_text = case.subject or ''
                case_data = {
                    'type': 'case',
                    'case_number': case.case_number,
                    'court': case.court,
                    'subject': full_text[:500] + '...' if len(full_text) > 500 else full_text,
                    'full_text': full_text,
                    'text_length': len(full_text),
                    'date_issued': case.date_issued,
                    'ecli': case.ecli,
                    'keywords': case.keywords,
                    'legal_references': case.legal_references,
                    'relevance_score': round(case.relevance_score, 3),
                    'source_url': case.source_url,
                }
                yield f"data: {json.dumps(case_data)}\n\n"
            
            yield 'data: {"type": "case_search_end"}\n\n'
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/combined-search", response_model=CombinedSearchResponse)
async def combined_search(request: QueryRequest, api_key_valid: bool = Depends(verify_api_key)):
    """Combined web + case search"""
    try:
        import asyncio
        
        async def do_case_search():
            queries = await llm_service.generate_search_queries(request.question, num_queries=5)
            cases = await multi_source_engine.search(queries, DataSource.GENERAL_COURTS, limit=request.top_k)
            answer = await llm_service.answer_based_on_cases(request.question, cases)
            return answer, cases
        
        web_task = llm_service.get_sonar_answer(request.question)
        case_task = do_case_search()
        
        (web_answer, web_citations), (case_answer, cases) = await asyncio.gather(web_task, case_task)
        
        return CombinedSearchResponse(
            web_answer=web_answer,
            web_source="Perplexity Sonar",
            web_citations=web_citations,
            case_answer=case_answer,
            supporting_cases=cases,
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
            queries = await llm_service.generate_search_queries(question, num_queries=5)
            cases = await multi_source_engine.search(queries, DataSource.GENERAL_COURTS, limit=top_k)
            
            yield 'data: {"type": "gpt_answer_start"}\n\n'
            case_full = ""
            async for chunk in llm_service.answer_based_on_cases_stream(question, cases):
                case_full += chunk
                yield f"data: {json.dumps({'type': 'case_answer_chunk', 'content': chunk})}\n\n"
            yield 'data: {"type": "gpt_answer_end"}\n\n'
            
            # Send cases
            yield 'data: {"type": "cases_start"}\n\n'
            for case in cases:
                full_text = case.subject or ''
                yield f"data: {json.dumps({'type': 'case', 'case_number': case.case_number, 'court': case.court, 'full_text': full_text, 'text_length': len(full_text), 'relevance_score': round(case.relevance_score, 3), 'source_url': case.source_url})}\n\n"
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
