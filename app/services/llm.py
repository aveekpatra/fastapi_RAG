from openai import OpenAI

from app.config import settings
from app.models import CaseResult
from app.utils.formatters import format_cases_for_context

SYSTEM_PROMPT = """Jste právní analytik specializující se na české právo. Vaším úkolem je analyzovat poskytnutá soudní rozhodnutí a odpovědět na otázku uživatele.

KRITICKÁ PRAVIDLA - ABSOLUTNÍ ZÁKAZ HALUCINACÍ:
1. Používejte POUZE informace z poskytnutých rozhodnutí
2. NIKDY nevymýšlejte právní závěry, které nejsou v rozhodnutích
3. Pokud rozhodnutí neobsahují odpověď, JASNĚ to řekněte
4. NIKDY neodkazujte na zákony nebo paragrafy, které nejsou zmíněny v rozhodnutích
5. Citujte POUZE skutečné části z poskytnutých rozhodnutí

FORMÁT ODPOVĚDI:

**Shrnutí relevance:**
Nejprve v 1-2 větách řekněte, zda poskytnutá rozhodnutí odpovídají na otázku, nebo ne.

**Analýza rozhodnutí:**
Pro KAŽDÉ relevantní rozhodnutí uveďte:

📋 **[Spisová značka]** - [Soud], [Datum]
- **Co řešilo:** [Stručný popis případu z rozhodnutí]
- **Klíčové závěry:** [Konkrétní závěry soudu z rozhodnutí]
- **Právní předpisy:** [Pouze ty, které jsou zmíněny v rozhodnutí]
- **Relevance pro vaši otázku:** [Jak se to vztahuje k otázce]

**Odpověď na otázku:**
Na základě analyzovaných rozhodnutí [odpověď]. Citujte konkrétní rozhodnutí inline pomocí [^1], [^2] atd.

**Pokud rozhodnutí neodpovídají:**
Pokud poskytnutá rozhodnutí neobsahují odpověď na otázku, napište:
"⚠️ Poskytnutá rozhodnutí se nezabývají [tématem otázky]. Pro odpověď na tuto otázku by bylo potřeba nalézt rozhodnutí týkající se [konkrétní téma]."

INLINE CITACE:
- Používejte [^1], [^2], [^3] pro odkazy na konkrétní rozhodnutí
- Na konci odpovědi uveďte seznam citací:

**Citované případy:**
[^1]: [Spisová značka], [Soud], [Datum], ECLI: [ECLI]
[^2]: [Spisová značka], [Soud], [Datum], ECLI: [ECLI]

PŘÍKLAD DOBRÉ ODPOVĚDI:
"Podle rozhodnutí Nejvyššího soudu [^1] platí, že [konkrétní závěr z rozhodnutí]. Toto bylo potvrzeno i v případě [^2], kde soud rozhodl, že [konkrétní závěr]."

PŘÍKLAD ŠPATNÉ ODPOVĚDI (HALUCINACE):
"Podle § 123 zákona XYZ..." (pokud tento paragraf není v rozhodnutích)
"Obecně platí, že..." (bez odkazu na konkrétní rozhodnutí)
"Soud by pravděpodobně rozhodl..." (spekulace)

PAMATUJTE: Raději řekněte "nevím" než vymýšlejte informace!"""

SONAR_PROMPT = """Jste právní expert se specialistem na české právo. Odpovídejte na otázky uživatele VÝHRADNĚ na základě poskytnutých rozhodnutí českých soudů.

Vaše odpověď musí obsahovat:
1. Přímou odpověď na položenou otázku na základě příslušných rozhodnutí
2. Citace všech relevantních, aktuálních a konkrétních zákonů, vyhlášek, právních předpisů, právních principů, zrátka zákona, musí obsahovat:
   - Konkrétní paragraf a číslo zákonu
   - Datum vydání
   - Datum vydání
   - ECLI reference
   - Relevantní právní předpisy (§ citace)

Odpověď musí být:
- Strukturovaná a logická
- Psaná v češtině
- Soustředěna výhradně na poskytnuté informace
- Bez generalizací nebo informací mimo základnu rozhodnutí
- S přesnými citacemi a odkazem
- Musí vycházet z kontextu, musí brát v potaz i právní principy, strukturu a hierarchii zákonů
- Používejte pouze údaje z oficiálních vládních nebo renomovaných právních webů (např. zakonyprolidi.cz, nsoud.cz, eur-lex.europa.eu)
- Vyhýbejte se citacím z náhodných fór, diskuzních skupin nebo uživatelských komentářů

Pokud je otázka nezodpověditelná na základě těchto dat a tohoto postupu, výslovně to uveďte."""


def get_openai_client() -> OpenAI:
    """Get configured OpenAI client for OpenRouter"""
    return OpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
    )


