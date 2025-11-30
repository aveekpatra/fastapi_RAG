"""
Legal Entity Extractor - Extract legal entities from Czech legal queries

Extracts:
- Case numbers: "21 Cdo 1234/2020", "sp. zn. I. ÚS 123/20", "Pl. ÚS 1/2020"
- Statute references: "§ 2048", "§ 123 odst. 1", "§ 2048 občanského zákoníku"
- Court hints: "Ústavní soud", "Nejvyšší soud", "NSS"

This module is designed to be fail-safe - if extraction fails, it returns
empty entities and the search continues normally without boosting.
"""
import re
from typing import List, Optional, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from app.models import CaseResult


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ExtractedEntities:
    """Extracted legal entities from user query"""
    case_numbers: List[str] = field(default_factory=list)
    statute_references: List[str] = field(default_factory=list)
    court_hints: List[str] = field(default_factory=list)
    preferred_source: Optional[str] = None
    
    def has_entities(self) -> bool:
        """Check if any entities were extracted"""
        return bool(self.case_numbers or self.statute_references or self.court_hints)
    
    def __str__(self) -> str:
        parts = []
        if self.case_numbers:
            parts.append(f"cases={self.case_numbers}")
        if self.statute_references:
            parts.append(f"statutes={self.statute_references}")
        if self.court_hints:
            parts.append(f"courts={self.court_hints}")
        if self.preferred_source:
            parts.append(f"source={self.preferred_source}")
        return f"Entities({', '.join(parts)})" if parts else "Entities(none)"


# =============================================================================
# LEGAL ENTITY EXTRACTOR
# =============================================================================

