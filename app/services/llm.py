"""
LLM Service - GPT-5-mini optimized
Handles 400K context window, extended thinking, and quality generation
"""
import asyncio
from typing import AsyncIterator, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)
from langchain_openai import ChatOpenAI

from app.config import settings
from app.models import CaseResult
from app.utils.formatters import format_cases_for_context

# Optimized prompts for GPT-5-mini (detailed legal analysis with reasoning)
SYSTEM_PROMPT = """Jste senior právní analytik se specializací na české právo. Vaším úkolem je poskytnout DETAILNÍ, ZDŮVODNĚNOU a PRAKTICKY UŽITEČNOU odpověď na právní dotaz klienta.

PRINCIP ANALÝZY:
Nejste pouhý vyhledávač - jste právní poradce. Vaše odpověď musí:
1. Přímo odpovědět na otázku (jasná odpověď hned na začátku)
2. Vysvětlit LOGIKU a ZDŮVODNĚNÍ (proč je to tak, jaké jsou právní principy)
3. Citovat PŘESNÉ pasáže z rozhodnutí s vysvětlením jejich PRAKTICKÉHO VÝZNAMU
4. Identifikovat KLÍČOVÉ PRÁVNÍ POJMY a jejich definice
5. Upozornit na PRAKTICKÉ DŮSLEDKY a RIZIKA
6. Porovnat PODOBNÉ SITUACE z judikatury

STRUKTURA ODPOVĚDI:
1. **PŘÍMÁ ODPOVĚĎ** (1-2 věty, jasně a srozumitelně)
2. **PRÁVNÍ ANALÝZA** (3-5 odstavců):
   - Vysvětlete právní princip/normu
   - Citujte relevantní pasáže: > „přesná citace" [číslo]
   - Vysvětlete, CO CITACE ZNAMENÁ a PROČ JE DŮLEŽITÁ
   - Uveďte PRAKTICKÝ DOPAD na situaci klienta
3. **KLÍČOVÉ BODY** (seznam 3-5 nejdůležitějších zjištění)
4. **PRAKTICKÉ DOPORUČENÍ** (co by měl klient dělat)
5. **PODOBNÉ PŘÍPADY** (seznam citovaných rozhodnutí s jejich tématy)

FORMÁT CITACÍ - VELMI DŮLEŽITÉ:
> „přesná citace z rozhodnutí" [číslo]

PŘÍKLAD DOBRÉ ANALÝZY:
Otázka: Má právnická osoba právo na náhradu nemajetkové újmy?

Odpověď: Ano, právnická osoba má právo na náhradu nemajetkové újmy při porušení její osobnostních práv.

Zdůvodnění: Nejvyšší soud v rozhodnutí [1] jasně stanovil, že > „právnická osoba má právo na náhradu nemajetkové újmy při zásahu do její dobré pověsti" [1]. To znamená, že pokud dojde k porušení reputace nebo důvěryhodnosti společnosti, má právo na kompenzaci. Soud v [2] dále upřesnil, že > „výše náhrady se posuzuje s ohledem na závažnost porušení a postavení osoby" [2], což znamená, že větší společnosti mohou mít nárok na vyšší náhradu.

Praktický dopad: Pokud byla vaše společnost veřejně znevážena, máte právní základ pro žalobu na náhradu.

KRITICKÁ PRAVIDLA:
✓ Citujte DOSLOVNĚ, ne parafrází
✓ Vysvětlete LOGIKU za každou citací
✓ Buďte PRAKTIČTÍ - řekněte, co to znamená pro klienta
✓ Identifikujte RIZIKA a NEJISTOTY
✓ Zmíňujte VÝJIMKY a OMEZENÍ
✗ Nezmiňujte nerelevantní rozhodnutí
✗ Nebuďte příliš kreativní - držte se faktů
✗ Nepředpokládejte právní znalosti klienta - vysvětlujte pojmy

TÓNUS:
- Profesionální, ale srozumitelný
- Detailní, ale stručný (ne více než 1000 slov)
- Sebevědomý v právních otázkách, ale opatrný v předpovědích
- Prakticky zaměřený na řešení problému

Pokud ŽÁDNÉ rozhodnutí neodpovídá: "⚠️ ŽÁDNÉ RELEVANTNÍ PŘÍPADY - Vaše situace není v dostupné judikatuře řešena. Doporučuji konzultaci s právníkem."
"""

