"""
e-Sbírka REST API Client
Production-ready client for Czech legal database search
"""
import httpx
from typing import Optional, List, Dict, Any
import logging
from datetime import datetime

from app.config import settings

logger = logging.getLogger(__name__)


class ESbirkaAPIClient:
    """Production-ready e-Sbírka REST API client with error handling"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_endpoint: str = "https://opendata.eselpoint.cz/api/v1",
    ):
        self.api_key = api_key or getattr(settings, "ESBIRKA_API_KEY", None)
        self.api_endpoint = api_endpoint
        self.timeout = 30.0

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with optional auth"""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "LexioChat/1.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _handle_response(self, response: httpx.Response) -> Dict:
        """Handle API responses with error checking"""
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "60")
            raise Exception(f"Rate limited. Retry after {retry_after} seconds")

        if response.status_code == 401:
            raise Exception("Invalid API key - check credentials")

        if response.status_code == 403:
            raise Exception("Access forbidden - check your permissions")

        if response.status_code >= 400:
            logger.error(f"API Error {response.status_code}: {response.text}")
            response.raise_for_status()

        return response.json() if response.text else {}

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
        Search laws with advanced filtering.

        Args:
            query: Search term (e.g., "pracovní právo", "kupní smlouva")
            full_text: Search in complete law content vs metadata only
            limit: Results per page (max 100)
            offset: Pagination offset
            legal_act_type: Filter by type (zákon, nařízení, vyhláška)
            year_from: From year (e.g., 2020)
            year_to: To year (e.g., 2024)

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

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    url, params=params, headers=self._get_headers()
                )
                data = self._handle_response(response)
                results = data.get("results", [])
                logger.info(f"Search completed: '{query}' - {len(results)} results")
                return results

        except httpx.TimeoutException:
            logger.error(f"Search timeout for query: {query}")
            raise
        except Exception as e:
            logger.error(f"Search error: {e}")
            raise

    async def get_law(
        self, law_iri: str, version_date: Optional[str] = None
    ) -> Dict:
        """
        Retrieve specific legal act.

        Args:
            law_iri: Law identifier (e.g., "eli/cz/sb/2006/262")
            version_date: Optional specific version date (YYYY-MM-DD)

        Returns:
            Complete legal act with metadata
        """
        # Convert common citation formats to IRI
        if law_iri.count("/") < 3:  # Likely citation format like "262/2006"
            parts = law_iri.split("/")
            law_iri = f"eli/cz/sb/{'/'.join(reversed(parts))}"

        url = f"{self.api_endpoint}/legal-acts/{law_iri}"
        params = {}
        if version_date:
            params["version"] = version_date

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    url, params=params, headers=self._get_headers()
                )
                data = self._handle_response(response)
                logger.info(f"Retrieved law: {law_iri}")
                return data

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Law not found: {law_iri}")
            raise

    async def get_law_fragments(self, law_iri: str) -> List[Dict]:
        """
        Get sections/articles of a legal act.

        Args:
            law_iri: Law identifier

        Returns:
            List of fragments (articles, sections) with full text
        """
        url = f"{self.api_endpoint}/legal-acts/{law_iri}/fragments"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._get_headers())
                data = self._handle_response(response)
                fragments = data.get("fragments", [])
                logger.info(f"Retrieved {len(fragments)} fragments for {law_iri}")
                return fragments

        except Exception as e:
            logger.error(f"Error fetching fragments: {e}")
            raise

    async def search_vocabulary(
        self, term: str, vocabulary: str = "czechvoc"
    ) -> List[Dict]:
        """
        Search legal vocabulary/terminology database.

        Args:
            term: Term to search for
            vocabulary: Vocabulary type (czechvoc, legal_act_types, etc.)

        Returns:
            Matching vocabulary entries with definitions
        """
        url = f"{self.api_endpoint}/vocabulary/{vocabulary}"
        params = {"q": term}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    url, params=params, headers=self._get_headers()
                )
                data = self._handle_response(response)
                terms = data.get("terms", [])
                logger.info(f"Found {len(terms)} vocabulary entries for '{term}'")
                return terms

        except Exception as e:
            logger.error(f"Vocabulary search error: {e}")
            raise


# Global instance
esbirka_client = ESbirkaAPIClient()
