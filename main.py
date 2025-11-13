import os
from typing import Optional
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from openai import OpenAI
import httpx
import json

load_dotenv()

app = FastAPI()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Qdrant Configuration
QDRANT_HOST = os.getenv("QDRANT_HOST")
QDRANT_PORT = os.getenv("QDRANT_PORT", "6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_HTTPS = os.getenv("QDRANT_HTTPS", "False").lower() == "true"
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION")

# Build Qdrant URL
QDRANT_PROTOCOL = "https" if QDRANT_HTTPS else "http"
QDRANT_URL = f"{QDRANT_PROTOCOL}://{QDRANT_HOST}:{QDRANT_PORT}"


class QueryRequest(BaseModel):
    question: str
    top_k: int = 5


class CaseResult(BaseModel):
    case_number: str
    court: str
    judge: Optional[str] = None
    subject: str
    date_issued: Optional[str] = None
    date_published: Optional[str] = None
    ecli: Optional[str] = None
    keywords: list[str] = []
    legal_references: list[str] = []
    source_url: Optional[str] = None
    relevance_score: float


class LegalQueryResponse(BaseModel):
    sonar_answer: str
    sonar_source: str
    case_based_answer: str
    supporting_cases: list[CaseResult]


@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.post("/legal-query")
async def legal_query(request: QueryRequest):
    """
    Stage 1: Get Sonar answer (unchanged)
    Stage 2: Query Qdrant for top 5 cases
    Stage 3: GPT-4o answers based on cases with citations
    """
    try:
        client = OpenAI(
            api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL
        )

        # Stage 1: Get Sonar answer (AS IS, no modification)
        sonar_answer = ""
        stream = client.chat.completions.create(
            model="perplexity/sonar",
            messages=[{"role": "user", "content": request.question}],
            stream=True,
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                sonar_answer += chunk.choices[0].delta.content

        # Stage 2: Get top 5 most relevant cases from Qdrant
        supporting_cases = await get_cases_from_qdrant(
            request.question, request.top_k
        )

        # Stage 3: GPT-4o answers based on cases with citations
        case_based_answer = ""
        if supporting_cases:
            case_based_answer = await answer_based_on_cases(
                request.question, supporting_cases, client
            )

        return LegalQueryResponse(
            sonar_answer=sonar_answer,
            sonar_source="Perplexity Sonar via OpenRouter",
            case_based_answer=case_based_answer,
            supporting_cases=supporting_cases,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/legal-query-stream")
async def legal_query_stream(question: str, top_k: int = 5):
    """
    Streaming endpoint
    Stage 1: Stream Sonar answer
    Stage 2: Get cases and GPT-4o answer
    """

    async def generate():
        try:
            client = OpenAI(
                api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL
            )

            # Stage 1: Stream Sonar answer
            yield "data: {\"type\": \"sonar_start\"}\n\n"

            sonar_answer = ""
            stream = client.chat.completions.create(
                model="perplexity/sonar",
                messages=[{"role": "user", "content": question}],
                stream=True,
            )

            for chunk in stream:
                if chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    sonar_answer += token
                    data = {
                        "type": "sonar_chunk",
                        "content": token,
                    }
                    yield f"data: {json.dumps(data)}\n\n"

            yield "data: {\"type\": \"sonar_end\"}\n\n"

            # Stage 2: Get cases from Qdrant
            yield "data: {\"type\": \"cases_fetching\"}\n\n"

            supporting_cases = await get_cases_from_qdrant(question, top_k)

            # Stage 3: Stream GPT-4o answer based on cases
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

            # Send supporting cases metadata
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


async def answer_based_on_cases(
    question: str, cases: list[CaseResult], client: OpenAI
) -> str:
    """
    GPT-4o answers the question based on all case data
    Cites all relevant cases with full details
    """
    try:
        # Format all cases for context (NO TRUNCATION)
        cases_context = format_cases_for_context(cases)

        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """You are a Czech legal expert. Answer the user's question 
based ONLY on the provided court cases. Cite all relevant cases with:
- Case number
- Court name
- Date issued
- ECLI reference
- Legal references (§ citations)
- Relevant quote or reasoning from the case

Provide comprehensive analysis with proper Czech legal citations.""",
                },
                {
                    "role": "user",
                    "content": f"""Question: {question}

Based on these Czech court cases, please answer the question with full citations:

{cases_context}

Provide a detailed answer citing all relevant cases.""",
                },
            ],
            temperature=0.5,
            max_tokens=2000,
        )

        answer = (response.choices[0].message.content or "").strip()
        return answer

    except Exception as e:
        print(f"Error generating case-based answer: {str(e)}")
        return ""