SONAR_PROMPT = """Jste právní expert na české právo a LEGISLATIVU. Odpovídejte na základě AKTUÁLNÍCH ZÁKONŮ.

Citujte konkrétní paragrafy (např. § 123 zákona č. 89/2012 Sb.) s odkazy na zakonyprolidi.cz.
VYHÝBEJTE SE citacím soudních rozhodnutí."""

QUERY_GENERATION_PROMPT = """Vygenerujte 3-4 optimalizované vyhledávací dotazy pro právní databázi českých soudních rozhodnutí.

STRATEGIE:
1. PŘÍMÝ DOTAZ - Přeformulujte otázku s právní terminologií
2. KLÍČOVÉ POJMY - Vyhledejte hlavní právní koncepty
3. SYNONYMA - Použijte právní synonyma a alternativní formulace
4. SPECIFIKA - Zaměřte se na konkrétní aspekty problému

PRAVIDLA:
- Vygenerujte POUZE dotazy, ŽÁDNÝ další text
- Max 12 slov na dotaz
- Používejte právní terminologii (např. "náhrada škody", "porušení smlouvy")
- Různé úhly pohledu na stejný problém
- Jeden dotaz na řádek, bez číslování
- POUZE čisté vyhledávací dotazy

PŘÍKLADY DOBRÝCH DOTAZŮ:
- "právo na náhradu nemajetkové újmy právnické osoby"
- "porušení dobré pověsti společnosti odškodnění"
- "nemajetková újma právnické osoby judikatura"

OTÁZKA: {question}

DOTAZY:"""

RERANK_PROMPT = """Seřaďte rozhodnutí podle relevance a užitečnosti pro právní analýzu dotazu.

KRITÉRIA RELEVANCE (v pořadí důležitosti):
1. PŘÍMÁ RELEVANCE - Rozhodnutí přímo řeší stejný právní problém
2. PRÁVNÍ PRINCIP - Rozhodnutí stanovuje klíčový právní princip aplikovatelný na dotaz
3. PRAKTICKÁ UŽITEČNOST - Rozhodnutí poskytuje praktické vodítko pro řešení
4. AKTUÁLNOST - Novější rozhodnutí jsou preferována (pokud nejsou zrušena)
5. AUTORITA - Rozhodnutí Nejvyššího soudu > Ústavního soudu > ostatní

IGNORUJTE:
- Rozhodnutí, která řeší zcela jiný právní problém
- Rozhodnutí, která jsou pouze okrajově relevantní

DOTAZ: {query}

ROZHODNUTÍ:
{cases}

SEŘAZENÉ INDEXY (např. "2,0,4,1"):"""