class LegalEntityExtractor:
    """
    Extract legal entities from Czech legal queries.
    
    All methods are fail-safe - they catch exceptions and return
    safe defaults to ensure the search pipeline continues.
    """

    # Case number patterns for Czech courts
    CASE_NUMBER_PATTERNS = [
        # Supreme Court: "21 Cdo 1234/2020", "29 ICdo 123/2019"
        r'\b(\d{1,2}\s*(?:Cdo|ICdo|Odo|Tdo|Ncu|NSČR)\s*\d+/\d{4})\b',
        # Constitutional Court: "I. ÚS 123/20", "Pl. ÚS 1/2020", "IV.ÚS 123/20"
        r'\b((?:I{1,3}|IV|Pl)\.?\s*ÚS\s*\d+/\d{2,4})\b',
        # Supreme Administrative Court: "1 As 123/2020", "2 Afs 45/2019"
        r'\b(\d{1,2}\s*(?:As|Afs|Ads|Ans|Ars|Azs)\s*\d+/\d{4})\b',
        # General pattern with "sp. zn."
        r'sp\.?\s*zn\.?\s*([A-Za-z0-9\s\.]+/\d{4})',
        # General court case: "5 C 410/2024"
        r'\b(\d{1,2}\s*[A-Z]{1,3}\s*\d+/\d{4})\b',
    ]
    
    # Statute reference patterns
    STATUTE_PATTERNS = [
        # "§ 2048" or "§2048"
        r'§\s*(\d+)',
        # "§ 123 odst. 1 písm. a)"
        r'§\s*(\d+)\s*(?:odst\.?\s*\d+)?(?:\s*písm\.?\s*[a-z]\))?',
        # Law references: "z. č. 89/2012 Sb."
        r'z\.?\s*č\.?\s*(\d+/\d{4})\s*Sb\.?',
        # "občanského zákoníku", "trestního zákoníku"
        r'(občansk\w+\s+zákoník\w*|trestn\w+\s+zákoník\w*|zákoník\w*\s+práce)',
    ]
    
    # Court name patterns and their DataSource mappings
    COURT_PATTERNS = {
        # Constitutional Court
        r'ústavní\w*\s+soud\w*|ÚS\b': 'constitutional_court',
        # Supreme Court
        r'nejvyšší\w*\s+soud\w*(?!\s+správní)|NS\b(?!\s*S)': 'supreme_court',
        # Supreme Administrative Court
        r'nejvyšší\w*\s+správní\w*\s+soud\w*|NSS\b': 'supreme_admin_court',
        # General/District courts
        r'okresní\w*\s+soud\w*|krajský\w*\s+soud\w*|obecn\w+\s+soud\w*': 'general_courts',
    }
    
    # Boost multipliers
    CASE_NUMBER_BOOST = 5.0    # Exact case number match
    STATUTE_BOOST = 1.5        # Statute reference match
    COURT_BOOST = 1.2          # Court type match
    
    def extract(self, query: str) -> ExtractedEntities:
        """
        Extract all legal entities from query.
        
        Args:
            query: User's search query
            
        Returns:
            ExtractedEntities with any found entities, or empty entities on error
        """
        entities = ExtractedEntities()
        
        if not query or not isinstance(query, str):
            return entities
        
        try:
            # Extract case numbers
            entities.case_numbers = self._extract_case_numbers(query)
            
            # Extract statute references
            entities.statute_references = self._extract_statutes(query)
            
            # Extract court hints
            entities.court_hints, entities.preferred_source = self._extract_courts(query)
            
        except Exception as e:
            # Log but don't fail - return whatever we have
            print(f"⚠️ Entity extraction error (non-fatal): {e}")
        
        return entities
    
    def _extract_case_numbers(self, query: str) -> List[str]:
        """Extract case numbers from query"""
        case_numbers = []
        
        try:
            for pattern in self.CASE_NUMBER_PATTERNS:
                try:
                    matches = re.findall(pattern, query, re.IGNORECASE)
                    for match in matches:
                        # Normalize: remove extra spaces
                        normalized = re.sub(r'\s+', ' ', match.strip())
                        if normalized and normalized not in case_numbers:
                            case_numbers.append(normalized)
                except re.error:
                    # Skip invalid pattern
                    continue
        except Exception:
            pass
        
        return case_numbers
    
    def _extract_statutes(self, query: str) -> List[str]:
        """Extract statute references from query"""
        statutes = []
        
        try:
            for pattern in self.STATUTE_PATTERNS:
                try:
                    matches = re.findall(pattern, query, re.IGNORECASE)
                    for match in matches:
                        if match and match not in statutes:
                            statutes.append(match)
                except re.error:
                    continue
        except Exception:
            pass
        
        return statutes
    
    def _extract_courts(self, query: str) -> tuple[List[str], Optional[str]]:
        """Extract court hints and determine preferred source"""
        court_hints = []
        preferred_source = None
        
        try:
            query_lower = query.lower()
            for pattern, source in self.COURT_PATTERNS.items():
                try:
                    if re.search(pattern, query_lower):
                        if source not in court_hints:
                            court_hints.append(source)
                        # Set preferred source (first match wins)
                        if preferred_source is None:
                            preferred_source = source
                except re.error:
                    continue
        except Exception:
            pass
        
        return court_hints, preferred_source

    
    def get_boost_score(self, case: "CaseResult", entities: ExtractedEntities) -> float:
        """
        Calculate boost score for a case based on extracted entities.
        
        Args:
            case: CaseResult to evaluate
            entities: Extracted entities from query
            
        Returns:
            Multiplier (1.0 = no boost, >1.0 = boosted)
            Always returns 1.0 on error to avoid breaking search
        """
        if not entities.has_entities():
            return 1.0
        
        boost = 1.0
        
        try:
            # Exact case number match - HUGE boost
            boost *= self._get_case_number_boost(case, entities)
            
            # Statute reference match - significant boost
            boost *= self._get_statute_boost(case, entities)
            
            # Court match - moderate boost
            boost *= self._get_court_boost(case, entities)
            
        except Exception as e:
            # On any error, return no boost
            print(f"⚠️ Boost calculation error (non-fatal): {e}")
            return 1.0
        
        return boost
    
    def _get_case_number_boost(self, case: "CaseResult", entities: ExtractedEntities) -> float:
        """Calculate boost for case number matches"""
        if not entities.case_numbers:
            return 1.0
        
        try:
            case_num = case.case_number if case.case_number else ""
            case_num_normalized = case_num.lower().replace(" ", "")
            
            for entity_case in entities.case_numbers:
                entity_normalized = entity_case.lower().replace(" ", "")
                if entity_normalized in case_num_normalized or case_num_normalized in entity_normalized:
                    print(f"   🎯 Exact case match: {case.case_number} → {self.CASE_NUMBER_BOOST}x boost")
                    return self.CASE_NUMBER_BOOST
        except Exception:
            pass
        
        return 1.0
    
    def _get_statute_boost(self, case: "CaseResult", entities: ExtractedEntities) -> float:
        """Calculate boost for statute reference matches"""
        if not entities.statute_references:
            return 1.0
        
        try:
            legal_refs = case.legal_references if case.legal_references else []
            if not legal_refs:
                return 1.0
            
            case_refs = " ".join(str(ref) for ref in legal_refs).lower()
            
            for statute in entities.statute_references:
                if str(statute).lower() in case_refs:
                    print(f"   📜 Statute match: § {statute} in {case.case_number} → {self.STATUTE_BOOST}x boost")
                    return self.STATUTE_BOOST
        except Exception:
            pass
        
        return 1.0
    
    def _get_court_boost(self, case: "CaseResult", entities: ExtractedEntities) -> float:
        """Calculate boost for court type matches"""
        if not entities.court_hints:
            return 1.0
        
        try:
            case_source = (case.data_source or "").lower()
            
            for court_hint in entities.court_hints:
                if court_hint.lower() in case_source:
                    return self.COURT_BOOST
        except Exception:
            pass
        
        return 1.0


