"""
LLM Service - LangChain-powered
Provides LLM integration with OpenRouter using LangChain
"""
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

# Prompts
SYSTEM_PROMPT = """Jste právní analytik specializující se na české právo. Vaším úkolem je analyzovat soudní rozhodnutí a odpovědět na otázku uživatele přirozeným způsobem s citacemi.

KRITICKÁ PRAVIDLA:
1. Používejte POUZE informace z poskytnutých rozhodnutí
2. Extrahujte KONKRÉTNÍ závěry z ODŮVODNĚNÍ rozhodnutí
3. Citujte DOSLOVNĚ klíčové pasáže z odůvodnění
4. **Pokud rozhodnutí NEJSOU relevantní, začněte odpověď přesně slovy: "⚠️ ŽÁDNÉ RELEVANTNÍ PŘÍPADY"**
5. NIKDY nevymýšlejte informace

FORMÁT ODPOVĚDI:
Napište přirozenou, plynulou odpověď na otázku s inline citacemi [^1], [^2].

**Citované případy:**
[^1]: [[Spisová značka]](URL) - [Soud], [Datum], ECLI: [ECLI]

PAMATUJTE:
- Pište jako právník vysvětlující klientovi
- Každé tvrzení = citace
- Buďte konkrétní: částky, data, podmínky, kritéria"""

SONAR_PROMPT = """Jste právní expert specializující se na české právo a LEGISLATIVU. Odpovídejte na základě AKTUÁLNÍCH ZÁKONŮ, VYHLÁŠEK a PRÁVNÍCH PŘEDPISŮ.

Vaše odpověď musí obsahovat:
1. Přímou odpověď založenou na AKTUÁLNÍ LEGISLATIVĚ
2. Citace konkrétních zákonů (např. § 123 zákona č. 89/2012 Sb.)
3. Odkazy na oficiální zdroje (zakonyprolidi.cz, psp.cz)

VYHÝBEJTE SE citacím soudních rozhodnutí - to je pro jiný typ vyhledávání."""

QUERY_GENERATION_PROMPT = """Jste expert na generování vyhledávacích dotazů pro právní databáze českých soudních rozhodnutí.

PRAVIDLA:
1. ZACHOVEJTE PŮVODNÍ VÝZNAM
2. Dotazy max 8 slov
3. Používejte právní terminologii
4. Dotazy v češtině, jeden na řádek, BEZ číslování

Vygenerujte 2-3 optimalizované vyhledávací dotazy:"""

SUMMARY_PROMPT = """Vytvořte KRÁTKÉ shrnutí (2-3 věty) kombinující webové informace a judikaturu."""


