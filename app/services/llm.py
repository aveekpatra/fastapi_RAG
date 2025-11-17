from openai import OpenAI

from app.config import settings
from app.models import CaseResult
from app.utils.formatters import format_cases_for_context

SYSTEM_PROMPT = """Jste právní analytik specializující se na české právo. Vaším úkolem je DETAILNĚ analyzovat poskytnutá soudní rozhodnutí a odpovědět na otázku uživatele s KONKRÉTNÍMI ZÁVĚRY.

KRITICKÁ PRAVIDLA - ABSOLUTNÍ ZÁKAZ HALUCINACÍ:
1. Používejte POUZE informace z poskytnutých rozhodnutí
2. NIKDY nevymýšlejte právní závěry, které nejsou v rozhodnutích
3. Pokud rozhodnutí neobsahují odpověď, JASNĚ to řekněte
4. NIKDY neodkazujte na zákony nebo paragrafy, které nejsou zmíněny v rozhodnutích
5. Citujte POUZE skutečné části z poskytnutých rozhodnutí
6. **NEJDŮLEŽITĚJŠÍ: Extrahujte KONKRÉTNÍ ZÁVĚRY a SKUTKOVÁ ZJIŠTĚNÍ z každého rozhodnutí**

FORMÁT ODPOVĚDI:

**Shrnutí relevance:**
Nejprve v 1-2 větách řekněte, zda poskytnutá rozhodnutí odpovídají na otázku, nebo ne.

**Detailní analýza rozhodnutí:**
Pro KAŽDÉ relevantní rozhodnutí uveďte:

📋 **[Spisová značka]** - [Soud], [Datum]

**Skutkový stav:**
[Co se v případě stalo? Jaká byla situace účastníků?]

**Konkrétní právní závěry soudu:**
[Co PŘESNĚ soud rozhodl? Jaké KONKRÉTNÍ závěry učinil?]
- Citujte DOSLOVNĚ klíčové pasáže z odůvodnění
- Uveďte KONKRÉTNÍ podmínky, požadavky, nebo kritéria, které soud stanovil

**Použité právní předpisy:**
[Pouze ty paragrafy, které jsou EXPLICITNĚ zmíněny v rozhodnutí]

**Přímá odpověď na vaši otázku:**
[Jak KONKRÉTNĚ toto rozhodnutí odpovídá na položenou otázku?]
[Co z tohoto rozhodnutí PŘÍMO vyplývá pro vaši situaci?]

---

**Souhrnná odpověď na otázku:**

Na základě analyzovaných rozhodnutí:

1. **[První hlavní závěr]** - Podle rozhodnutí [^1], soud konkrétně stanovil, že [PŘESNÝ CITÁT nebo PARAFRÁZE konkrétního závěru].

2. **[Druhý hlavní závěr]** - V případě [^2], soud rozhodl, že [KONKRÉTNÍ závěr s detaily].

3. **[Další závěry...]**

**Praktické shrnutí:**
[Co z těchto rozhodnutí KONKRÉTNĚ vyplývá pro odpověď na otázku?]

**Pokud rozhodnutí neodpovídají:**
Pokud poskytnutá rozhodnutí neobsahují KONKRÉTNÍ odpověď na otázku, napište:
"⚠️ Poskytnutá rozhodnutí se zabývají [co řeší], ale NEOBSAHUJÍ konkrétní informace o [co chybí]. Pro přesnou odpověď by bylo potřeba nalézt rozhodnutí, která se přímo zabývají [konkrétní téma]."

**Citované případy:**
[^1]: [Spisová značka], [Soud], [Datum], ECLI: [ECLI]
[^2]: [Spisová značka], [Soud], [Datum], ECLI: [ECLI]

PŘÍKLAD DOBRÉ ODPOVĚDI (KONKRÉTNÍ):
"Podle rozhodnutí Nejvyššího soudu sp. zn. 25 Cdo 1234/2020 [^1] platí, že 'manželé jsou povinni předložit soudu dohodu o úpravě poměrů k nezletilým dětem, která musí obsahovat úpravu výživného, bydlení a výchovy dětí.' Soud v tomto případě konkrétně uvedl, že bez takové dohody nelze rozvod vyslovit. Toto bylo potvrzeno i v případě [^2], kde soud odmítl návrh na rozvod, protože manželé nepředložili úplnou dohodu o výživném."

PŘÍKLAD ŠPATNÉ ODPOVĚDI (PŘÍLIŠ OBECNÉ):
"Rozhodnutí se zabývá rodičovskou odpovědností." ❌ (Chybí konkrétní závěry!)
"Soud řešil výživné." ❌ (Co KONKRÉTNĚ o výživném rozhodl?)
"Relevantní pro vaši otázku." ❌ (JAK konkrétně je relevantní?)

PAMATUJTE: 
- Buďte KONKRÉTNÍ, ne obecní
- Citujte PŘESNÉ závěry, ne jen témata
- Extrahujte SKUTEČNÁ ZJIŠTĚNÍ, ne jen to, čeho se případ týkal
- Pokud v rozhodnutí není dostatek detailů, ŘEKNĚTE TO"""

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
    GPT-4o answers the question based on FULL case data with citations
    NO TRUNCATION - All context is passed to GPT
    """
    try:
        # Format cases with FULL context - NO TRUNCATION
        cases_context = format_cases_for_context(cases)
        
        print(f"\n{'='*80}")
        print(f"📤 PASSING FULL CONTEXT TO GPT")
        print(f"{'='*80}")
        print(f"Number of cases: {len(cases)}")
        print(f"Context length: {len(cases_context)} characters")
        print(f"Context length: {len(cases_context.split())} words")
        print(f"Estimated tokens: ~{len(cases_context) // 4}")
        print(f"{'='*80}\n")

        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"""OTÁZKA UŽIVATELE:
{question}

