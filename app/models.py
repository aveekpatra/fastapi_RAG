from typing import Optional, Literal
from enum import Enum

from pydantic import BaseModel, Field


class DataSourceEnum(str, Enum):
    """Available data sources for legal search"""
    # Main 3 court collections (Seznam/retromae model)
    CONSTITUTIONAL_COURT = "constitutional_court"
    SUPREME_COURT = "supreme_court"
    SUPREME_ADMIN_COURT = "supreme_admin_court"
    # Search all 3 courts (default for explicit selection)
    ALL_COURTS = "all_courts"
    # Legacy collection (paraphrase-multilingual model)
    GENERAL_COURTS = "general_courts"


class QueryRequest(BaseModel):
    question: str
    top_k: int = 7
    source: DataSourceEnum = Field(
        default=DataSourceEnum.ALL_COURTS,
        description="Data source: constitutional_court, supreme_court, supreme_admin_court, all_courts, or general_courts (legacy)"
    )


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
    # New field to indicate source collection
    data_source: Optional[str] = None


class DataSourceInfo(BaseModel):
    """Information about a data source"""
    id: str
    name: str
    description: str
    collection: str
    embedding_model: str
    vector_size: int
    points_count: int
    status: str


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
