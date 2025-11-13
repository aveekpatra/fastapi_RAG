from typing import Optional
import httpx
from app.config import settings
from app.models import CaseResult
from app.services.embedding import get_embedding


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
            headers = (
                {"api-key": settings.QDRANT_API_KEY}
                if settings.QDRANT_API_KEY
                else {}
            )

            response = await client.post(
                f"{settings.qdrant_url}/collections/{settings.QDRANT_COLLECTION}/points/search",
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


async def debug_qdrant_connection() -> dict:
    """
    Debug Qdrant connection and return status
    """
    try:
        async with httpx.AsyncClient() as client:
            headers = (
                {"api-key": settings.QDRANT_API_KEY}
                if settings.QDRANT_API_KEY
                else {}
            )

            response = await client.get(
                f"{settings.qdrant_url}/collections",
                headers=headers,
                timeout=10.0,
            )

            return {
                "status": response.status_code,
                "url": settings.qdrant_url,
                "text": response.text[:500],
                "headers": dict(response.headers),
            }
    except Exception as e:
        return {
            "error": str(e),
            "url": settings.qdrant_url,
            "type": type(e).__name__,
        }