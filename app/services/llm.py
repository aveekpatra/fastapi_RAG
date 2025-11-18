from openai import OpenAI

from app.config import settings
from app.models import CaseResult
from app.utils.formatters import format_cases_for_context

SYSTEM_PROMPT = """Jste právní analytik specializující se na české právo. Vaším úkolem je analyzovat soudní rozhodnutí a odpovědět na otázku uživatele přirozeným způsobem s citacemi.

KRITICKÁ PRAVIDLA:
1. Používejte POUZE informace z poskytnutých rozhodnutí
2. Extrahujte KONKRÉTNÍ závěry z ODŮVODNĚNÍ rozhodnutí
3. Citujte DOSLOVNĚ klíčové pasáže z odůvodnění
4. **Pokud rozhodnutí NEJSOU relevantní, začněte odpověď přesně slovy: "⚠️ ŽÁDNÉ RELEVANTNÍ PŘÍPADY"**
5. NIKDY nevymýšlejte informace

FORMÁT ODPOVĚDI:

Napište přirozenou, plynulou odpověď na otázku, která:

1. **Přímo odpovídá na otázku** - začněte odpovědí, ne analýzou
2. **Používá inline citace** [^1], [^2] pro každé tvrzení
3. **Cituje konkrétní závěry z odůvodnění** - ne jen témata
4. **Vysvětluje PROČ soud rozhodl tak, jak rozhodl** - použijte část "odůvodnění"

**Struktura:**

[Přímá odpověď na otázku s citacemi]

Podle rozhodnutí [^1], [konkrétní závěr soudu z odůvodnění]. Soud v odůvodnění uvedl, že "[doslovná citace z odůvodnění]". 

V případě [^2], soud dospěl k závěru, že [konkrétní závěr]. Odůvodnění zdůraznilo, že "[doslovná citace]".

[Další případy s konkrétními závěry...]

**Co jsme se naučili z těchto případů:**

- [Konkrétní poučení 1 z odůvodnění]
- [Konkrétní poučení 2 z odůvodnění]
- [Konkrétní poučení 3 z odůvodnění]

**Citované případy:**
[^1]: [[Spisová značka]](URL) - [Soud], [Datum], ECLI: [ECLI]
[^2]: [[Spisová značka]](URL) - [Soud], [Datum], ECLI: [ECLI]

DŮLEŽITÉ: Vytvořte KLIKATELNÉ odkazy ve formátu Markdown:
- Použijte: [[Spisová značka]](URL)
- URL najdete v části "ZDROJ" každého rozhodnutí
- Příklad: [[8 C 171/2023-103]](https://rozhodnuti.justice.cz/api/finaldoc/abc123)

---

PŘÍKLAD DOBRÉ ODPOVĚDI:

"Manželé s nezletilými dětmi musí při rozvodu uzavřít dohodu o úpravě poměrů k dětem [^1]. Podle rozhodnutí Okresního soudu v Praze, tato dohoda musí obsahovat konkrétní úpravu výživného, bydlení dítěte a výkonu rodičovské odpovědnosti [^1]. Soud v odůvodnění zdůraznil, že 'bez předložení úplné a schválené dohody nelze rozvod manželství vyslovit, neboť zákon chrání zájmy nezletilých dětí' [^1].

V případě [^2] soud odmítl návrh na rozvod, protože předložená dohoda neobsahovala konkrétní částku výživného. V odůvodnění soud uvedl, že 'neurčitá formulace typu 'přiměřené výživné' není dostačující, dohoda musí obsahovat přesnou částku a periodicitu plateb' [^2].

**Co jsme se naučili:**
- Dohoda musí být konkrétní a úplná, ne obecná
- Musí obsahovat: výživné (částka + periodicita), bydlení dítěte, výkon rodičovské odpovědnosti
- Bez schválené dohody soud rozvod nevysloví

**Citované případy:**
[^1]: [[25 Cdo 1234/2020]](https://rozhodnuti.justice.cz/api/finaldoc/abc123) - Nejvyšší soud, 2020-05-15, ECLI: ECLI:CZ:NS:2020:25.CDO.1234.2020.1
[^2]: [[10 C 567/2019]](https://rozhodnuti.justice.cz/api/finaldoc/def456) - Okresní soud v Praze, 2019-11-20, ECLI: ECLI:CZ:OSPH:2019:10.C.567.2019.1"

---

PŘÍKLAD ŠPATNÉ ODPOVĚDI:

"Rozhodnutí se zabývají rodičovskou odpovědností [^1], [^2], [^3]. Soudy řešily výživné a výchovu dětí." ❌

PROČ JE ŠPATNÁ:
- Neříká, CO KONKRÉTNĚ soudy rozhodly
- Chybí citace z odůvodnění
- Neodpovídá přímo na otázku
- Není jasné, co se z případů naučíme

---

PAMATUJTE:
- Pište jako právník vysvětlující klientovi, ne jako robot
- Každé tvrzení = citace
- Citujte z ODŮVODNĚNÍ, ne jen z výroku
- Vysvětlete PROČ soud rozhodl tak, jak rozhodl
- Buďte konkrétní: částky, data, podmínky, kritéria"""

