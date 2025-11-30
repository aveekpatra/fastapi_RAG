"""
LLM Service - Optimized for Quality
Focus: Better queries, better answers
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
# PROMPTS - Optimized for Czech legal search
# =============================================================================

QUERY_PROMPT = """Jsi expert na české právo. Vygeneruj 5-7 různých vyhledávacích dotazů pro právní databázi.

STRATEGIE:
1. Přímý dotaz - přesná formulace otázky
2. Právní terminologie - použij odborné termíny
3. Synonyma - různé způsoby vyjádření
4. Specifické aspekty - rozděl na dílčí otázky
5. Obecnější dotaz - širší kontext
6. Konkrétnější dotaz - specifické detaily

PRAVIDLA:
- Každý dotaz na nový řádek
- Bez číslování
- Max 15 slov na dotaz
- Použij českou právní terminologii
- Různé úhly pohledu

PŘÍKLAD pro "náhrada škody při dopravní nehodě":
náhrada škody dopravní nehoda
odškodnění újma na zdraví autonehoda
bolestné ztížení společenského uplatnění
odpovědnost za škodu provoz vozidla
pojistné plnění povinné ručení
regres pojišťovny viník nehody

OTÁZKA: {question}

DOTAZY:"""


ANSWER_PROMPT = """Jsi zkušený český právní analytik. Odpověz na otázku na základě soudních rozhodnutí.

KRITICKÁ PRAVIDLA:
1. Odpověz PŘÍMO na otázku - první věta musí být jasná odpověď
2. Cituj DOSLOVNĚ z rozhodnutí: > „přesná citace" [číslo]
3. Vysvětli, co citace znamená a proč je důležitá
4. Pokud rozhodnutí NEODPOVÍDAJÍ na otázku, řekni: "Nemám odpověď na tuto otázku."
5. NECITUJ rozhodnutí, která nejsou relevantní!

STRUKTURA:
1. **Odpověď:** (1-2 věty, jasně)
2. **Analýza:** (citace s vysvětlením)
3. **Závěr:** (praktické shrnutí)

FORMÁT CITACE:
> „přesná citace z textu rozhodnutí" [1]

To znamená, že... (vysvětlení)

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
        if self._main_model is None:
            self._main_model = ChatOpenAI(
                model=settings.LLM_MODEL,
                api_key=settings.OPENROUTER_API_KEY,
                base_url=settings.OPENROUTER_BASE_URL,
                temperature=0.1,  # Lower for more focused answers
                max_tokens=settings.LLM_MAX_TOKENS,
                timeout=settings.LLM_TIMEOUT,
            )
        return self._main_model
    
    @property
    def fast_model(self) -> ChatOpenAI:
        if self._fast_model is None:
            self._fast_model = ChatOpenAI(
                model=settings.FAST_MODEL,
                api_key=settings.OPENROUTER_API_KEY,
                base_url=settings.OPENROUTER_BASE_URL,
                temperature=0.5,  # More creative for query generation
                max_tokens=2000,
                timeout=60.0,
            )
        return self._fast_model
    
    async def generate_search_queries(self, question: str, num_queries: int = 7) -> List[str]:
        """Generate multiple search queries for better recall"""
        try:
            prompt = ChatPromptTemplate.from_messages([
                HumanMessagePromptTemplate.from_template(QUERY_PROMPT)
            ])
            chain = prompt | self.fast_model | StrOutputParser()
            
            result = await chain.ainvoke({"question": question})
            
            # Parse queries - be more lenient
            queries = []
            for line in result.split("\n"):
                line = line.strip()
                # Skip empty lines and lines that look like instructions
                if not line or len(line) < 5:
                    continue
                if line.startswith(("-", "*", "•", "1.", "2.", "3.")):
                    line = line.lstrip("-*•0123456789. ")
                if len(line) >= 5:
                    queries.append(line)
            
            # Always include original question first
            final = [question]
            for q in queries:
                if q.lower() != question.lower() and q not in final:
                    final.append(q)
            
            print(f"✅ Generated {len(final)} queries:")
            for q in final[:5]:
                print(f"   • {q[:60]}...")
            
            return final[:num_queries]
            
        except Exception as e:
            print(f"⚠️ Query generation failed: {e}")
            return [question]
    
    def _format_cases_for_context(self, cases: List[CaseResult]) -> str:
        """Format cases for LLM - include ALL available text with clear truncation"""
        parts = []
        total_chars = 0
        max_total_chars = 100000  # ~25k tokens, safe for most models
        max_per_case = 15000  # ~3.7k tokens per case
        
        for i, case in enumerate(cases, 1):
            text = case.subject or ""
            original_length = len(text)
            
            if not text:
                text = "[Text rozhodnutí není k dispozici]"
            
            # Truncate if needed with clear marker
            truncated = False
            if len(text) > max_per_case:
                text = text[:max_per_case]
                truncated = True
            
            # Check total context size
            if total_chars + len(text) > max_total_chars:
                remaining = max_total_chars - total_chars
                if remaining > 1000:
                    text = text[:remaining]
                    truncated = True
                else:
                    # Add note that more cases were skipped
                    parts.append(f"\n[Dalších {len(cases) - i + 1} rozhodnutí vynecháno kvůli limitu kontextu]")
                    break
            
            truncation_note = ""
            if truncated:
                truncation_note = f"\n[⚠️ Text zkrácen z {original_length:,} na {len(text):,} znaků]"
            
            parts.append(f"""
{'═'*80}
[{i}] {case.case_number}
Soud: {case.court}
Datum: {case.date_issued or "N/A"}
Relevance skóre: {case.relevance_score:.3f}
Délka textu: {len(text):,} znaků{truncation_note}
{'═'*80}

{text}
""")
            total_chars += len(text)
        
        result = "\n".join(parts)
        print(f"   📄 Context: {len(result):,} chars, {len(cases)} cases")
        return result
    
    async def answer_based_on_cases(self, question: str, cases: List[CaseResult]) -> str:
        """Generate answer - let LLM decide what's relevant"""
        if not cases:
            return "Nemám odpověď na tuto otázku. V databázi jsem nenašel žádná soudní rozhodnutí."
        
        try:
            context = self._format_cases_for_context(cases)
            
            print(f"📤 Sending {len(cases)} cases to LLM")
            print(f"   Context: {len(context):,} chars")
            
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
            return "Došlo k chybě při generování odpovědi."
    
    async def answer_based_on_cases_stream(
        self, question: str, cases: List[CaseResult]
    ) -> AsyncIterator[str]:
        """Stream answer"""
        if not cases:
            yield "Nemám odpověď na tuto otázku. V databázi jsem nenašel žádná soudní rozhodnutí."
            return
        
        try:
            context = self._format_cases_for_context(cases)
            
            print(f"📤 Streaming {len(cases)} cases")
            print(f"   Context: {len(context):,} chars")
            
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
    
    # Skip relevance filtering - cross-encoder handles this now
    async def filter_relevant_cases(
        self, question: str, cases: List[CaseResult], max_cases: int = 10
    ) -> List[CaseResult]:
        """Just return cases - cross-encoder already filtered"""
        return cases[:max_cases]
    
    async def rerank_cases(self, query: str, cases: List[CaseResult]) -> List[CaseResult]:
        """Reranking is now done by cross-encoder in search"""
        return cases
    
    # Sonar for web search
    async def get_sonar_answer(self, question: str) -> tuple[str, list[str]]:
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
