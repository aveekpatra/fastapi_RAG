from typing import Optional

from pydantic import BaseModel


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


# Response model for web search (Sonar only)
class WebSearchResponse(BaseModel):
    answer: str
    source: str
    citations: list[str] = []


# Response model for case search (Qdrant + GPT)
class CaseSearchResponse(BaseModel):
    answer: str
    supporting_cases: list[CaseResult]


# Response model for combined search (Sonar + Qdrant + GPT)
class CombinedSearchResponse(BaseModel):
    web_answer: str
    web_source: str
    web_citations: list[str] = []
    case_answer: str
    supporting_cases: list[CaseResult]


# Keep the old model for backward compatibility (though endpoints will be removed)
class LegalQueryResponse(BaseModel):
    sonar_answer: str
    sonar_source: str
    sonar_citations: list[str] = []
    case_based_answer: str
    supporting_cases: list[CaseResult]
