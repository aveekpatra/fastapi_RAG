"""
LLM Service - Simplified
1. Generate search queries (fast model)
2. Check relevance (fast model)
3. Generate answer (main model)
"""
import asyncio
from typing import AsyncIterator, Optional, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain_openai import ChatOpenAI

from app.config import settings
from app.models import CaseResult


# =============================================================================
# PROMPTS - All in Czech, simple and direct
# =============================================================================

QUERY_PROMPT = """Vygeneruj 3 vyhledávací dotazy pro právní databázi českých soudních rozhodnutí.

PRAVIDLA:
- Použij českou právní terminologii
- Každý dotaz na nový řádek
- Bez číslování, bez vysvětlení
- Max 10 slov na dotaz

OTÁZKA: {question}

DOTAZY:"""


RELEVANCE_PROMPT = """Jsi právní asistent. Rozhodni, zda je rozhodnutí relevantní pro otázku.

OTÁZKA: {question}

ROZHODNUTÍ ({case_number}):
{text}

Odpověz POUZE "ANO" nebo "NE"."""


ANSWER_PROMPT = """Jsi český právní analytik. Odpověz na otázku na základě poskytnutých soudních rozhodnutí.

PRAVIDLA:
1. Odpověz PŘÍMO na otázku
2. Cituj DOSLOVNĚ z rozhodnutí ve formátu: > „citace" [číslo]
3. Vysvětli, co citace znamená
4. Pokud rozhodnutí neodpovídají na otázku, řekni: "Nemám odpověď na tuto otázku."
5. Piš česky, stručně, jasně

STRUKTURA:
1. Přímá odpověď (1-2 věty)
2. Právní analýza s citacemi
3. Závěr

OTÁZKA: {question}

ROZHODNUTÍ:
{context}

ODPOVĚĎ:"""


# =============================================================================
# LLM SERVICE
# =============================================================================