async def answer_based_on_cases_stream(
    question: str, cases: list[CaseResult], client: OpenAI
):
    """
    Stream GPT-4o answer based on cases
    """
    try:
        cases_context = format_cases_for_context(cases)

        stream = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """You are a Czech legal expert. Answer the user's question 
based ONLY on the provided court cases. Cite all relevant cases with:
- Case number
- Court name
- Date issued
- ECLI reference
- Legal references (§ citations)
- Relevant quote or reasoning from the case

Provide comprehensive analysis with proper Czech legal citations.""",
                },
                {
                    "role": "user",
                    "content": f"""Question: {question}

Based on these Czech court cases, please answer the question with full citations:

{cases_context}

Provide a detailed answer citing all relevant cases.""",
                },
            ],
            temperature=0.5,
            max_tokens=2000,
            stream=True,
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    except Exception as e:
        print(f"Error streaming case-based answer: {str(e)}")


def format_cases_for_context(cases: list[CaseResult]) -> str:
    """
    Format all cases (NO TRUNCATION) for GPT context
    """
    context = ""
    for i, case in enumerate(cases, 1):
        context += f"""
CASE {i}:
Case Number: {case.case_number}
Court: {case.court}
Judge: {case.judge or "N/A"}
Date Issued: {case.date_issued}
Date Published: {case.date_published}
ECLI: {case.ecli}
Subject: {case.subject}
Keywords: {', '.join(case.keywords)}
Legal References: {', '.join(case.legal_references)}
Source URL: {case.source_url}
Relevance Score: {case.relevance_score}
---
"""
    return context


async def get_cases_from_qdrant(
    question: str, top_k: int
) -> list[CaseResult]:
    """
    Search Qdrant for top K most relevant cases
    Returns full case data (NO TRUNCATION)
    """
    try:
        vector = await get_embedding(question)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points/search",
                headers = {"api-key": QDRANT_API_KEY} if QDRANT_API_KEY else {},
                json={
                    "vector": vector,
                    "limit": top_k,
                    "with_payload": True,
                },
            )

            if response.status_code != 200:
                raise Exception(
                    f"Qdrant search failed: {response.text}"
                )

            results = response.json()

            cases = []
            for result in results.get("result", []):
                payload = result.get("payload", {})
                cases.append(
                    CaseResult(
                        case_number=payload.get("case_number", "N/A"),
                        court=payload.get("court", "N/A"),
                        judge=payload.get("judge"),
                        subject=payload.get("subject", ""),
                        date_issued=payload.get("date_issued"),
                        date_published=payload.get("date_published"),
                        ecli=payload.get("ecli"),
                        keywords=payload.get("keywords", []),
                        legal_references=payload.get(
                            "legal_references", []
                        ),
                        source_url=payload.get("source_url"),
                        relevance_score=result.get("score", 0.0),
                    )
                )

            return cases

    except Exception as e:
        print(f"Error querying Qdrant: {str(e)}")
        return []
        
# Debug route for Qdrant

@app.get("/debug/qdrant")
async def debug_qdrant():
    try:
        async with httpx.AsyncClient() as client:
            headers = {"api-key": QDRANT_API_KEY} if QDRANT_API_KEY else {}
            response = await client.post(
                f"{QDRANT_URL}/health",
                headers=headers,
            )
            return {
                "status": response.status_code,
                "url": QDRANT_URL,
                "response": response.json()
            }
    except Exception as e:
        return {"error": str(e), "url": QDRANT_URL}
        
async def get_embedding(text: str) -> list[float]:
    """
    Get embedding for the question
    """
    try:
        client = OpenAI(
            api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL
        )

        response = client.embeddings.create(
            model="openai/text-embedding-3-small",
            input=text,
        )

        return response.data[0].embedding

    except Exception as e:
        print(f"Error getting embedding: {str(e)}")
        return [0.0] * 1536


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app, host="0.0.0.0", port=int(os.getenv("PORT", 8000))
    )