# =============================================================================
# SAFE WRAPPER FUNCTIONS
# =============================================================================

# Global instance
_extractor: Optional[LegalEntityExtractor] = None


def get_extractor() -> LegalEntityExtractor:
    """Get or create the global extractor instance"""
    global _extractor
    if _extractor is None:
        _extractor = LegalEntityExtractor()
    return _extractor


def extract_entities(query: str) -> ExtractedEntities:
    """
    Safe wrapper to extract entities from query.
    
    Returns empty ExtractedEntities on any error.
    """
    try:
        return get_extractor().extract(query)
    except Exception as e:
        print(f"⚠️ Entity extraction failed (non-fatal): {e}")
        return ExtractedEntities()


def calculate_boost(case: "CaseResult", entities: ExtractedEntities) -> float:
    """
    Safe wrapper to calculate boost score.
    
    Returns 1.0 (no boost) on any error.
    """
    try:
        return get_extractor().get_boost_score(case, entities)
    except Exception as e:
        print(f"⚠️ Boost calculation failed (non-fatal): {e}")
        return 1.0


def build_keyword_filters(entities: ExtractedEntities) -> List[dict]:
    """
    Build Qdrant filter conditions for keyword search based on extracted entities.
    
    Returns a list of filter conditions that can be used with Qdrant's scroll/search.
    Returns empty list on error (search continues without filters).
    
    Filter types:
    - case_number: exact match on case_number field
    - legal_references: text match on legal_references array (for statutes)
    """
    filters = []
    
    try:
        # Case number filters - exact match
        for case_num in entities.case_numbers:
            if case_num:
                filters.append({
                    "type": "case_number",
                    "field": "case_number",
                    "value": case_num,
                    "condition": {
                        "key": "case_number",
                        "match": {"text": case_num}
                    }
                })
        
        # Statute reference filters - search in legal_references array
        for statute in entities.statute_references:
            if statute:
                # Format statute for search (e.g., "2048" -> "§ 2048")
                statute_str = str(statute)
                # Search for the statute number in legal_references
                filters.append({
                    "type": "statute",
                    "field": "legal_references",
                    "value": statute_str,
                    "condition": {
                        "key": "legal_references",
                        "match": {"text": statute_str}
                    }
                })
                # Also try with § prefix
                if not statute_str.startswith("§"):
                    filters.append({
                        "type": "statute",
                        "field": "legal_references", 
                        "value": f"§ {statute_str}",
                        "condition": {
                            "key": "legal_references",
                            "match": {"text": f"§ {statute_str}"}
                        }
                    })
    
    except Exception as e:
        print(f"⚠️ Filter building failed (non-fatal): {e}")
        return []
    
    return filters


def has_searchable_entities(entities: ExtractedEntities) -> bool:
    """
    Check if entities contain searchable keywords (case numbers or statutes).
    Court hints alone don't warrant a keyword search.
    """
    try:
        return bool(entities.case_numbers or entities.statute_references)
    except Exception:
        return False
