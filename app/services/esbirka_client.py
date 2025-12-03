"""
e-Sbírka REST API Client
Production client for Czech legal database search
"""
import httpx
from typing import Optional, List, Dict
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class ESbirkaAPIClient:
    """e-Sbírka REST API client"""

    def __init__(self):
        self.api_key = settings.ESBIRKA_API_KEY
        self.api_endpoint = settings.ESBIRKA_API_ENDPOINT
        self.timeout = 30.0
        
        logger.info(f"e-Sbírka client initialized")
        logger.info(f"  Endpoint: {self.api_endpoint}")
        logger.info(f"  API Key configured: {'Yes' if self.api_key else 'No'}")

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with auth"""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "LexioChat/1.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def search_laws(
        self,
        query: str,
        full_text: bool = True,
        limit: int = 20,
        offset: int = 0,
        legal_act_type: Optional[str] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
    ) -> List[Dict]:
        """
        Search laws using REST API.
        
        Args:
            query: Search term (e.g., "pracovní právo", "kupní smlouva")
            full_text: Search in complete law content vs metadata only
            limit: Results per page (max 100)
            offset: Pagination offset
            legal_act_type: Filter by type (zákon, nařízení, vyhláška)
            year_from: From year
            year_to: To year

        Returns:
            List of matching legal acts
        """
        url = f"{self.api_endpoint}/legal-acts/search"
        params = {
            "q": query,
            "full_text": "true" if full_text else "false",
            "limit": min(limit, 100),
            "offset": offset,
        }

        if legal_act_type:
            params["type"] = legal_act_type
        if year_from:
            params["year_from"] = year_from
        if year_to:
            params["year_to"] = year_to

        logger.info(f"[e-Sbírka] Search request:")
        logger.info(f"  URL: {url}")
        logger.info(f"  Params: {params}")
        logger.info(f"  Headers: Authorization={'Bearer ***' if self.api_key else 'None'}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    url, params=params, headers=self._get_headers()
                )
                
                logger.info(f"[e-Sbírka] Response status: {response.status_code}")
                
                if response.status_code == 401:
                    logger.error(f"[e-Sbírka] 401 Unauthorized - Invalid API key")
                    logger.error(f"[e-Sbírka] Response: {response.text[:500]}")
                    raise Exception("Invalid API key - check ESBIRKA_API_KEY")
                
                if response.status_code == 403:
                    logger.error(f"[e-Sbírka] 403 Forbidden - Access denied")
                    logger.error(f"[e-Sbírka] Response: {response.text[:500]}")
                    raise Exception("Access forbidden - check API permissions")
                
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After", "60")
                    logger.error(f"[e-Sbírka] 429 Rate limited - Retry after {retry_after}s")
                    raise Exception(f"Rate limited. Retry after {retry_after} seconds")
                
                if response.status_code != 200:
                    logger.error(f"[e-Sbírka] Error {response.status_code}")
                    logger.error(f"[e-Sbírka] Response: {response.text[:500]}")
                    raise Exception(f"API error: {response.status_code}")
                
                data = response.json()
                results = data.get("results", [])
                
                logger.info(f"[e-Sbírka] Success - {len(results)} results")
                if results:
                    logger.info(f"[e-Sbírka] First result: {results[0]}")
                
                return results

        except httpx.TimeoutException:
            logger.error(f"[e-Sbírka] Timeout after {self.timeout}s")
            raise Exception(f"Request timeout after {self.timeout}s")
        except httpx.RequestError as e:
            logger.error(f"[e-Sbírka] Request error: {e}")
            raise Exception(f"Request error: {e}")

    async def get_law(self, law_iri: str, version_date: Optional[str] = None) -> Dict:
        """Retrieve specific legal act."""
        if law_iri.count("/") < 3:
            parts = law_iri.split("/")
            law_iri = f"eli/cz/sb/{'/'.join(reversed(parts))}"

        url = f"{self.api_endpoint}/legal-acts/{law_iri}"
        params = {}
        if version_date:
            params["version"] = version_date

        logger.info(f"[e-Sbírka] Get law: {url}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    url, params=params, headers=self._get_headers()
                )
                
                if response.status_code != 200:
                    logger.error(f"[e-Sbírka] Get law error: {response.status_code}")
                    raise Exception(f"Law not found: {law_iri}")
                
                return response.json()

        except Exception as e:
            logger.error(f"[e-Sbírka] Error fetching law {law_iri}: {e}")
            raise

    async def get_law_fragments(self, law_iri: str) -> List[Dict]:
        """Get sections/articles of a legal act."""
        url = f"{self.api_endpoint}/legal-acts/{law_iri}/fragments"

        logger.info(f"[e-Sbírka] Get fragments: {url}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._get_headers())
                
                if response.status_code != 200:
                    logger.error(f"[e-Sbírka] Get fragments error: {response.status_code}")
                    return []
                
                data = response.json()
                return data.get("fragments", [])

        except Exception as e:
            logger.error(f"[e-Sbírka] Error fetching fragments: {e}")
            return []


# Global instance
esbirka_client = ESbirkaAPIClient()
