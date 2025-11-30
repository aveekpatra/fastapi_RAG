"""
Multi-Source Search Router - Quality Focused
Pipeline: Generate queries → Vector search → Cross-encoder rerank → Answer
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
    Quality-focused search:
    1. Generate 5-7 search queries
    2. Vector search (get lots of candidates)
    3. Cross-encoder rerank (precision)
    4. Generate answer
    """
    try:
        source = _convert_source(request.source)
        
        # Generate multiple queries for better recall
        queries = await llm_service.generate_search_queries(request.question, num_queries=7)
        
        # Search with cross-encoder reranking
        cases = await multi_source_engine.search(queries, source, limit=request.top_k)
        
        # Generate answer
        answer = await llm_service.answer_based_on_cases(request.question, cases)
        
        return CaseSearchResponse(answer=answer, supporting_cases=cases)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/case-search-stream")
async def case_search_stream(
    question: str = Query(..., min_length=3, max_length=5000),
    top_k: int = Query(10, ge=1, le=25),
    source: DataSourceEnum = Query(DataSourceEnum.ALL_COURTS),
    api_key_valid: bool = Depends(verify_api_key_query),
):
    """Streaming case search with quality focus"""

    async def generate():
        try:
            internal_source = _convert_source(source)
            
            print(f"\n{'='*60}")
            print(f"🎯 QUALITY SEARCH")
            print(f"   Question: {question[:80]}...")
            print(f"{'='*60}")
            
            yield f'data: {json.dumps({"type": "search_start", "source": source.value})}\n\n'
            
            # Step 1: Generate queries
            yield 'data: {"type": "generating_queries"}\n\n'
            queries = await llm_service.generate_search_queries(question, num_queries=7)
            yield f'data: {json.dumps({"type": "queries_generated", "count": len(queries)})}\n\n'
            
            # Step 2: Search with cross-encoder reranking
            yield 'data: {"type": "searching"}\n\n'
            cases = await multi_source_engine.search(queries, internal_source, limit=top_k)
            yield f'data: {json.dumps({"type": "cases_found", "count": len(cases)})}\n\n'
            
            # Step 3: Stream answer
            yield 'data: {"type": "generating_answer"}\n\n'
            
            full_answer = ""
            async for chunk in llm_service.answer_based_on_cases_stream(question, cases):
                full_answer += chunk
                yield f"data: {json.dumps({'type': 'answer_chunk', 'content': chunk})}\n\n"
            
            yield 'data: {"type": "answer_complete"}\n\n'
            
            # Send cases with full text (no silent truncation)
            yield 'data: {"type": "cases_start"}\n\n'
            print(f"\n📤 Sending {len(cases)} cases to frontend:")
            for idx, case in enumerate(cases):
                full_text = case.subject or ''
                # Preview is truncated but marked
                preview = full_text[:500] + '...' if len(full_text) > 500 else full_text
                
                print(f"   [{idx+1}] {case.case_number}: {len(full_text):,} chars")
                
                case_data = {
                    'type': 'case',
                    'citation_index': idx + 1,
                    'case_number': case.case_number,
                    'court': case.court,
                    'date_issued': case.date_issued,
                    'relevance_score': round(case.relevance_score, 3),
                    'data_source': case.data_source,
                    'subject': preview,  # Preview with truncation marker
                    'full_text': full_text,  # Full text, no truncation
                    'text_length': len(full_text),  # So frontend knows if truncated
                }
                yield f"data: {json.dumps(case_data)}\n\n"
            
            yield 'data: {"type": "search_complete"}\n\n'
            
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
        source = _convert_source(request.source)
        
        import asyncio
        
        async def do_case_search():
            queries = await llm_service.generate_search_queries(request.question, num_queries=7)
            cases = await multi_source_engine.search(queries, source, limit=request.top_k)
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
            queries = await llm_service.generate_search_queries(question, num_queries=7)
            cases = await multi_source_engine.search(queries, internal_source, limit=top_k)
            
            case_full = ""
            async for chunk in llm_service.answer_based_on_cases_stream(question, cases):
                case_full += chunk
                yield f"data: {json.dumps({'type': 'case_chunk', 'content': chunk})}\n\n"
            
            yield 'data: {"type": "case_search_complete"}\n\n'
            
            # Send cases
            for case in cases:
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