class LLMService:
    def __init__(self):
        self._main_model: Optional[ChatOpenAI] = None
        self._fast_model: Optional[ChatOpenAI] = None
    
    @property
    def main_model(self) -> ChatOpenAI:
        """Main model for answers"""
        if self._main_model is None:
            self._main_model = ChatOpenAI(
                model=settings.LLM_MODEL,
                api_key=settings.OPENROUTER_API_KEY,
                base_url=settings.OPENROUTER_BASE_URL,
                temperature=0.2,
                max_tokens=settings.LLM_MAX_TOKENS,
                timeout=settings.LLM_TIMEOUT,
            )
        return self._main_model
    
    @property
    def fast_model(self) -> ChatOpenAI:
        """Fast model for queries and relevance"""
        if self._fast_model is None:
            self._fast_model = ChatOpenAI(
                model=settings.FAST_MODEL,
                api_key=settings.OPENROUTER_API_KEY,
                base_url=settings.OPENROUTER_BASE_URL,
                temperature=0.3,
                max_tokens=1000,
                timeout=60.0,
            )
        return self._fast_model
    
    async def generate_search_queries(self, question: str, num_queries: int = 3) -> List[str]:
        """Generate search queries from user question"""
        try:
            prompt = ChatPromptTemplate.from_messages([
                HumanMessagePromptTemplate.from_template(QUERY_PROMPT)
            ])
            chain = prompt | self.fast_model | StrOutputParser()
            
            result = await chain.ainvoke({"question": question})
            
            # Parse queries
            queries = [q.strip() for q in result.split("\n") if q.strip() and len(q.strip()) > 5]
            
            # Always include original question
            final = [question] + [q for q in queries if q.lower() != question.lower()]
            
            print(f"✅ Generated {len(final)} queries")
            return final[:num_queries + 1]
            
        except Exception as e:
            print(f"⚠️ Query generation failed: {e}")
            return [question]
    
    async def check_relevance(self, question: str, case: CaseResult) -> bool:
        """Quick relevance check with fast model"""
        try:
            # Use first 2000 chars of text
            text = (case.subject or "")[:2000]
            if not text:
                return False
            
            prompt = RELEVANCE_PROMPT.format(
                question=question,
                case_number=case.case_number,
                text=text
            )
            
            response = await self.fast_model.ainvoke(prompt)
            answer = response.content.strip().upper()
            
            return "ANO" in answer
            
        except Exception as e:
            print(f"⚠️ Relevance check failed: {e}")
            return True  # Include on error
    
    async def filter_relevant_cases(
        self, question: str, cases: List[CaseResult], max_cases: int = 5
    ) -> List[CaseResult]:
        """Filter cases by relevance using fast model"""
        if not cases:
            return []
        
        print(f"🔍 Checking relevance of {len(cases)} cases...")
        
        # Check relevance in parallel
        tasks = [self.check_relevance(question, case) for case in cases[:10]]
        results = await asyncio.gather(*tasks)
        
        relevant = [case for case, is_relevant in zip(cases[:10], results) if is_relevant]
        
        print(f"✅ Found {len(relevant)} relevant cases")
        return relevant[:max_cases]
    
    def _format_cases_for_context(self, cases: List[CaseResult]) -> str:
        """Format cases for LLM context"""
        parts = []
        for i, case in enumerate(cases, 1):
            text = case.subject or "Text není k dispozici."
            # Limit text length
            if len(text) > 8000:
                text = text[:8000] + "..."
            
            parts.append(f"""
[{i}] {case.case_number}
Soud: {case.court}
Datum: {case.date_issued or "N/A"}

{text}
""")
        return "\n---\n".join(parts)
    
    async def answer_based_on_cases(self, question: str, cases: List[CaseResult]) -> str:
        """Generate answer based on cases"""
        if not cases:
            return "Nemám odpověď na tuto otázku. V databázi jsem nenašel relevantní soudní rozhodnutí."
        
        try:
            context = self._format_cases_for_context(cases)
            
            prompt = ChatPromptTemplate.from_messages([
                HumanMessagePromptTemplate.from_template(ANSWER_PROMPT)
            ])
            chain = prompt | self.main_model | StrOutputParser()
            
            answer = await chain.ainvoke({
                "question": question,
                "context": context
            })
            
            return answer
            
        except Exception as e:
            print(f"⚠️ Answer generation failed: {e}")
            return "Došlo k chybě při generování odpovědi. Zkuste to prosím znovu."
    
    async def answer_based_on_cases_stream(
        self, question: str, cases: List[CaseResult]
    ) -> AsyncIterator[str]:
        """Stream answer based on cases"""
        if not cases:
            yield "Nemám odpověď na tuto otázku. V databázi jsem nenašel relevantní soudní rozhodnutí."
            return
        
        try:
            context = self._format_cases_for_context(cases)
            
            prompt = ChatPromptTemplate.from_messages([
                HumanMessagePromptTemplate.from_template(ANSWER_PROMPT)
            ])
            chain = prompt | self.main_model | StrOutputParser()
            
            async for chunk in chain.astream({
                "question": question,
                "context": context
            }):
                if chunk:
                    yield chunk
                    
        except Exception as e:
            print(f"⚠️ Streaming failed: {e}")
            yield "Došlo k chybě při generování odpovědi."
    
    async def rerank_cases(self, query: str, cases: List[CaseResult]) -> List[CaseResult]:
        """Simple reranking - just return as-is for now"""
        return cases
    
    # Sonar for web search (keep for compatibility)
    async def get_sonar_answer(self, question: str) -> tuple[str, list[str]]:
        """Web search with Sonar"""
        try:
            sonar = ChatOpenAI(
                model="perplexity/sonar",
                api_key=settings.OPENROUTER_API_KEY,
                base_url=settings.OPENROUTER_BASE_URL,
                temperature=0.7,
                timeout=settings.LLM_TIMEOUT,
            )
            
            response = await sonar.ainvoke([
                SystemMessage(content="Jsi právní expert na české právo. Odpovídej česky."),
                HumanMessage(content=question)
            ])
            
            citations = []
            if hasattr(response, "response_metadata"):
                citations = response.response_metadata.get("citations", [])
            
            return response.content or "", citations
            
        except Exception as e:
            print(f"⚠️ Sonar error: {e}")
            return "", []
    
    async def get_sonar_answer_stream(self, question: str):
        """Stream Sonar answer"""
        try:
            sonar = ChatOpenAI(
                model="perplexity/sonar",
                api_key=settings.OPENROUTER_API_KEY,
                base_url=settings.OPENROUTER_BASE_URL,
                temperature=0.7,
            )
            
            messages = [
                SystemMessage(content="Jsi právní expert na české právo. Odpovídej česky."),
                HumanMessage(content=question)
            ]
            
            full_answer = ""
            async for chunk in sonar.astream(messages):
                if chunk.content:
                    full_answer += chunk.content
                    yield chunk.content, None, None
            
            yield None, full_answer, []
            
        except Exception as e:
            print(f"⚠️ Sonar stream error: {e}")
            yield None, "", []
    
    async def generate_summary_stream(
        self, question: str, web_answer: str, case_answer: str
    ) -> AsyncIterator[str]:
        """Generate summary"""
        try:
            prompt = f"""Shrň hlavní závěry v 2-3 větách česky:

OTÁZKA: {question}
WEB: {web_answer[:2000]}
JUDIKATURA: {case_answer[:2000]}

SHRNUTÍ:"""
            
            async for chunk in self.fast_model.astream(prompt):
                if chunk.content:
                    yield chunk.content
                    
        except Exception as e:
            print(f"⚠️ Summary error: {e}")


# Global instance
llm_service = LLMService()
