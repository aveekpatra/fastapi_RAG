"""
e-Sbírka REST API Client
Production client for Czech legal database search using official e-Sbírka API
API Documentation: https://api.e-sbirka.cz
"""
import httpx
import re
from urllib.parse import quote
from typing import Optional, List, Dict
import logging

from app.config import settings

logger = logging.getLogger(__name__)

# Official e-Sbírka API base URL
ESBIRKA_API_BASE = "https://api.e-sbirka.cz"


class ESbirkaAPIClient:
    """Official e-Sbírka REST API client"""

    def __init__(self):
        self.api_key = settings.ESBIRKA_API_KEY
        self.base_url = ESBIRKA_API_BASE
        self.timeout = 60.0
        
        logger.info(f"e-Sbírka client initialized")
        logger.info(f"  Base URL: {self.base_url}")
        logger.info(f"  API Key configured: {'Yes' if self.api_key else 'No'}")

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with official e-Sbírka auth header"""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "LexioChat/1.0",
        }
        if self.api_key:
            # Official e-Sbírka uses esel-api-access-key header
            headers["esel-api-access-key"] = self.api_key
        return headers

    def _strip_html(self, text: str) -> str:
        """Remove HTML tags from text"""
        if not text:
            return ""
        return re.sub(r'<[^>]+>', '', text)

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
        Search laws using official e-Sbírka API.
        
        Uses POST /jednoducha-vyhledavani endpoint.
        
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
        url = f"{self.base_url}/jednoducha-vyhledavani"
        
        # Build request payload for simple search
        payload = {
            "fulltext": query,
            "maxPocet": min(limit, 100)
        }

        logger.info(f"[e-Sbírka] Search request:")
        logger.info(f"  URL: {url}")
        logger.info(f"  Payload: {payload}")
        logger.info(f"  API Key: {'***' if self.api_key else 'None'}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
                response = await client.post(
                    url, 
                    json=payload, 
                    headers=self._get_headers()
                )
                
                logger.info(f"[e-Sbírka] Response status: {response.status_code}")
                
                if response.status_code == 401:
                    logger.error(f"[e-Sbírka] 401 Unauthorized - Invalid API key")
                    logger.error(f"[e-Sbírka] Response: {response.text[:500]}")
                    raise Exception("Invalid API key - check ESBIRKA_API_KEY")
                
                if response.status_code == 403:
                    logger.error(f"[e-Sbírka] 403 Forbidden - Access denied")
                    raise Exception("Access forbidden - check API permissions")
                
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After", "60")
                    logger.error(f"[e-Sbírka] 429 Rate limited")
                    raise Exception(f"Rate limited. Retry after {retry_after} seconds")
                
                if response.status_code >= 400:
                    logger.error(f"[e-Sbírka] Error {response.status_code}")
                    logger.error(f"[e-Sbírka] Response: {response.text[:500]}")
                    raise Exception(f"API error: {response.status_code}")
                
                data = response.json()
                raw_results = data.get("seznam", [])
                total_count = data.get("pocetCelkem", 0)
                
                logger.info(f"[e-Sbírka] Success - {len(raw_results)} results (total: {total_count})")
                
                # Transform to standardized format
                results = []
                for doc in raw_results:
                    stale_url = doc.get("staleUrl", "")
                    citation = doc.get("kodDokumentuSbirky", "")
                    title = doc.get("nazev", "")
                    status = doc.get("stavDokumentuSbirky", "")
                    date = doc.get("datum", "")
                    
                    # Apply filters if specified
                    if legal_act_type:
                        if legal_act_type.lower() not in title.lower() and legal_act_type.lower() not in citation.lower():
                            continue
                    
                    if year_from or year_to:
                        # Extract year from citation (e.g., "262/2006 Sb." -> 2006)
                        year_match = re.search(r'/(\d{4})', citation)
                        if year_match:
                            year = int(year_match.group(1))
                            if year_from and year < year_from:
                                continue
                            if year_to and year > year_to:
                                continue
                    
                    results.append({
                        "iri": stale_url,
                        "citation": citation,
                        "citace": citation,
                        "title": title,
                        "nazev": title,
                        "type": self._detect_law_type(title, citation),
                        "typ": self._detect_law_type(title, citation),
                        "status": status,
                        "effective_from": date,
                        "verze_od": date,
                        "staleUrl": stale_url,
                    })
                
                if results:
                    logger.info(f"[e-Sbírka] First result: {results[0].get('citation')} - {results[0].get('title')[:50]}")
                
                return results

        except httpx.TimeoutException:
            logger.error(f"[e-Sbírka] Timeout after {self.timeout}s")
            raise Exception(f"Request timeout after {self.timeout}s")
        except httpx.RequestError as e:
            logger.error(f"[e-Sbírka] Request error: {e}")
            raise Exception(f"Request error: {e}")

    def _detect_law_type(self, title: str, citation: str) -> str:
        """Detect law type from title and citation"""
        title_lower = title.lower()
        if "zákon" in title_lower or "zákoník" in title_lower:
            return "Zákon"
        elif "nařízení" in title_lower:
            return "Nařízení"
        elif "vyhláška" in title_lower:
            return "Vyhláška"
        elif "sdělení" in title_lower:
            return "Sdělení"
        elif "usnesení" in title_lower:
            return "Usnesení"
        elif "Sb. m. s." in citation:
            return "Mezinárodní smlouva"
        return "Právní předpis"

    async def get_law(self, stale_url: str, version_date: Optional[str] = None) -> Dict:
        """
        Retrieve specific legal act details.
        
        Uses GET /dokumenty-sbirky/{staleUrl} endpoint.
        """
        # URL encode the staleUrl (replace / with %2F)
        encoded_url = quote(stale_url, safe='')
        url = f"{self.base_url}/dokumenty-sbirky/{encoded_url}"

        logger.info(f"[e-Sbírka] Get law: {url}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
                response = await client.get(url, headers=self._get_headers())
                
                if response.status_code != 200:
                    logger.error(f"[e-Sbírka] Get law error: {response.status_code}")
                    raise Exception(f"Law not found: {stale_url}")
                
                data = response.json()
                
                return {
                    "iri": stale_url,
                    "citation": data.get("kodDokumentuSbirky", ""),
                    "title": data.get("nazev", ""),
                    "description": data.get("popis", ""),
                    "type": data.get("typZneni", ""),
                    "effective_from": data.get("datumUcinnostiZneniOd", ""),
                    "effective_to": data.get("datumUcinnostiZneniDo", ""),
                    "status": data.get("stavDokumentuSbirky", ""),
                    "full_citation": data.get("uplnaCitace", ""),
                    "short_citation": data.get("zkracenaCitace", ""),
                    "amendments": data.get("novely", []),
                    "raw": data,
                }

        except Exception as e:
            logger.error(f"[e-Sbírka] Error fetching law {stale_url}: {e}")
            raise

    async def get_law_fragments(self, stale_url: str, page: int = 1) -> List[Dict]:
        """
        Get sections/articles of a legal act.
        
        Uses GET /dokumenty-sbirky/{staleUrl}/fragmenty endpoint.
        """
        encoded_url = quote(stale_url, safe='')
        url = f"{self.base_url}/dokumenty-sbirky/{encoded_url}/fragmenty"
        params = {"cisloStranky": page}

        logger.info(f"[e-Sbírka] Get fragments: {url}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
                response = await client.get(
                    url, 
                    params=params,
                    headers=self._get_headers()
                )
                
                if response.status_code != 200:
                    logger.error(f"[e-Sbírka] Get fragments error: {response.status_code}")
                    return []
                
                data = response.json()
                raw_fragments = data.get("seznam", [])
                total_pages = data.get("pocetStranek", 1)
                
                # Transform fragments
                fragments = []
                for frag in raw_fragments:
                    fragments.append({
                        "id": frag.get("id"),
                        "full_citation": frag.get("uplnaCitace", ""),
                        "short_citation": frag.get("zkracenaCitace", ""),
                        "text": self._strip_html(frag.get("xhtml", "")),
                        "html": frag.get("xhtml", ""),
                        "is_effective": frag.get("jeUcinny", True),
                    })
                
                logger.info(f"[e-Sbírka] Got {len(fragments)} fragments (page {page}/{total_pages})")
                return fragments

        except Exception as e:
            logger.error(f"[e-Sbírka] Error fetching fragments: {e}")
            return []

    async def get_law_full_text(self, stale_url: str) -> Dict:
        """
        Get complete law with all fragments assembled.
        
        Fetches law details and all fragments, assembles full text.
        """
        logger.info(f"[e-Sbírka] Getting full text for: {stale_url}")
        
        try:
            # Get law details
            law_data = await self.get_law(stale_url)
            
            # Get fragments (first page)
            fragments = await self.get_law_fragments(stale_url, page=1)
            
            # Assemble full text
            full_text = ""
            for frag in fragments:
                citation = frag.get("full_citation", "")
                text = frag.get("text", "")
                if citation:
                    full_text += f"\n{citation}\n"
                if text:
                    full_text += f"{text}\n"
            
            law_data["full_text"] = full_text.strip()
            law_data["fragments"] = fragments
            law_data["fragment_count"] = len(fragments)
            
            return law_data
            
        except Exception as e:
            logger.error(f"[e-Sbírka] Error getting full text: {e}")
            raise

    async def get_law_history(self, stale_url: str) -> Dict:
        """
        Get version history of a law.
        
        Uses GET /dokumenty-sbirky/{staleUrl}/historie endpoint.
        """
        encoded_url = quote(stale_url, safe='')
        url = f"{self.base_url}/dokumenty-sbirky/{encoded_url}/historie"

        logger.info(f"[e-Sbírka] Get history: {url}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
                response = await client.get(url, headers=self._get_headers())
                
                if response.status_code != 200:
                    logger.error(f"[e-Sbírka] Get history error: {response.status_code}")
                    return {"versions": []}
                
                data = response.json()
                return {"versions": data.get("seznam", []), "raw": data}

        except Exception as e:
            logger.error(f"[e-Sbírka] Error fetching history: {e}")
            return {"versions": []}

    async def get_law_relationships(self, stale_url: str) -> Dict:
        """
        Get law relationships (amendments, derogations).
        
        Uses GET /dokumenty-sbirky/{staleUrl}/souvislosti endpoint.
        """
        encoded_url = quote(stale_url, safe='')
        url = f"{self.base_url}/dokumenty-sbirky/{encoded_url}/souvislosti"

        logger.info(f"[e-Sbírka] Get relationships: {url}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
                response = await client.get(url, headers=self._get_headers())
                
                if response.status_code != 200:
                    logger.error(f"[e-Sbírka] Get relationships error: {response.status_code}")
                    return {"relationships": []}
                
                data = response.json()
                return {"relationships": data.get("seznam", []), "raw": data}

        except Exception as e:
            logger.error(f"[e-Sbírka] Error fetching relationships: {e}")
            return {"relationships": []}


# Global instance
esbirka_client = ESbirkaAPIClient()
