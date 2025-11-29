"""
Multi-Source Search Router - Simplified Pipeline
1. Generate search queries
2. Vector search
3. Filter relevant cases
4. Generate answer with full text
"""
import json
import re
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.models import (
    CaseSearchResponse,
    CombinedSearchResponse,
    DataSourceEnum,
    DataSourceInfo,
    QueryRequest,
)
from app.security import verify_api_key, verify_api_key_query
from app.services.multi_source_search import DataSource, multi_source_engine
from app.services.llm import llm_service

router = APIRouter(prefix="/v2", tags=["multi-source"])


def _convert_source(source: DataSourceEnum) -> DataSource:
    mapping = {
        DataSourceEnum.CONSTITUTIONAL_COURT: DataSource.CONSTITUTIONAL_COURT,
        DataSourceEnum.SUPREME_COURT: DataSource.SUPREME_COURT,
        DataSourceEnum.SUPREME_ADMIN_COURT: DataSource.SUPREME_ADMIN_COURT,
        DataSourceEnum.ALL_COURTS: DataSource.ALL_COURTS,
        DataSourceEnum.GENERAL_COURTS: DataSource.GENERAL_COURTS,
    }
    return mapping.get(source, DataSource.ALL_COURTS)


@router.get("/sources", response_model=List[DataSourceInfo])
async def get_available_sources(api_key_valid: bool = Depends(verify_api_key)):
    sources = await multi_source_engine.get_available_sources()
    return [DataSourceInfo(**s) for s in sources]


@router.post("/case-search", response_model=CaseSearchResponse)
async def case_search(request: QueryRequest, api_key_valid: bool = Depends(verify_api_key)):
    """
    Simplified pipeline:
    1. Generate search queries
    2. Vector search
    3. Filter relevant cases
    4. Generate answer
    """
    try:
        source = _convert_source(request.source)
        
        # Step 1: Generate search queries
        queries = await llm_service.generate_search_queries(request.question, num_queries=3)
        
        # Step 2: Vector search (returns cases with full text)
        cases = await multi_source_engine.search(queries, source, limit=10)
        
        # Step 3: Filter relevant cases
        relevant_cases = await llm_service.filter_relevant_cases(
            request.question, cases, max_cases=request.top_k
        )
        
        # Step 4: Generate answer
        answer = await llm_service.answer_based_on_cases(request.question, relevant_cases)
        
        return CaseSearchResponse(answer=answer, supporting_cases=relevant_cases)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/case-search-stream")
async def case_search_stream(
    question: str = Query(..., min_length=3, max_length=5000),
    top_k: int = Query(10, ge=1, le=25),
    source: DataSourceEnum = Query(DataSourceEnum.ALL_COURTS),
    api_key_valid: bool = Depends(verify_api_key_query),
):
    """Streaming case search"""

    async def generate():
        try:
            internal_source = _convert_source(source)
            
            print(f"\n🎯 Search: {question[:100]}...")
            
            yield f'data: {json.dumps({"type": "search_start", "source": source.value})}\n\n'
            
            # Step 1: Generate queries
            yield 'data: {"type": "generating_queries"}\n\n'
            queries = await llm_service.generate_search_queries(question, num_queries=3)
            yield f'data: {json.dumps({"type": "queries_generated", "count": len(queries)})}\n\n'
            
            # Step 2: Vector search
            yield 'data: {"type": "searching"}\n\n'
            cases = await multi_source_engine.search(queries, internal_source, limit=10)
            yield f'data: {json.dumps({"type": "cases_found", "count": len(cases)})}\n\n'
            
            # Step 3: Filter relevant
            yield 'data: {"type": "filtering"}\n\n'
            relevant_cases = await llm_service.filter_relevant_cases(question, cases, max_cases=top_k)
            yield f'data: {json.dumps({"type": "relevant_cases", "count": len(relevant_cases)})}\n\n'
            
            # Step 4: Stream answer
            yield 'data: {"type": "generating_answer"}\n\n'
            
            full_answer = ""
            if relevant_cases:
                async for chunk in llm_service.answer_based_on_cases_stream(question, relevant_cases):
                    full_answer += chunk
                    yield f"data: {json.dumps({'type': 'answer_chunk', 'content': chunk})}\n\n"
            else:
                no_answer = "Nemám odpověď na tuto otázku. V databázi jsem nenašel relevantní soudní rozhodnutí."
                full_answer = no_answer
                yield f"data: {json.dumps({'type': 'answer_chunk', 'content': no_answer})}\n\n"
            
            yield 'data: {"type": "answer_complete"}\n\n'
            
            # Send cases
            yield 'data: {"type": "cases_start"}\n\n'
            for idx, case in enumerate(relevant_cases):
                yield f"data: {json.dumps({'type': 'case', 'citation_index': idx + 1, 'case_number': case.case_number, 'court': case.court, 'subject': (case.subject or '')[:500], 'date_issued': case.date_issued, 'relevance_score': round(case.relevance_score, 3), 'data_source': case.data_source, 'full_text': case.subject or ''})}\n\n"
            
            yield 'data: {"type": "search_complete"}\n\n'
            
        except Exception as e:
            print(f"❌ Error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/combined-search", response_model=CombinedSearchResponse)
