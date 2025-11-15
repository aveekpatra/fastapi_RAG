import asyncio

import httpx

from app.config import settings
from app.models import CaseResult
from app.services.embedding import get_embedding


async def get_cases_from_qdrant(question: str, top_k: int) -> list[CaseResult]:
    """
    Search Qdrant for most relevant cases using sentence transformers
    Implements retry logic with exponential backoff for serverless cold starts
    """
    max_retries = settings.QDRANT_MAX_RETRIES
    initial_timeout = settings.QDRANT_INITIAL_TIMEOUT

    try:
        vector = await get_embedding(question)

        if vector is None:
            print("Chyba: Nepodařilo se vygenerovat vektorové vyjádření")
            return []

        headers = (
            {"api-key": settings.QDRANT_API_KEY} if settings.QDRANT_API_KEY else {}
        )

        for attempt in range(max_retries):
            try:
                timeout = initial_timeout * (
                    2**attempt
                )  # Exponential backoff: 30, 60, 120 seconds

                async with httpx.AsyncClient(timeout=timeout) as client:
                    print(
                        f"Attempt {attempt + 1}/{max_retries} with timeout {timeout}s"
                    )

                    response = await client.post(
                        f"{settings.qdrant_url}/collections/{settings.QDRANT_COLLECTION}/points/search",
                        headers=headers,
                        json={
                            "vector": vector,
                            "limit": top_k,
                            "with_payload": True,
                        },
                    )

                    if response.status_code == 200:
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
                                    legal_references=payload.get(
                                        "legal_references", []
                                    ),
                                    source_url=payload.get("source_url"),
                                    relevance_score=result.get("score", 0.0),
                                )
                            )
                        return cases

                    # Don't retry on client errors (4xx)
                    if 400 <= response.status_code < 500:
                        print(f"Client error in Qdrant: {response.status_code}")
                        print(f"Response: {response.text}")
                        return []

                    # Log server error and continue to retry
                    print(
                        f"Server error in Qdrant (attempt {attempt + 1}): {response.status_code}"
                    )
                    print(f"Response: {response.text}")

            except httpx.TimeoutException as e:
                print(f"Timeout error (attempt {attempt + 1}/{max_retries}): {str(e)}")
            except httpx.ConnectError as e:
                print(
                    f"Connection error (attempt {attempt + 1}/{max_retries}): {str(e)}"
                )
            except Exception as e:
                print(
                    f"Unexpected error (attempt {attempt + 1}/{max_retries}): {str(e)}"
                )

            # If not the last attempt, wait before retrying
            if attempt < max_retries - 1:
                wait_time = 2**attempt  # 1s, 2s, 4s between retries
                print(f"Waiting {wait_time}s before retry...")
                await asyncio.sleep(wait_time)

        print(f"Failed after {max_retries} attempts")
        return []

    except Exception as e:
        print(f"Fatal error in Qdrant query: {str(e)}")
        return []


async def debug_qdrant_connection() -> dict:
    """
    Debug Qdrant connection and return status
    Implements retry logic with exponential backoff
    """
    max_retries = settings.QDRANT_MAX_RETRIES
    initial_timeout = settings.QDRANT_INITIAL_TIMEOUT

    headers = {"api-key": settings.QDRANT_API_KEY} if settings.QDRANT_API_KEY else {}

    for attempt in range(max_retries):
        try:
            timeout = initial_timeout * (2**attempt)  # 30, 60, 120 seconds

            async with httpx.AsyncClient(timeout=timeout) as client:
                print(
                    f"Debug attempt {attempt + 1}/{max_retries} with timeout {timeout}s"
                )

                response = await client.get(
                    f"{settings.qdrant_url}/collections",
                    headers=headers,
                )

                return {
                    "status": response.status_code,
                    "url": settings.qdrant_url,
                    "text": response.text[:500],
                    "headers": dict(response.headers),
                    "attempts": attempt + 1,
                }

        except httpx.TimeoutException as e:
            print(f"Debug timeout (attempt {attempt + 1}/{max_retries}): {str(e)}")
        except httpx.ConnectError as e:
            print(
                f"Debug connection error (attempt {attempt + 1}/{max_retries}): {str(e)}"
            )
        except Exception as e:
            print(f"Debug error (attempt {attempt + 1}/{max_retries}): {str(e)}")

        # If not the last attempt, wait before retrying
        if attempt < max_retries - 1:
            wait_time = 2**attempt  # 1s, 2s, 4s between retries
            print(f"Waiting {wait_time}s before retry...")
            await asyncio.sleep(wait_time)

    return {
        "error": "Failed after all retry attempts",
        "url": settings.qdrant_url,
        "attempts": max_retries,
    }