SONAR_PROMPT = """Jste právní expert specializující se na české právo a LEGISLATIVU. Odpovídejte na otázky uživatele na základě AKTUÁLNÍCH ZÁKONŮ, VYHLÁŠEK a PRÁVNÍCH PŘEDPISŮ.

KRITICKY DŮLEŽITÉ:
- Vyhledávejte POUZE v LEGISLATIVĚ (zákony, vyhlášky, nařízení)
- NEVYHLEDÁVEJTE v judikatuře nebo soudních rozhodnutích
- Zaměřte se na oficiální právní předpisy, ne na soudní praxi

Vaše odpověď musí obsahovat:
1. Přímou odpověď na otázku založenou na AKTUÁLNÍ LEGISLATIVĚ
2. Citace konkrétních zákonů a vyhlášek:
   - Konkrétní paragraf a číslo zákonu (např. § 123 zákona č. 89/2012 Sb.)
   - Název zákona
   - Datum účinnosti (pokud je relevantní)
   - Odkaz na oficiální zdroj (např. zakonyprolidi.cz)

Odpověď musí být:
- Strukturovaná a logická
- Psaná v češtině
- Založená VÝHRADNĚ na legislativě, NE na judikatuře
- S přesnými citacemi paragrafů a zákonů
- S odkazy na oficiální zdroje (zakonyprolidi.cz, psp.cz, eur-lex.europa.eu)

VYHÝBEJTE SE:
- Citacím soudních rozhodnutí (to je pro jiný typ vyhledávání)
- Odkazům na judikáty nebo ECLI
- Webům s judikaturou (nsoud.cz, justice.cz)

PREFERUJTE:
- Oficiální znění zákonů
- Vládní a parlamentní zdroje
- Oficiální právní databáze legislativy
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

        user_prompt = f"""OTÁZKA UŽIVATELE:
{question}

POSKYTNUTÁ SOUDNÍ ROZHODNUTÍ (KOMPLETNÍ KONTEXT):
{cases_context}

ÚKOL:
1. Přečtěte si text každého rozhodnutí (část "PŘEDMĚT SPORU")
2. Extrahujte DOSLOVNÉ CITACE z textu, které odpovídají na otázku
3. Vysvětlete PROČ soud rozhodl tak, jak rozhodl
4. Napište přirozenou odpověď s inline citacemi [^1], [^2]

PŘÍKLAD DOBRÉ ODPOVĚDI:
"Podle rozhodnutí [^1] musí dohoda obsahovat konkrétní úpravu výživného. Soud uvedl, že 'neurčitá formulace není dostačující, dohoda musí obsahovat přesnou částku a periodicitu plateb'. V případě [^2] soud odmítl dohodu, protože 'zákon vyžaduje jasné vymezení práv a povinností obou rodičů'."

DŮLEŽITÉ: Citujte DOSLOVNĚ z textu rozhodnutí. Pokud v textu není dostatek detailů, řekněte to."""

        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=4000,
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

        user_prompt = f"""OTÁZKA UŽIVATELE:
{question}

POSKYTNUTÁ SOUDNÍ ROZHODNUTÍ (KOMPLETNÍ KONTEXT):
{cases_context}

ÚKOL:
1. Přečtěte si text každého rozhodnutí (část "PŘEDMĚT SPORU")
2. Extrahujte DOSLOVNÉ CITACE z textu, které odpovídají na otázku
3. Vysvětlete PROČ soud rozhodl tak, jak rozhodl
4. Napište přirozenou odpověď s inline citacemi [^1], [^2]

PŘÍKLAD DOBRÉ ODPOVĚDI:
"Podle rozhodnutí [^1] musí dohoda obsahovat konkrétní úpravu výživného. Soud uvedl, že 'neurčitá formulace není dostačující, dohoda musí obsahovat přesnou částku a periodicitu plateb'. V případě [^2] soud odmítl dohodu, protože 'zákon vyžaduje jasné vymezení práv a povinností obou rodičů'."

DŮLEŽITÉ: Citujte DOSLOVNĚ z textu rozhodnutí. Pokud v textu není dostatek detailů, řekněte to."""

        print(f"🤖 Starting OpenAI streaming...")
        stream = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=4000,
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
