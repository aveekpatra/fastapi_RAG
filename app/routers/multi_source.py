"""
Multi-Source Search Router - V2 API with orchestrated search
"""
import json
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
from app.services.multi_source_search import DataSource, multi_source_engine, get_configs
from app.services.llm import llm_service

router = APIRouter(prefix="/v2", tags=["multi-source"])


def _convert_source(source: DataSourceEnum) -> DataSource:
    """Convert API enum to internal enum"""
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
    """Get list of available data sources with document counts"""
    sources = await multi_source_engine.get_available_sources()
    return [DataSourceInfo(**s) for s in sources]


@router.post("/case-search", response_model=CaseSearchResponse)
async def case_search(request: QueryRequest, api_key_valid: bool = Depends(verify_api_key)):
    """
    Orchestrated case search with reranking
    
    Default: searches all 3 court collections (constitutional, supreme, admin)
    """
    try:
        source = _convert_source(request.source)
        
        # Generate query variants for better recall
        queries = await llm_service.generate_search_queries(request.question, num_queries=3)
        
        # Multi-query search with RRF fusion
        cases = await multi_source_engine.multi_query_search(
            queries=queries,
            source=source,
            results_per_query=15,
            final_limit=request.top_k,
        )

        # Generate answer
        answer = ""
        filtered_cases = cases
        if cases:
            answer = await llm_service.answer_based_on_cases(request.question, cases)
            if "⚠️ ŽÁDNÉ RELEVANTNÍ PŘÍPADY" in answer:
                filtered_cases = []

        return CaseSearchResponse(answer=answer, supporting_cases=filtered_cases)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/case-search-stream")
async def case_search_stream(
    question: str = Query(..., min_length=3, max_length=5000),
    top_k: int = Query(7, ge=1, le=20),
    source: DataSourceEnum = Query(DataSourceEnum.ALL_COURTS),
    api_key_valid: bool = Depends(verify_api_key_query),
):
    """Streaming orchestrated case search"""

    async def generate():
        try:
            internal_source = _convert_source(source)
            
            yield f'data: {json.dumps({"type": "search_start", "source": source.value})}\n\n'
            yield 'data: {"type": "generating_queries"}\n\n'

            # Generate queries
            queries = await llm_service.generate_search_queries(question, num_queries=3)
            yield f'data: {json.dumps({"type": "queries_generated", "count": len(queries)})}\n\n'

            # Search
            yield 'data: {"type": "searching"}\n\n'
            cases = await multi_source_engine.multi_query_search(
                queries=queries,
                source=internal_source,
                results_per_query=15,
                final_limit=top_k,
            )
            yield f'data: {json.dumps({"type": "cases_found", "count": len(cases)})}\n\n'

            # Stream answer
            yield 'data: {"type": "generating_answer"}\n\n'
            full_answer = ""
            if cases:
                async for chunk in llm_service.answer_based_on_cases_stream(question, cases):
                    full_answer += chunk
                    yield f"data: {json.dumps({'type': 'answer_chunk', 'content': chunk})}\n\n"

            yield 'data: {"type": "answer_complete"}\n\n'

            # Send cases
            relevant = "⚠️ ŽÁDNÉ RELEVANTNÍ PŘÍPADY" not in full_answer
            yield 'data: {"type": "cases_start"}\n\n'
            
            if relevant:
                for case in cases:
                    yield f"data: {json.dumps({'type': 'case', 'case_number': case.case_number, 'court': case.court, 'subject': (case.subject or '')[:300], 'date_issued': case.date_issued, 'relevance_score': round(case.relevance_score, 3), 'data_source': case.data_source})}\n\n"

            yield 'data: {"type": "search_complete"}\n\n'
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/combined-search", response_model=CombinedSearchResponse)
async def combined_search(request: QueryRequest, api_key_valid: bool = Depends(verify_api_key)):
    """Combined web + case search"""
    try:
        source = _convert_source(request.source)

        # Parallel: web search + case search
        web_task = llm_service.get_sonar_answer(request.question)
        
        queries = await llm_service.generate_search_queries(request.question, num_queries=3)
        case_task = multi_source_engine.multi_query_search(
            queries=queries, source=source, results_per_query=15, final_limit=request.top_k
        )

        web_result, cases = await asyncio.gather(web_task, case_task)
        web_answer, web_citations = web_result

        # Generate case answer
        case_answer = ""
        filtered_cases = cases
        if cases:
            case_answer = await llm_service.answer_based_on_cases(request.question, cases)
            if "⚠️ ŽÁDNÉ RELEVANTNÍ PŘÍPADY" in case_answer:
                filtered_cases = []

        return CombinedSearchResponse(
            web_answer=web_answer,
            web_source="Perplexity Sonar",
            web_citations=web_citations,
            case_answer=case_answer,
            supporting_cases=filtered_cases,
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
            cases = await multi_source_engine.multi_query_search(
                queries=queries, source=internal_source, results_per_query=15, final_limit=top_k
            )

            case_full = ""
            if cases:
                async for chunk in llm_service.answer_based_on_cases_stream(question, cases):
                    case_full += chunk
                    yield f"data: {json.dumps({'type': 'case_chunk', 'content': chunk})}\n\n"

            yield 'data: {"type": "case_search_complete"}\n\n'

            # Cases
            relevant = "⚠️ ŽÁDNÉ RELEVANTNÍ PŘÍPADY" not in case_full
            if relevant:
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


# Need to import asyncio for parallel execution
import asyncio