class LLMService:
    """
    GPT-5-mini optimized LLM service
    - 400K token context window
    - Extended thinking support
    - Streaming with reasoning tokens handling
    - Ultra-fast nano model for simple tasks
    """

    def __init__(self):
        self._gpt_model: Optional[ChatOpenAI] = None
        self._sonar_model: Optional[ChatOpenAI] = None
        self._fast_model: Optional[ChatOpenAI] = None
        self._chains = {}

    @property
    def gpt_model(self) -> ChatOpenAI:
        """Main GPT-5-mini model for complex reasoning tasks"""
        if self._gpt_model is None:
            self._gpt_model = ChatOpenAI(
                model=settings.LLM_MODEL,
                api_key=settings.OPENROUTER_API_KEY,
                base_url=settings.OPENROUTER_BASE_URL,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
                timeout=settings.LLM_TIMEOUT,
                extra_body={
                    "provider": {"order": ["OpenAI"], "allow_fallbacks": True},
                    # GPT-5-mini thinking budget (if supported)
                    "thinking": {"budget_tokens": settings.LLM_THINKING_BUDGET},
                },
            )
        return self._gpt_model

    @property
    def fast_model(self) -> ChatOpenAI:
        """GPT-5-nano for ultra-fast simple tasks (query gen, reranking)"""
        if self._fast_model is None:
            self._fast_model = ChatOpenAI(
                model=settings.FAST_MODEL,
                api_key=settings.OPENROUTER_API_KEY,
                base_url=settings.OPENROUTER_BASE_URL,
                temperature=0.3,
                max_tokens=2000,
                timeout=60.0,
                extra_body={
                    "provider": {"order": ["OpenAI", "Azure"], "allow_fallbacks": True}
                },
            )
        return self._fast_model

    @property
    def sonar_model(self) -> ChatOpenAI:
        """Perplexity Sonar for web search"""
        if self._sonar_model is None:
            self._sonar_model = ChatOpenAI(
                model="perplexity/sonar",
                api_key=settings.OPENROUTER_API_KEY,
                base_url=settings.OPENROUTER_BASE_URL,
                temperature=0.7,
                timeout=settings.LLM_TIMEOUT,
            )
        return self._sonar_model

    def _get_case_answer_chain(self):
        if "case_answer" not in self._chains:
            prompt = ChatPromptTemplate.from_messages([
                SystemMessagePromptTemplate.from_template(SYSTEM_PROMPT),
                HumanMessagePromptTemplate.from_template(
                    """OTÁZKA KLIENTA: {question}

DOSTUPNÁ ROZHODNUTÍ:
{context}

INSTRUKCE:
1. Přečtěte si otázku
2. Najděte POUZE rozhodnutí, která přímo odpovídají na otázku
3. Ignorujte všechna ostatní rozhodnutí
4. Odpovězte stručně s citacemi [^1], [^2] pouze z relevantních rozhodnutí
5. NEZMIŇUJTE rozhodnutí, která nejsou relevantní

ODPOVĚĎ:"""
                ),
            ])
            self._chains["case_answer"] = prompt | self.gpt_model | StrOutputParser()
        return self._chains["case_answer"]

    def _get_query_chain(self):
        if "query" not in self._chains:
            prompt = ChatPromptTemplate.from_messages([
                HumanMessagePromptTemplate.from_template(QUERY_GENERATION_PROMPT),
            ])
            self._chains["query"] = prompt | self.fast_model | StrOutputParser()
        return self._chains["query"]

    async def generate_search_queries(self, question: str, num_queries: int = 5) -> list[str]:
        """Generate optimized search queries using GPT-5-nano (ultra-fast)
        
        Dynamically generates 3-5 queries based on question complexity.
        Always includes the original question.
        """
        try:
            print(f"🔍 Query generation input:")
            print(f"   Question type: {type(question)}")
            print(f"   Question length: {len(question)} chars")
            print(f"   Question: {question[:200]}{'...' if len(question) > 200 else ''}")
            
            chain = self._get_query_chain()
            result = await chain.ainvoke({"question": question})

            queries = [
                q.strip()
                for q in result.split("\n")
                if q.strip() and not q.strip().startswith(("1.", "2.", "3.", "4.", "5.", "-", "*", "•"))
            ]
            
            # Validate - allow longer queries for complex legal terms
            validated = [q for q in queries if 2 <= len(q.split()) <= 15]
            
            # Always include original question first
            final = [question]
            for q in validated:
                if q.lower() != question.lower() and len(final) < num_queries:
                    final.append(q)

            print(f"✅ Generated {len(final)} queries (GPT-5-nano)")
            for i, q in enumerate(final):
                print(f"Query: {q}")
            return final
        except Exception as e:
            print(f"❌ Query generation error: {e}")
            return [question]

    async def answer_based_on_cases(self, question: str, cases: list[CaseResult]) -> str:
        """Generate answer with GPT-5-mini - handles 400K context"""
        try:
            context = format_cases_for_context(cases)
            
            # GPT-5-mini can handle massive context efficiently
            context_tokens = len(context) // 4
            print(f"📤 Sending {len(cases)} cases to GPT-5-mini")
            print(f"   Context: {len(context):,} chars (~{context_tokens:,} tokens)")
            
            # Warn if approaching limit (400K)
            if context_tokens > 350000:
                print(f"⚠️ Large context - truncating to fit 400K window")
                context = context[:1400000]  # ~350K tokens

            chain = self._get_case_answer_chain()
            
            # GPT-5-mini is faster than 4.1-mini but may still think
            answer = await asyncio.wait_for(
                chain.ainvoke({"question": question, "context": context}),
                timeout=settings.LLM_TIMEOUT
            )

            print(f"✅ Response: {len(answer):,} chars")
            return answer
        except asyncio.TimeoutError:
            print("⏱️ GPT-5-mini timeout")
            return "⚠️ Časový limit vypršel. Zkuste kratší dotaz."
        except Exception as e:
            print(f"❌ Answer error: {e}")
            return ""

    async def answer_based_on_cases_stream(
        self, question: str, cases: list[CaseResult]
    ) -> AsyncIterator[str]:
        """Stream answer - handles GPT-5-mini thinking tokens"""
        try:
            context = format_cases_for_context(cases)
            print(f"📤 Streaming {len(cases)} cases (GPT-5-mini)")
            print(f"📝 Question being sent to LLM: {question[:300]}...")
            print(f"📊 Context length: {len(context):,} chars")
            
            # Debug: Show first case info
            if cases:
                print(f"📋 First case: {cases[0].case_number} - {(cases[0].subject or '')[:100]}...")

            chain = self._get_case_answer_chain()
            
            chunk_count = 0
            thinking_skipped = 0
            full_answer = ""
            
            async for chunk in chain.astream({"question": question, "context": context}):
                # GPT-5-mini may emit thinking/reasoning tokens - filter them
                if chunk:
                    # Skip thinking markers and internal reasoning
                    if any(marker in chunk for marker in ["<think>", "</think>", "<reasoning>", "</reasoning>"]):
                        thinking_skipped += 1
                        continue
                    chunk_count += 1
                    full_answer += chunk
                    yield chunk
            
            if thinking_skipped:
                print(f"✅ Streamed {chunk_count} chunks (filtered {thinking_skipped} thinking tokens)")
            else:
                print(f"✅ Streamed {chunk_count} chunks")
            
            # Debug: Show answer summary
            print(f"📝 Answer preview: {full_answer[:500]}...")
            if "⚠️ ŽÁDNÉ RELEVANTNÍ PŘÍPADY" in full_answer:
                print(f"⚠️ LLM returned 'no relevant cases' despite having {len(cases)} cases!")
            
        except Exception as e:
            print(f"❌ Streaming error: {e}")

    async def get_sonar_answer(self, question: str) -> tuple[str, list[str]]:
        """Get web answer from Perplexity Sonar"""
        try:
            messages = [
                SystemMessage(content=SONAR_PROMPT),
                HumanMessage(content=question)
            ]
            response = await self.sonar_model.ainvoke(messages)

            citations = []
            if hasattr(response, "response_metadata"):
                citations = response.response_metadata.get("citations", [])

            return response.content or "", citations
        except Exception as e:
            print(f"❌ Sonar error: {e}")
            return "", []

    async def get_sonar_answer_stream(self, question: str):
        """Stream Sonar answer"""
        try:
            messages = [
                SystemMessage(content=SONAR_PROMPT),
                HumanMessage(content=question)
            ]
            full_answer = ""

            async for chunk in self.sonar_model.astream(messages):
                if chunk.content:
                    full_answer += chunk.content
                    yield chunk.content, None, None

            # Get citations
            try:
                response = await self.sonar_model.ainvoke(messages)
                citations = response.response_metadata.get("citations", []) if hasattr(response, "response_metadata") else []
            except Exception:
                citations = []

            yield None, full_answer, citations
        except Exception as e:
            print(f"❌ Sonar stream error: {e}")
            yield None, "", []

    async def generate_summary_stream(
        self, question: str, web_answer: str, case_answer: str
    ) -> AsyncIterator[str]:
        """Generate summary combining web and case answers (uses fast model)"""
        try:
            prompt = f"""Shrňte v 2-3 větách hlavní závěry:

OTÁZKA: {question}
WEB: {web_answer[:3000]}
JUDIKATURA: {case_answer[:3000]}

SHRNUTÍ:"""

            async for chunk in self.fast_model.astream(prompt):
                if chunk.content:
                    yield chunk.content
        except Exception as e:
            print(f"❌ Summary error: {e}")

    async def rerank_cases(self, query: str, cases: list[CaseResult]) -> list[CaseResult]:
        """
        Rerank cases using GPT-5-nano for speed
        Returns reordered list by relevance
        """
        if len(cases) <= 3:
            return cases
        
        try:
            # Build case summaries
            case_summaries = []
            for i, case in enumerate(cases):
                summary = f"[{i}] {case.case_number}: {(case.subject or '')[:200]}"
                case_summaries.append(summary)
            
            prompt = RERANK_PROMPT.format(
                query=query,
                cases="\n".join(case_summaries)
            )
            
            # Use fast model for reranking
            response = await self.fast_model.ainvoke(prompt)
            
            # Parse indices
            indices_str = response.content.strip()
            indices = [int(i.strip()) for i in indices_str.split(",") if i.strip().isdigit()]
            
            # Reorder
            reranked = []
            for idx in indices:
                if 0 <= idx < len(cases):
                    reranked.append(cases[idx])
            
            # Add missing
            for case in cases:
                if case not in reranked:
                    reranked.append(case)
            
            print(f"🔄 Reranked {len(cases)} cases (GPT-5-nano)")
            return reranked
            
        except Exception as e:
            print(f"⚠️ Reranking failed: {e}")
            return cases


# Global instance
llm_service = LLMService()
