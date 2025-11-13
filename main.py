import os
from typing import Optional
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from openai import OpenAI
from sentence_transformers import SentenceTransformer
import httpx
import json

load_dotenv()

app = FastAPI()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

QDRANT_HOST = os.getenv("QDRANT_HOST")
QDRANT_PORT = os.getenv("QDRANT_PORT", "6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_HTTPS = os.getenv("QDRANT_HTTPS", "False").lower() == "true"
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION")

QDRANT_PROTOCOL = "https" if QDRANT_HTTPS else "http"
QDRANT_URL = f"{QDRANT_PROTOCOL}://{QDRANT_HOST}:{QDRANT_PORT}"

embedding_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")


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

        sonar_answer = ""
        stream = client.chat.completions.create(
            model="perplexity/sonar",
            messages=[{"role": "user", "content": request.question}],
            stream=True,
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                sonar_answer += chunk.choices[0].delta.content

        supporting_cases = await get_cases_from_qdrant(
            request.question, request.top_k
        )

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
    Streaming endpoint for legal queries
    """

    async def generate():
        try:
            client = OpenAI(
                api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL
            )

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


async def answer_based_on_cases(
    question: str, cases: list[CaseResult], client: OpenAI
) -> str:
    """
    GPT-4o answers the question based on all case data with citations
    """
    try:
        cases_context = format_cases_for_context(cases)

        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """Jste právní expert se specialistem na české právo. Odpovídejte na otázky uživatele VÝHRADNĚ na základě poskytnutých rozhodnutí českých soudů. 

Vaše odpověď musí obsahovat:
1. Přímou odpověď na položenou otázku na základě příslušných rozhodnutí
2. Citace všech relevantních rozhodnutí s následujícími údaji:
   - Spisová značka rozsudku
   - Název soudu
   - Datum vydání
   - ECLI reference
   - Relevantní právní předpisy (§ citace)
   - Klíčové právní principy nebo závěry z rozhodnutí

Odpověď musí být:
- Strukturovaná a logická
- Psaná v češtině
- Soustředěna výhradně na poskytnutá rozhodnutí
- Bez generalizací nebo informací mimo základnu rozhodnutí
- S přesnými citacemi a odkazem na čísla případů

Pokud je otázka nezodpověditelná na základě poskytnutých rozhodnutí, výslovně to uveďte.""",
                },
                {
                    "role": "user",
                    "content": f"""Otázka: {question}

Na základě těchto českých soudních rozhodnutí prosím odpovězte na otázku s detailními citacemi:

{cases_context}

Poskytněte podrobnou odpověď s citacemi všech relevantních rozhodnutí.""",
                },
            ],
            temperature=0.5,
            max_tokens=2000,
        )

        answer = (response.choices[0].message.content or "").strip()
        return answer

    except Exception as e:
        print(f"Chyba pri generovani odpovedi zalozene na pripadech: {str(e)}")
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
                    "content": """Jste právní expert se specialistem na české právo. Odpovídejte na otázky uživatele VÝHRADNĚ na základě poskytnutých rozhodnutí českých soudů. 

Vaše odpověď musí obsahovat:
1. Přímou odpověď na položenou otázku na základě příslušných rozhodnutí
2. Citace všech relevantních rozhodnutí s následujícími údaji:
   - Spisová značka rozsudku
   - Název soudu
   - Datum vydání
   - ECLI reference
   - Relevantní právní předpisy (§ citace)
   - Klíčové právní principy nebo závěry z rozhodnutí

Odpověď musí být:
- Strukturovaná a logická
- Psaná v češtině
- Soustředěna výhradně na poskytnutá rozhodnutí
- Bez generalizací nebo informací mimo základnu rozhodnutí
- S přesnými citacemi a odkazem na čísla případů

Pokud je otázka nezodpověditelná na základě poskytnutých rozhodnutí, výslovně to uveďte.""",
                },
                {
                    "role": "user",
                    "content": f"""Otázka: {question}

Na základě těchto českých soudních rozhodnutí prosím odpovězte na otázku s detailními citacemi:

{cases_context}

Poskytněte podrobnou odpověď s citacemi všech relevantních rozhodnutí.""",
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
        print(f"Chyba pri streamovani odpovedi: {str(e)}")


def format_cases_for_context(cases: list[CaseResult]) -> str:
    """
    Format all cases for GPT context without truncation
    """
    context = ""
    for i, case in enumerate(cases, 1):
        context += f"""
ROZHODNUTÍ {i}:
Spisová značka: {case.case_number}
Soud: {case.court}
Soudce: {case.judge or "Neuvedeno"}
Datum vydání: {case.date_issued}
Datum publikace: {case.date_published}
ECLI: {case.ecli}
Předmět sporu: {case.subject}
Klíčová slova: {', '.join(case.keywords) if case.keywords else 'Neuvedena'}
Právní předpisy: {', '.join(case.legal_references) if case.legal_references else 'Neuvedeny'}
Zdroj: {case.source_url}
Relevance: {case.relevance_score}
---
"""
    return context


async def get_cases_from_qdrant(
    question: str, top_k: int
) -> list[CaseResult]:
    """
    Search Qdrant for most relevant cases using sentence transformers
    """
    try:
        vector = await get_embedding(question)

        if vector is None:
            print("Chyba: Nepodařilo se vygenerovat vektorové vyjádření")
            return []

        async with httpx.AsyncClient() as client:
            headers = {"api-key": QDRANT_API_KEY} if QDRANT_API_KEY else {}

            response = await client.post(
                f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points/search",
                headers=headers,
                json={
                    "vector": vector,
                    "limit": top_k,
                    "with_payload": True,
                },
                timeout=10.0,
            )

            if response.status_code != 200:
                print(f"Chyba pri hledani v Qdrant: {response.status_code}")
                print(f"Odpověď: {response.text}")
                return []

            results = response.json()
            print(f"Nalezeno {len(results.get('result', []))} případů")

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
                        legal_references=payload.get("legal_references", []),
                        source_url=payload.get("source_url"),
                        relevance_score=result.get("score", 0.0),
                    )
                )

            return cases

    except Exception as e:
        print(f"Chyba pri dotazu na Qdrant: {str(e)}")
        return []


async def get_embedding(text: str) -> Optional[list[float]]:
    """
    Get embedding using sentence transformers (paraphrase-multilingual-MiniLM-L12-v2)
    Must match the model used for Qdrant storage
    """
    try:
        embedding = embedding_model.encode(text).tolist()
        print(f"Vektorové vyjádření generováno: {len(embedding)} dimenzí")
        return embedding

    except Exception as e:
        print(f"Chyba pri generovani vektoru: {str(e)}")
        return None


@app.get("/debug/qdrant")
async def debug_qdrant():
    """
    Debug endpoint to verify Qdrant connection
    """
    try:
        async with httpx.AsyncClient() as client:
            headers = {"api-key": QDRANT_API_KEY} if QDRANT_API_KEY else {}

            response = await client.get(
                f"{QDRANT_URL}/collections",
                headers=headers,
                timeout=10.0,
            )

            return {
                "status": response.status_code,
                "url": QDRANT_URL,
                "text": response.text[:500],
                "headers": dict(response.headers),
            }
    except Exception as e:
        return {
            "error": str(e),
            "url": QDRANT_URL,
            "type": type(e).__name__
        }
        
@app.get("/search-cases")
async def search_cases(question: str, top_k: int = 5):
    """
    Direct vector search in Qdrant without AI processing
    Returns matching cases with relevance scores
    """
    try:
        cases = await get_cases_from_qdrant(question, top_k)

        if not cases:
            return {
                "query": question,
                "total_results": 0,
                "cases": [],
                "message": "Žádné příslušné případy nebyly nalezeny"
            }

        return {
            "query": question,
            "total_results": len(cases),
            "cases": [
                {
                    "case_number": case.case_number,
                    "court": case.court,
                    "judge": case.judge,
                    "subject": case.subject,
                    "date_issued": case.date_issued,
                    "date_published": case.date_published,
                    "ecli": case.ecli,
                    "keywords": case.keywords,
                    "legal_references": case.legal_references,
                    "source_url": case.source_url,
                    "relevance_score": round(case.relevance_score, 4),
                }
                for case in cases
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/search-cases-stream")
async def search_cases_stream(question: str, top_k: int = 5):
    """
    Streaming vector search results
    """

    async def generate():
        try:
            yield "data: {\"type\": \"search_start\"}\n\n"

            cases = await get_cases_from_qdrant(question, top_k)

            yield f"data: {json.dumps({
                'type': 'search_info',
                'query': question,
                'total_results': len(cases)
            })}\n\n"

            for i, case in enumerate(cases):
                case_data = {
                    "type": "case_result",
                    "index": i + 1,
                    "case_number": case.case_number,
                    "court": case.court,
                    "judge": case.judge,
                    "subject": case.subject,
                    "date_issued": case.date_issued,
                    "date_published": case.date_published,
                    "ecli": case.ecli,
                    "keywords": case.keywords,
                    "legal_references": case.legal_references,
                    "source_url": case.source_url,
                    "relevance_score": round(case.relevance_score, 4),
                }
                yield f"data: {json.dumps(case_data)}\n\n"

            yield "data: {\"type\": \"done\"}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app, host="0.0.0.0", port=int(os.getenv("PORT", 8000))
    )