"""
Multi-Source Search Router
Provides endpoints for searching across multiple legal data sources
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
from app.services.multi_source_search import (
    DataSource,
    multi_source_engine,
    get_configs,
)
from app.services.llm import llm_service

router = APIRouter(prefix="/v2", tags=["multi-source"])


def _convert_source(source: DataSourceEnum) -> DataSource:
    """Convert API enum to internal enum"""
    return DataSource(source.value)


@router.get("/sources", response_model=List[DataSourceInfo])
async def get_available_sources(api_key_valid: bool = Depends(verify_api_key)):
    """Get list of available data sources with their status"""
    sources = await multi_source_engine.get_available_sources()
    return [DataSourceInfo(**s) for s in sources]


@router.post("/case-search", response_model=CaseSearchResponse)
async def multi_source_case_search(
    request: QueryRequest,
    api_key_valid: bool = Depends(verify_api_key),
):
    """Search for cases across specified data source"""
    try:
        source = _convert_source(request.source)
        configs = get_configs()
        config = configs.get(source)

        if source == DataSource.ALL or (config and config.uses_chunking):
            cases = await multi_source_engine.search_collection(
                query=request.question, source=source, limit=request.top_k
            )
        else:
            queries = await llm_service.generate_search_queries(request.question, num_queries=2)
            cases = await multi_source_engine.multi_query_search(
                queries=queries, source=source, results_per_query=10, final_limit=request.top_k
            )

        answer = ""
        filtered_cases = cases
        if cases:
            answer = await llm_service.answer_based_on_cases(request.question, cases)
            if "⚠️ ŽÁDNÉ RELEVANTNÍ PŘÍPADY" in answer or "žádné relevantní případy" in answer.lower():
                filtered_cases = []

        return CaseSearchResponse(answer=answer, supporting_cases=filtered_cases)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/case-search-stream")
async def multi_source_case_search_stream(
    question: str = Query(..., description="Legal question", min_length=3, max_length=5000),
    top_k: int = Query(5, ge=1, le=20),
    source: DataSourceEnum = Query(DataSourceEnum.GENERAL_COURTS),
    api_key_valid: bool = Depends(verify_api_key_query),
):
    """Streaming case search across specified data source"""

    async def generate():
        try:
            internal_source = _convert_source(source)
            yield f'data: {json.dumps({"type": "case_search_start", "source": source.value})}\n\n'
            yield 'data: {"type": "cases_fetching"}\n\n'

            configs = get_configs()
            config = configs.get(internal_source)

            if internal_source == DataSource.ALL or (config and config.uses_chunking):
                cases = await multi_source_engine.search_collection(
                    query=question, source=internal_source, limit=top_k
                )
            else:
                queries = await llm_service.generate_search_queries(question, num_queries=2)
                cases = await multi_source_engine.multi_query_search(
                    queries=queries, source=internal_source, results_per_query=10, final_limit=top_k
                )

            yield 'data: {"type": "gpt_answer_start"}\n\n'

            full_answer = ""
            if cases:
                async for chunk in llm_service.answer_based_on_cases_stream(question, cases):
                    full_answer += chunk
                    yield f"data: {json.dumps({'type': 'case_answer_chunk', 'content': chunk})}\n\n"

            yield 'data: {"type": "gpt_answer_end"}\n\n'

            cases_relevant = "⚠️ ŽÁDNÉ RELEVANTNÍ PŘÍPADY" not in full_answer
            yield 'data: {"type": "cases_start"}\n\n'

            if cases_relevant:
                for case in cases:
                    yield f"data: {json.dumps({'type': 'case', 'case_number': case.case_number, 'court': case.court, 'subject': (case.subject or '')[:500], 'date_issued': case.date_issued, 'relevance_score': round(case.relevance_score, 3)})}\n\n"

            yield 'data: {"type": "case_search_end"}\n\n'
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/combined-search", response_model=CombinedSearchResponse)
async def multi_source_combined_search(
    request: QueryRequest,
    api_key_valid: bool = Depends(verify_api_key),
):
    """Combined search using web (Sonar) and case search"""
    try:
        source = _convert_source(request.source)

        web_answer, web_citations = await llm_service.get_sonar_answer(request.question)

        configs = get_configs()
        config = configs.get(source)

        if source == DataSource.ALL or (config and config.uses_chunking):
            cases = await multi_source_engine.search_collection(
                query=request.question, source=source, limit=request.top_k
            )
        else:
            queries = await llm_service.generate_search_queries(request.question, num_queries=2)
            cases = await multi_source_engine.multi_query_search(
                queries=queries, source=source, results_per_query=10, final_limit=request.top_k
            )

        case_answer = ""
        filtered_cases = cases
        if cases:
            case_answer = await llm_service.answer_based_on_cases(request.question, cases)
            if "⚠️ ŽÁDNÉ RELEVANTNÍ PŘÍPADY" in case_answer:
                filtered_cases = []

        return CombinedSearchResponse(
            web_answer=web_answer,
            web_source="Perplexity Sonar via OpenRouter",
            web_citations=web_citations,
            case_answer=case_answer,
            supporting_cases=filtered_cases,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/combined-search-stream")
async def multi_source_combined_search_stream(
    question: str = Query(..., description="Legal question"),
    top_k: int = Query(5),
    source: DataSourceEnum = Query(DataSourceEnum.GENERAL_COURTS),
    api_key_valid: bool = Depends(verify_api_key_query),
):
    """Streaming combined search with source selection"""

    async def generate():
        try:
            internal_source = _convert_source(source)
            web_answer_full = ""
            case_answer_full = ""

            # Web search
            yield 'data: {"type": "web_search_start"}\n\n'
            async for chunk_text, final_answer, citations in llm_service.get_sonar_answer_stream(question):
                if chunk_text:
                    web_answer_full += chunk_text
                    yield f"data: {json.dumps({'type': 'web_answer_chunk', 'content': chunk_text})}\n\n"
                elif final_answer is not None:
                    web_answer_full = final_answer
                    if citations:
                        yield f"data: {json.dumps({'type': 'web_citations', 'citations': citations})}\n\n"
                    break
            yield 'data: {"type": "web_search_end"}\n\n'

            # Case search
            yield f'data: {json.dumps({"type": "case_search_start", "source": source.value})}\n\n'

            configs = get_configs()
            config = configs.get(internal_source)

            if internal_source == DataSource.ALL or (config and config.uses_chunking):
                cases = await multi_source_engine.search_collection(
                    query=question, source=internal_source, limit=top_k
                )
            else:
                queries = await llm_service.generate_search_queries(question, num_queries=2)
                cases = await multi_source_engine.multi_query_search(
                    queries=queries, source=internal_source, results_per_query=10, final_limit=top_k
                )

            yield 'data: {"type": "gpt_answer_start"}\n\n'
            if cases:
                async for chunk in llm_service.answer_based_on_cases_stream(question, cases):
                    case_answer_full += chunk
                    yield f"data: {json.dumps({'type': 'case_answer_chunk', 'content': chunk})}\n\n"
            yield 'data: {"type": "gpt_answer_end"}\n\n'

            cases_relevant = "⚠️ ŽÁDNÉ RELEVANTNÍ PŘÍPADY" not in case_answer_full
            yield 'data: {"type": "cases_start"}\n\n'
            if cases_relevant:
                for case in cases:
                    yield f"data: {json.dumps({'type': 'case', 'case_number': case.case_number, 'court': case.court, 'relevance_score': round(case.relevance_score, 3)})}\n\n"
            yield 'data: {"type": "case_search_end"}\n\n'

            # Summary
            if web_answer_full and case_answer_full:
                yield 'data: {"type": "summary_start"}\n\n'
                async for chunk in llm_service.generate_summary_stream(question, web_answer_full, case_answer_full):
                    yield f"data: {json.dumps({'type': 'summary_chunk', 'content': chunk})}\n\n"
                yield 'data: {"type": "summary_end"}\n\n'

            yield 'data: {"type": "combined_search_end"}\n\n'
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
