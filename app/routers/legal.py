import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.models import (
    CaseSearchResponse,
    CombinedSearchResponse,
    QueryRequest,
    WebSearchResponse,
)
from app.security import verify_api_key, verify_api_key_query
from app.services.llm import (
    answer_based_on_cases,
    answer_based_on_cases_stream,
    get_openai_client,
    get_sonar_answer,
    get_sonar_answer_stream,
)
from app.services.qdrant import get_cases_from_qdrant

router = APIRouter(tags=["search"])


# Web Search (Sonar) Only Endpoints
@router.post("/web-search", response_model=WebSearchResponse)
async def web_search(
    request: QueryRequest, api_key_valid: bool = Depends(verify_api_key)
):
    """
    Web search using Perplexity Sonar only
    Returns answer with citations but no case information
    """
    try:
        answer, citations = await get_sonar_answer(request.question)

        return WebSearchResponse(
            answer=answer,
            source="Perplexity Sonar via OpenRouter",
            citations=citations,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/web-search-stream")
async def web_search_stream(
    question: str = Query(..., description="Legal question to search"),
    api_key_valid: bool = Depends(verify_api_key_query),
):
    """
    Streaming web search using Perplexity Sonar only
    """

    async def generate():
        try:
            yield 'data: {"type": "web_search_start"}\n\n'

            # Stream Sonar response directly
            sonar_stream = get_sonar_answer_stream(question)
            async for chunk_text, final_answer, citations in sonar_stream:
                if chunk_text:
                    # Stream individual chunk
                    data = {
                        "type": "web_answer_chunk",
                        "content": chunk_text,
                    }
                    yield f"data: {json.dumps(data)}\n\n"
                elif final_answer is not None:
                    # Final chunk with complete answer and citations
                    if citations:
                        yield f"data: {
                            json.dumps(
                                {'type': 'web_citations', 'citations': citations}
                            )
                        }\n\n"
                    break

            yield 'data: {"type": "web_search_end"}\n\n'

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# Case Search (Qdrant + GPT) Only Endpoints
@router.post("/case-search", response_model=CaseSearchResponse)
async def case_search(
    request: QueryRequest, 
    api_key_valid: bool = Depends(verify_api_key),
    use_improved_rag: bool = Query(
        None, 
        description="Use improved RAG pipeline (query generation + hybrid search). If not specified, uses config default."
    )
):
    """
    Case search using Qdrant + GPT only
    Returns answer based on court cases without web search
    
    Supports two modes:
    - Basic: Single vector search (original)
    - Improved: Query generation + hybrid search + reranking (set use_improved_rag=true or USE_IMPROVED_RAG env var)
    """
    try:
        client = get_openai_client()
        
        # Get supporting cases from Qdrant (with optional improved RAG)
        supporting_cases = await get_cases_from_qdrant(
            request.question, 
            request.top_k,
            use_improved_rag=use_improved_rag,
            openai_client=client
        )

        # Generate case-based answer
        answer = ""
        if supporting_cases:
            answer = await answer_based_on_cases(
                request.question, supporting_cases, client
            )

        return CaseSearchResponse(
            answer=answer,
            supporting_cases=supporting_cases,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/case-search-stream")
async def case_search_stream(
    question: str = Query(..., description="Legal question to search", min_length=3, max_length=1000),
    top_k: int = Query(5, description="Number of cases to retrieve", ge=1, le=20),
    use_improved_rag: bool = Query(
        None, 
        description="Use improved RAG pipeline (query generation + hybrid search)"
    ),
    api_key_valid: bool = Depends(verify_api_key_query),
):
    """
    Streaming case search using Qdrant + GPT only
    
    Supports two modes:
    - Basic: Single vector search (original)
    - Improved: Query generation + hybrid search + reranking
    """

    async def generate():
        try:
            yield 'data: {"type": "case_search_start"}\n\n'

            client = get_openai_client()

            yield 'data: {"type": "cases_fetching"}\n\n'

            supporting_cases = await get_cases_from_qdrant(
                question, 
                top_k,
                use_improved_rag=use_improved_rag,
                openai_client=client
            )

            print(f"🔍 Found {len(supporting_cases)} cases for question: {question[:50]}...")

            yield 'data: {"type": "gpt_answer_start"}\n\n'

            if supporting_cases:
                print(f"✅ Starting to stream answer for {len(supporting_cases)} cases")
                chunk_count = 0
                async for chunk in answer_based_on_cases_stream(
                    question, supporting_cases, client
                ):
                    chunk_count += 1
                    data = {
                        "type": "case_answer_chunk",
                        "content": chunk,
                    }
                    yield f"data: {json.dumps(data)}\n\n"
                print(f"✅ Streamed {chunk_count} chunks")
            else:
                print("⚠️ No supporting cases found, skipping answer generation")

            yield 'data: {"type": "gpt_answer_end"}\n\n'

            yield 'data: {"type": "cases_start"}\n\n'

            for case in supporting_cases:
                case_data = {
                    "type": "case",
                    "case_number": case.case_number,
                    "court": case.court,
                    "judge": case.judge,
                    "subject": case.subject,
                    "date_issued": case.date_issued,
                    "ecli": case.ecli,
                    "keywords": case.keywords,
                    "legal_references": case.legal_references,
                    "relevance_score": round(case.relevance_score, 3),
                    "source_url": case.source_url,
                }
                yield f"data: {json.dumps(case_data)}\n\n"

            yield 'data: {"type": "case_search_end"}\n\n'

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# Combined Search (Web + Case) Endpoints
@router.post("/combined-search", response_model=CombinedSearchResponse)
async def combined_search(
    request: QueryRequest, 
    api_key_valid: bool = Depends(verify_api_key),
    use_improved_rag: bool = Query(
        None, 
        description="Use improved RAG pipeline for case search"
    )
):
    """
    Combined search using both web (Sonar) and case (Qdrant + GPT) sources
    Returns answers from both sources with citations and case information
    
    Case search supports two modes:
    - Basic: Single vector search (original)
    - Improved: Query generation + hybrid search + reranking
    """
    try:
        client = get_openai_client()
        
        # Get Sonar answer with citations
        web_answer, web_citations = await get_sonar_answer(request.question)

        # Get supporting cases from Qdrant (with optional improved RAG)
        supporting_cases = await get_cases_from_qdrant(
            request.question, 
            request.top_k,
            use_improved_rag=use_improved_rag,
            openai_client=client
        )

        # Generate case-based answer
        case_answer = ""
        if supporting_cases:
            case_answer = await answer_based_on_cases(
                request.question, supporting_cases, client
            )

        return CombinedSearchResponse(
            web_answer=web_answer,
            web_source="Perplexity Sonar via OpenRouter",
            web_citations=web_citations,
            case_answer=case_answer,
            supporting_cases=supporting_cases,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/combined-search-stream")
async def combined_search_stream(
    question: str = Query(..., description="Legal question to search"),
    top_k: int = Query(5, description="Number of cases to retrieve"),
    use_improved_rag: bool = Query(
        None, 
        description="Use improved RAG pipeline for case search"
    ),
    api_key_valid: bool = Depends(verify_api_key_query),
):
    """
    Streaming combined search using both web (Sonar) and case (Qdrant + GPT) sources
    
    Case search supports two modes:
    - Basic: Single vector search (original)
    - Improved: Query generation + hybrid search + reranking
    """

    async def generate():
        try:
            client = get_openai_client()

            # Store answers for summary
            web_answer_full = ""
            case_answer_full = ""

            # Web Search Part
            yield 'data: {"type": "web_search_start"}\n\n'

            # Stream Sonar response directly
            sonar_stream = get_sonar_answer_stream(question)
            async for chunk_text, final_answer, web_citations in sonar_stream:
                if chunk_text:
                    web_answer_full += chunk_text
                    # Stream individual chunk
                    data = {
                        "type": "web_answer_chunk",
                        "content": chunk_text,
                    }
                    yield f"data: {json.dumps(data)}\n\n"
                elif final_answer is not None:
                    web_answer_full = final_answer
                    # Final chunk with complete answer and citations
                    if web_citations:
                        yield f"data: {
                            json.dumps(
                                {'type': 'web_citations', 'citations': web_citations}
                            )
                        }\n\n"
                    break

            yield 'data: {"type": "web_search_end"}\n\n'

            # Case Search Part
            yield 'data: {"type": "case_search_start"}\n\n'

            yield 'data: {"type": "cases_fetching"}\n\n'

            supporting_cases = await get_cases_from_qdrant(
                question, 
                top_k,
                use_improved_rag=use_improved_rag,
                openai_client=client
            )

            yield 'data: {"type": "gpt_answer_start"}\n\n'

            if supporting_cases:
                async for chunk in answer_based_on_cases_stream(
                    question, supporting_cases, client
                ):
                    case_answer_full += chunk
                    data = {
                        "type": "case_answer_chunk",
                        "content": chunk,
                    }
                    yield f"data: {json.dumps(data)}\n\n"

            yield 'data: {"type": "gpt_answer_end"}\n\n'

            yield 'data: {"type": "cases_start"}\n\n'

            for case in supporting_cases:
                case_data = {
                    "type": "case",
                    "case_number": case.case_number,
                    "court": case.court,
                    "judge": case.judge,
                    "subject": case.subject,
                    "date_issued": case.date_issued,
                    "ecli": case.ecli,
                    "keywords": case.keywords,
                    "legal_references": case.legal_references,
                    "relevance_score": round(case.relevance_score, 3),
                    "source_url": case.source_url,
                }
                yield f"data: {json.dumps(case_data)}\n\n"

            yield 'data: {"type": "case_search_end"}\n\n'

            # Generate combined summary
            if web_answer_full and case_answer_full:
                yield 'data: {"type": "summary_start"}\n\n'
                
                from app.services.llm import generate_combined_summary_stream
                async for summary_chunk in generate_combined_summary_stream(
                    question, web_answer_full, case_answer_full, client
                ):
                    data = {
                        "type": "summary_chunk",
                        "content": summary_chunk,
                    }
                    yield f"data: {json.dumps(data)}\n\n"
                
                yield 'data: {"type": "summary_end"}\n\n'

            yield 'data: {"type": "combined_search_end"}\n\n'

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