class LLMService:
    """LangChain-based LLM service"""

    def __init__(self):
        self._gpt_model: Optional[ChatOpenAI] = None
        self._sonar_model: Optional[ChatOpenAI] = None
        self._case_answer_chain = None
        self._query_generation_chain = None
        self._summary_chain = None

    @property
    def gpt_model(self) -> ChatOpenAI:
        if self._gpt_model is None:
            self._gpt_model = ChatOpenAI(
                model=settings.LLM_MODEL,
                api_key=settings.OPENROUTER_API_KEY,
                base_url=settings.OPENROUTER_BASE_URL,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
                timeout=settings.LLM_TIMEOUT,
                extra_body={"provider": {"order": ["Azure"], "allow_fallbacks": False}},
            )
        return self._gpt_model

    @property
    def sonar_model(self) -> ChatOpenAI:
        if self._sonar_model is None:
            self._sonar_model = ChatOpenAI(
                model="perplexity/sonar",
                api_key=settings.OPENROUTER_API_KEY,
                base_url=settings.OPENROUTER_BASE_URL,
                temperature=0.7,
                timeout=settings.LLM_TIMEOUT,
            )
        return self._sonar_model

    def get_case_answer_chain(self):
        if self._case_answer_chain is None:
            prompt = ChatPromptTemplate.from_messages([
                SystemMessagePromptTemplate.from_template(SYSTEM_PROMPT),
                HumanMessagePromptTemplate.from_template(
                    "OTÁZKA: {question}\n\nROZHODNUTÍ:\n{context}\n\nOdpovězte s citacemi:"
                ),
            ])
            self._case_answer_chain = prompt | self.gpt_model | StrOutputParser()
        return self._case_answer_chain

    def get_query_generation_chain(self):
        if self._query_generation_chain is None:
            prompt = ChatPromptTemplate.from_messages([
                SystemMessagePromptTemplate.from_template(QUERY_GENERATION_PROMPT),
                HumanMessagePromptTemplate.from_template("{question}"),
            ])
            query_model = ChatOpenAI(
                model=settings.LLM_MODEL,
                api_key=settings.OPENROUTER_API_KEY,
                base_url=settings.OPENROUTER_BASE_URL,
                temperature=0.5,
                max_tokens=2000,
                timeout=60.0,
                extra_body={"provider": {"order": ["Azure"], "allow_fallbacks": False}},
            )
            self._query_generation_chain = prompt | query_model | StrOutputParser()
        return self._query_generation_chain

    def get_summary_chain(self):
        if self._summary_chain is None:
            prompt = ChatPromptTemplate.from_messages([
                SystemMessagePromptTemplate.from_template(SUMMARY_PROMPT),
                HumanMessagePromptTemplate.from_template(
                    "OTÁZKA: {question}\nWEB: {web_answer}\nJUDIKATURA: {case_answer}"
                ),
            ])
            self._summary_chain = prompt | self.gpt_model | StrOutputParser()
        return self._summary_chain

    async def generate_search_queries(self, question: str, num_queries: int = 2) -> list[str]:
        try:
            chain = self.get_query_generation_chain()
            generated_text = await chain.ainvoke({"question": question})

            queries = [
                q.strip()
                for q in generated_text.split("\n")
                if q.strip() and not q.strip().startswith(("1.", "2.", "3.", "-", "*"))
            ]
            queries = queries[:num_queries]

            validated = [q for q in queries if 2 <= len(q.split()) <= 12]
            if not validated:
                validated = [question]

            final = [question]
            for q in validated:
                if q != question and len(final) < num_queries:
                    final.append(q)

            print(f"✅ Generated {len(final)} search queries")
            return final
        except Exception as e:
            print(f"❌ Query generation error: {e}")
            return [question]

    async def answer_based_on_cases(self, question: str, cases: list[CaseResult]) -> str:
        try:
            context = format_cases_for_context(cases)
            print(f"📤 Passing {len(cases)} cases to GPT ({len(context)} chars)")

            chain = self.get_case_answer_chain()
            answer = await chain.ainvoke({"question": question, "context": context})

            print(f"✅ GPT response: {len(answer)} chars")
            return answer
        except Exception as e:
            print(f"❌ Answer generation error: {e}")
            return ""

    async def answer_based_on_cases_stream(
        self, question: str, cases: list[CaseResult]
    ) -> AsyncIterator[str]:
        try:
            context = format_cases_for_context(cases)
            print(f"📤 Streaming {len(cases)} cases to GPT")

            chain = self.get_case_answer_chain()
            async for chunk in chain.astream({"question": question, "context": context}):
                if chunk:
                    yield chunk
        except Exception as e:
            print(f"❌ Streaming error: {e}")

    async def get_sonar_answer(self, question: str) -> tuple[str, list[str]]:
        try:
            messages = [SystemMessage(content=SONAR_PROMPT), HumanMessage(content=question)]
            response = await self.sonar_model.ainvoke(messages)

            citations = []
            if hasattr(response, "response_metadata"):
                metadata = response.response_metadata
                citations = metadata.get("citations", [])

            return response.content or "", citations
        except Exception as e:
            print(f"❌ Sonar error: {e}")
            return "", []

    async def get_sonar_answer_stream(self, question: str):
        try:
            messages = [SystemMessage(content=SONAR_PROMPT), HumanMessage(content=question)]
            full_answer = ""

            async for chunk in self.sonar_model.astream(messages):
                if chunk.content:
                    full_answer += chunk.content
                    yield chunk.content, None, None

            # Get citations separately
            try:
                response = await self.sonar_model.ainvoke(messages)
                citations = []
                if hasattr(response, "response_metadata"):
                    citations = response.response_metadata.get("citations", [])
            except Exception:
                citations = []

            yield None, full_answer, citations
        except Exception as e:
            print(f"❌ Sonar streaming error: {e}")
            yield None, "", []

    async def generate_summary_stream(
        self, question: str, web_answer: str, case_answer: str
    ) -> AsyncIterator[str]:
        try:
            chain = self.get_summary_chain()
            async for chunk in chain.astream({
                "question": question,
                "web_answer": web_answer[:5000],
                "case_answer": case_answer[:5000],
            }):
                if chunk:
                    yield chunk
        except Exception as e:
            print(f"❌ Summary error: {e}")


# Global instance
llm_service = LLMService()
