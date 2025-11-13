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


class LegalQueryResponse(BaseModel):
    sonar_answer: str
    sonar_source: str
    sonar_citations: list[str] = []
    case_based_answer: str
    supporting_cases: list[CaseResult]