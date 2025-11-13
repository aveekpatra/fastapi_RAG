import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.models import QueryRequest, LegalQueryResponse
from app.services.llm import (
    get_openai_client,
    get_sonar_answer,
    answer_based_on_cases,
    answer_based_on_cases_stream,
)
from app.services.qdrant import get_cases_from_qdrant

router = APIRouter(prefix="/legal-query", tags=["legal"])


@router.post("", response_model=LegalQueryResponse)
async def legal_query(request: QueryRequest):
    """
    Stage 1: Get Sonar answer with citations
    Stage 2: Query Qdrant for top 5 cases
    Stage 3: GPT-4o answers based on cases with citations
    """
    try:
        # Get Sonar answer with citations
        sonar_answer, sonar_citations = await get_sonar_answer(request.question)

        # Get supporting cases from Qdrant
        supporting_cases = await get_cases_from_qdrant(
            request.question, request.top_k
        )

        # Generate case-based answer
        case_based_answer = ""
        if supporting_cases:
            client = get_openai_client()
            case_based_answer = await answer_based_on_cases(
                request.question, supporting_cases, client
            )

        return LegalQueryResponse(
            sonar_answer=sonar_answer,
            sonar_source="Perplexity Sonar via OpenRouter",
            sonar_citations=sonar_citations,
            case_based_answer=case_based_answer,
            supporting_cases=supporting_cases,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("-stream")
async def legal_query_stream(question: str, top_k: int = 5):
    """
    Streaming endpoint for legal queries with citations
    """

    async def generate():
        try:
            client = get_openai_client()

            yield "data: {\"type\": \"sonar_start\"}\n\n"

            # Get Sonar response with citations
            sonar_answer, sonar_citations = await get_sonar_answer(question)

            # Stream the answer text
            for char in sonar_answer:
                data = {
                    "type": "sonar_chunk",
                    "content": char,
                }
                yield f"data: {json.dumps(data)}\n\n"

            # Send citations
            if sonar_citations:
                yield f"data: {json.dumps({
                    'type': 'sonar_citations',
                    'citations': sonar_citations
                })}\n\n"

            yield "data: {\"type\": \"sonar_end\"}\n\n"

            yield "data: {\"type\": \"cases_fetching\"}\n\n"

            supporting_cases = await get_cases_from_qdrant(question, top_k)

            yield "data: {\"type\": \"gpt_answer_start\"}\n\n"

            if supporting_cases:
                async for chunk in answer_based_on_cases_stream(
                    question, supporting_cases, client
                ):
                    data = {
                        "type": "gpt_answer_chunk",
                        "content": chunk,
                    }
                    yield f"data: {json.dumps(data)}\n\n"

            yield "data: {\"type\": \"gpt_answer_end\"}\n\n"

            yield "data: {\"type\": \"cases_start\"}\n\n"

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

            yield "data: {\"type\": \"done\"}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")