async def get_sonar_answer(question: str) -> tuple[str, list[str]]:
    """
    Get answer from Perplexity Sonar with citations
    Returns: (answer_text, citations_list)
    """
    try:
        client = get_openai_client()

        sonar_response = client.chat.completions.create(
            model="perplexity/sonar",
            messages=[
                {"role": "system", "content": SONAR_PROMPT},
                {"role": "user", "content": question},
            ],
            stream=False,
        )

        sonar_answer = sonar_response.choices[0].message.content or ""

        # Capture citations
        sonar_citations = getattr(sonar_response, "citations", [])
        if not sonar_citations:
            search_results = getattr(sonar_response, "search_results", [])
            sonar_citations = [
                result.get("url", "") for result in search_results if result.get("url")
            ]

        return sonar_answer, sonar_citations

    except Exception as e:
        print(f"Chyba pri ziskani Sonar odpovedi: {str(e)}")
        return "", []


async def get_sonar_answer_stream(question: str):
    """
    Get streaming answer from Perplexity Sonar with citations
    Yields: (chunk_text, final_answer, citations_list)
    
    Note: Perplexity's streaming API doesn't include citations in chunks.
    We need to make a separate non-streaming call to get citations.
    """
    try:
        client = get_openai_client()

        # Start streaming the answer
        stream = client.chat.completions.create(
            model="perplexity/sonar",
            messages=[
                {"role": "system", "content": SONAR_PROMPT},
                {"role": "user", "content": question},
            ],
            stream=True,
        )

        full_answer = ""
        citations = []

        # Stream the content
        for chunk in stream:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_answer += content
                yield content, None, None

        # After streaming completes, make a non-streaming call to get citations
        # This is necessary because Perplexity's streaming API doesn't include citations
        try:
            citation_response = client.chat.completions.create(
                model="perplexity/sonar",
                messages=[
                    {"role": "system", "content": SONAR_PROMPT},
                    {"role": "user", "content": question},
                ],
                stream=False,
            )
            
            # Extract citations from the response
            citations = getattr(citation_response, "citations", [])
            if not citations:
                # Fallback to search_results if citations not available
                search_results = getattr(citation_response, "search_results", [])
                citations = [
                    result.get("url", "") for result in search_results if result.get("url")
                ]
        except Exception as citation_error:
            print(f"Error fetching citations: {str(citation_error)}")
            citations = []

        # Final yield with complete answer and citations
        yield None, full_answer, citations

    except Exception as e:
        print(f"Chyba pri ziskani Sonar odpovedi: {str(e)}")
        yield None, "", []


async def answer_based_on_cases(
    question: str, cases: list[CaseResult], client: OpenAI
) -> str:
    """
    GPT-4o answers the question based on all case data with citations
    """
    try:
        cases_context = format_cases_for_context(cases)

        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"""OTÁZKA UŽIVATELE:
{question}

POSKYTNUTÁ SOUDNÍ ROZHODNUTÍ:
{cases_context}

ÚKOL:
1. Analyzujte každé rozhodnutí a zjistěte, zda obsahuje informace relevantní k otázce
2. Pokud ANO: Vytvořte strukturovanou odpověď s inline citacemi [^1], [^2] atd.
3. Pokud NE: Jasně řekněte, že rozhodnutí se netýkají této otázky
4. NIKDY nevymýšlejte informace, které nejsou v rozhodnutích
5. Citujte konkrétní části rozhodnutí, ne obecné právní znalosti

Začněte analýzou relevance rozhodnutí.""",
                },
            ],
            temperature=0.3,  # Snížená teplota pro menší halucinace
            max_tokens=2500,
        )

        answer = (response.choices[0].message.content or "").strip()
        return answer

    except Exception as e:
        print(f"Chyba pri generovani odpovedi zalozene na pripadech: {str(e)}")
        return ""


async def answer_based_on_cases_stream(
    question: str, cases: list[CaseResult], client: OpenAI
):
    """
    Stream GPT-4o answer based on cases
    """
    try:
        print(f"📝 Formatting {len(cases)} cases for context...")
        cases_context = format_cases_for_context(cases)
        print(f"📝 Context length: {len(cases_context)} characters")

        print(f"🤖 Starting OpenAI streaming...")
        stream = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"""OTÁZKA UŽIVATELE:
{question}

POSKYTNUTÁ SOUDNÍ ROZHODNUTÍ:
{cases_context}

ÚKOL:
1. Analyzujte každé rozhodnutí a zjistěte, zda obsahuje informace relevantní k otázce
2. Pokud ANO: Vytvořte strukturovanou odpověď s inline citacemi [^1], [^2] atd.
3. Pokud NE: Jasně řekněte, že rozhodnutí se netýkají této otázky
4. NIKDY nevymýšlejte informace, které nejsou v rozhodnutích
5. Citujte konkrétní části rozhodnutí, ne obecné právní znalosti

Začněte analýzou relevance rozhodnutí.""",
                },
            ],
            temperature=0.3,  # Snížená teplota pro menší halucinace
            max_tokens=2500,
            stream=True,
        )

        chunk_count = 0
        for chunk in stream:
            if chunk.choices[0].delta.content:
                chunk_count += 1
                content = chunk.choices[0].delta.content
                yield content
        
        print(f"✅ Yielded {chunk_count} chunks from OpenAI")
        
        if chunk_count == 0:
            print("⚠️ WARNING: OpenAI returned 0 chunks!")

    except Exception as e:
        print(f"❌ Chyba pri streamovani odpovedi: {str(e)}")
        import traceback
        traceback.print_exc()
        traceback.print_exc()