POSKYTNUTÁ SOUDNÍ ROZHODNUTÍ (KOMPLETNÍ KONTEXT):
{cases_context}

ÚKOL - KRITICKY DŮLEŽITÉ:
1. Pro KAŽDÉ rozhodnutí extrahujte:
   - Skutkový stav (co se stalo)
   - KONKRÉTNÍ právní závěry soudu (ne jen témata!)
   - PŘESNÉ citace z odůvodnění
   - Jak KONKRÉTNĚ odpovídá na otázku

2. NEŘÍKEJTE jen "rozhodnutí se zabývá X" - ŘEKNĚTE "soud konkrétně rozhodl, že..."

3. Extrahujte SPECIFICKÉ požadavky, podmínky, kritéria, které soud stanovil

4. Pokud rozhodnutí neobsahuje KONKRÉTNÍ odpověď na otázku, JASNĚ to řekněte

5. NIKDY nevymýšlejte - pokud v rozhodnutí není dostatek detailů, přiznejte to

PŘÍKLAD ŠPATNÉ ANALÝZY:
"Rozhodnutí se zabývá výživným." ❌

PŘÍKLAD DOBRÉ ANALÝZY:
"Soud v tomto rozhodnutí stanovil, že dohoda o výživném musí obsahovat konkrétní částku, periodicitu plateb a způsob valorizace. Bez těchto náležitostí soud dohodu neschválil." ✅

