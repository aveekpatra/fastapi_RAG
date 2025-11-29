"""
Legal Search Router - Original endpoints (backward compatible)
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
    """Web search using Perplexity Sonar only"""
    try:
        answer, citations = await llm_service.get_sonar_answer(request.question)
        return WebSearchResponse(answer=answer, source="Perplexity Sonar via OpenRouter", citations=citations)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/web-search-stream")
async def web_search_stream(
    question: str = Query(..., description="Legal question"),
    api_key_valid: bool = Depends(verify_api_key_query),
):
    """Streaming web search using Perplexity Sonar"""

    async def generate():
        try:
            yield 'data: {"type": "web_search_start"}\n\n'
            async for chunk_text, final_answer, citations in llm_service.get_sonar_answer_stream(question):
                if chunk_text:
                    yield f"data: {json.dumps({'type': 'web_answer_chunk', 'content': chunk_text})}\n\n"
                elif final_answer is not None:
                    if citations:
                        yield f"data: {json.dumps({'type': 'web_citations', 'citations': citations})}\n\n"
                    break
            yield 'data: {"type": "web_search_end"}\n\n'
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/case-search", response_model=CaseSearchResponse)
async def case_search(request: QueryRequest, api_key_valid: bool = Depends(verify_api_key)):
    """Case search using Qdrant + GPT (general_courts collection)"""
    try:
        queries = await llm_service.generate_search_queries(request.question, num_queries=2)
        cases = await multi_source_engine.multi_query_search(
            queries=queries,
            source=DataSource.GENERAL_COURTS,
            results_per_query=10,
            final_limit=request.top_k,
            original_query=request.question,  # For entity extraction
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
async def case_search_stream(
    question: str = Query(..., min_length=3, max_length=5000),
    top_k: int = Query(5, ge=1, le=20),
    api_key_valid: bool = Depends(verify_api_key_query),
):
    """Streaming case search"""

    async def generate():
        try:
            yield 'data: {"type": "case_search_start"}\n\n'
            yield 'data: {"type": "cases_fetching"}\n\n'

            queries = await llm_service.generate_search_queries(question, num_queries=2)
            cases = await multi_source_engine.multi_query_search(
                queries=queries,
                source=DataSource.GENERAL_COURTS,
                results_per_query=10,
                final_limit=top_k,
                original_query=question,  # For entity extraction
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
                    yield f"data: {json.dumps({'type': 'case', 'case_number': case.case_number, 'court': case.court, 'subject': case.subject, 'date_issued': case.date_issued, 'ecli': case.ecli, 'keywords': case.keywords, 'legal_references': case.legal_references, 'relevance_score': round(case.relevance_score, 3), 'source_url': case.source_url})}\n\n"

            yield 'data: {"type": "case_search_end"}\n\n'
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/combined-search", response_model=CombinedSearchResponse)
async def combined_search(request: QueryRequest, api_key_valid: bool = Depends(verify_api_key)):
    """Combined search using web (Sonar) and case (Qdrant + GPT)"""
    try:
        web_answer, web_citations = await llm_service.get_sonar_answer(request.question)

        queries = await llm_service.generate_search_queries(request.question, num_queries=2)
        cases = await multi_source_engine.multi_query_search(
            queries=queries,
            source=DataSource.GENERAL_COURTS,
            results_per_query=10,
            final_limit=request.top_k,
            original_query=request.question,  # For entity extraction
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
async def combined_search_stream(
    question: str = Query(...),
    top_k: int = Query(5),
    api_key_valid: bool = Depends(verify_api_key_query),
):
    """Streaming combined search"""

    async def generate():
        try:
            web_answer_full = ""
            case_answer_full = ""

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

            yield 'data: {"type": "case_search_start"}\n\n'
            yield 'data: {"type": "cases_fetching"}\n\n'

            queries = await llm_service.generate_search_queries(question, num_queries=2)
            cases = await multi_source_engine.multi_query_search(
                queries=queries,
                source=DataSource.GENERAL_COURTS,
                results_per_query=10,
                final_limit=top_k,
                original_query=question,  # For entity extraction
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
                    yield f"data: {json.dumps({'type': 'case', 'case_number': case.case_number, 'court': case.court, 'subject': case.subject, 'date_issued': case.date_issued, 'relevance_score': round(case.relevance_score, 3), 'source_url': case.source_url})}\n\n"
            yield 'data: {"type": "case_search_end"}\n\n'

            if web_answer_full and case_answer_full:
                yield 'data: {"type": "summary_start"}\n\n'
                async for chunk in llm_service.generate_summary_stream(question, web_answer_full, case_answer_full):
                    yield f"data: {json.dumps({'type': 'summary_chunk', 'content': chunk})}\n\n"
                yield 'data: {"type": "summary_end"}\n\n'

            yield 'data: {"type": "combined_search_end"}\n\n'
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