async def combined_search(request: QueryRequest, api_key_valid: bool = Depends(verify_api_key)):
    """Combined web + case search"""
    try:
        source = _convert_source(request.source)
        
        # Parallel: web + case search
        import asyncio
        
        async def do_case_search():
            queries = await llm_service.generate_search_queries(request.question, num_queries=3)
            cases = await multi_source_engine.search(queries, source, limit=10)
            relevant = await llm_service.filter_relevant_cases(request.question, cases, max_cases=request.top_k)
            answer = await llm_service.answer_based_on_cases(request.question, relevant)
            return answer, relevant
        
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
    top_k: int = Query(7),
    source: DataSourceEnum = Query(DataSourceEnum.ALL_COURTS),
    api_key_valid: bool = Depends(verify_api_key_query),
):
    """Streaming combined search"""

    async def generate():
        try:
            internal_source = _convert_source(source)
            
            # Web search
            yield 'data: {"type": "web_search_start"}\n\n'
            web_full = ""
            async for chunk, final, citations in llm_service.get_sonar_answer_stream(question):
                if chunk:
                    web_full += chunk
                    yield f"data: {json.dumps({'type': 'web_chunk', 'content': chunk})}\n\n"
                elif final is not None:
                    web_full = final
                    if citations:
                        yield f"data: {json.dumps({'type': 'web_citations', 'citations': citations})}\n\n"
                    break
            yield 'data: {"type": "web_search_complete"}\n\n'
            
            # Case search
            yield 'data: {"type": "case_search_start"}\n\n'
            queries = await llm_service.generate_search_queries(question, num_queries=3)
            cases = await multi_source_engine.search(queries, internal_source, limit=10)
            relevant = await llm_service.filter_relevant_cases(question, cases, max_cases=top_k)
            
            case_full = ""
            if relevant:
                async for chunk in llm_service.answer_based_on_cases_stream(question, relevant):
                    case_full += chunk
                    yield f"data: {json.dumps({'type': 'case_chunk', 'content': chunk})}\n\n"
            
            yield 'data: {"type": "case_search_complete"}\n\n'
            
            # Send cases
            for case in relevant:
                yield f"data: {json.dumps({'type': 'case', 'case_number': case.case_number, 'court': case.court, 'relevance_score': round(case.relevance_score, 3)})}\n\n"
            
            # Summary
            if web_full and case_full:
                yield 'data: {"type": "summary_start"}\n\n'
                async for chunk in llm_service.generate_summary_stream(question, web_full, case_full):
                    yield f"data: {json.dumps({'type': 'summary_chunk', 'content': chunk})}\n\n"
                yield 'data: {"type": "summary_complete"}\n\n'
            
            yield 'data: {"type": "complete"}\n\n'
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