DŮLEŽITÉ: Máte k dispozici PLNÝ kontext všech rozhodnutí bez zkrácení.
Začněte DETAILNÍ analýzou každého rozhodnutí.""",
                },
            ],
            temperature=0.3,  # Hardcoded: Low temperature to reduce hallucinations
            max_tokens=4000,  # Hardcoded: High limit for detailed responses with full context
        )

        answer = (response.choices[0].message.content or "").strip()
        
        print(f"✅ GPT response generated: {len(answer)} characters\n")
        
        return answer

    except Exception as e:
        print(f"❌ Chyba pri generovani odpovedi zalozene na pripadech: {str(e)}")
        import traceback
        traceback.print_exc()
        return ""


async def answer_based_on_cases_stream(
    question: str, cases: list[CaseResult], client: OpenAI
):
    """
    Stream GPT-4o answer based on FULL case data - NO TRUNCATION
    """
    try:
        print(f"\n{'='*80}")
        print(f"📤 STREAMING FULL CONTEXT TO GPT")
        print(f"{'='*80}")
        print(f"Number of cases: {len(cases)}")
        
        # Format cases with FULL context - NO TRUNCATION
        cases_context = format_cases_for_context(cases)
        
        print(f"Context length: {len(cases_context)} characters")
        print(f"Context length: {len(cases_context.split())} words")
        print(f"Estimated tokens: ~{len(cases_context) // 4}")
        print(f"{'='*80}\n")

        print(f"🤖 Starting OpenAI streaming...")
        stream = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"""OTÁZKA UŽIVATELE:
{question}

POSKYTNUTÁ SOUDNÍ ROZHODNUTÍ (KOMPLETNÍ KONTEXT):
{cases_context}

ÚKOL - KRITICKY DŮLEŽITÉ:
1. Pro KAŽDÉ rozhodnutí extrahujte:
   - Skutkový stav (co se stalo)
   - KONKRÉTNÍ právní závěry soudu (ne jen témata!)
   - PŘESNÉ citace z odůvodnění
   - Jak KONKRÉTNĚ odpovídá na otázku

2. NEŘÍKEJTE jen "rozhodnutí se zabývá X" - ŘEKNĚTE "soud konkrétně rozhodl, že..."

3. Extrahujte SPECIFICKÉ požadavky, podmínky, kritéria, které soud stanovil

4. Pokud rozhodnutí neobsahuje KONKRÉTNÍ odpověď na otázku, JASNĚ to řekněte

5. NIKDY nevymýšlejte - pokud v rozhodnutí není dostatek detailů, přiznejte to

PŘÍKLAD ŠPATNÉ ANALÝZY:
"Rozhodnutí se zabývá výživným." ❌

PŘÍKLAD DOBRÉ ANALÝZY:
"Soud v tomto rozhodnutí stanovil, že dohoda o výživném musí obsahovat konkrétní částku, periodicitu plateb a způsob valorizace. Bez těchto náležitostí soud dohodu neschválil." ✅

DŮLEŽITÉ: Máte k dispozici PLNÝ kontext všech rozhodnutí bez zkrácení.
Začněte DETAILNÍ analýzou každého rozhodnutí.""",
                },
            ],
            temperature=0.3,  # Hardcoded: Low temperature to reduce hallucinations
            max_tokens=4000,  # Hardcoded: High limit for detailed responses with full context
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



async def generate_combined_summary_stream(
    question: str,
    web_answer: str,
    case_answer: str,
    client: OpenAI
):
    """
    Generate a concise summary combining web and case search results
    """
    try:
        summary_prompt = """Jste právní expert. Máte k dispozici dvě odpovědi na stejnou otázku:
1. Odpověď z webového vyhledávání (aktuální právní informace)
2. Odpověď založená na soudních rozhodnutích (judikatura)

Vytvořte KRÁTKÉ shrnutí (2-3 věty), které:
- Syntetizuje obě odpovědi
- Zdůrazní klíčové body
- Ukáže, jak se webové informace a judikatura doplňují
- Buďte stručný a jasný

NEOPISUJTE celé odpovědi, pouze shrňte hlavní závěry."""

        stream = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {"role": "system", "content": summary_prompt},
                {
                    "role": "user",
                    "content": f"""OTÁZKA:
{question}

WEBOVÁ ODPOVĚĎ:
{web_answer[:1000]}

ODPOVĚĎ ZE SOUDNÍCH ROZHODNUTÍ:
{case_answer[:1000]}

Vytvořte krátké shrnutí (2-3 věty):"""
                }
            ],
            temperature=0.3,
            max_tokens=300,
            stream=True,
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    except Exception as e:
        print(f"Error generating summary: {str(e)}")
        yield ""
