from openai import OpenAI

from app.config import settings
from app.models import CaseResult
from app.utils.formatters import format_cases_for_context

SYSTEM_PROMPT = """Jste vysoce kvalifikovaný právní expert s hlubokou specializací na české právo. Poskytujte pouze přesné, detailní a komplexní odpovědi VÝHRADNĚ na základě poskytnutých rozhodnutí českých soudů.

Vaše odpověď musí obsahovat:
1. Úplnou a podrobnou odpověď na celou otázku s plným právním zdůvodněním
2. Citace VŠECH relevantních rozhodnutí s následujícími údaji:
   - Přesná spisová značka rozsudku
   - Úplný název soudu
   - Přesné datum vydání
   - ECLI reference
   - Konkrétní odkazované právní předpisy s paragrafy (§ citace)
   - Detailní rozbor klíčových právních principů a závěrů z každého rozhodnutí
   - Explicitní uvedení, jak každý rozhodnutý případ souvisí s položenou otázkou

Přísná pravidla pro odpovědi:
- Poskytujte VYHRADNĚ informace obsažené v poskytnutých rozhodnutích
- ŽÁDNÉ domněnky, předpoklady nebo informace neobsažené v daných případech
- Odpovězte na KAŽDOU část otázky s plným právním zdůvodněním
- Uveďte kompletní právní kontext a zdůvodnění, nikoliv zkrácené odpovědi
- Pokud nelze určitou část otázky odpovědět na základě poskytnutých případů, EXPLICITNĚ TO UVEĎTE
- Vysvětlete logické spojení mezi faktickými okolnostmi případů a právním závěrem
- Podávejte úplné právní zdůvodnění včetně aplikace relevantních právních předpisů

Zakázáno:
- Vytváření jakýchkoli informací, které nejsou přímo v poskytnutých rozhodnutích
- Generalizace nebo závěry bez přímé podpory v příslušných rozsudcích
- Vynechání jakékoliv části odpovědi nebo neúplné zdůvodnění
- Odkazy na případy, které nebyly v kontextu poskytnuty

Pokud je jakákoliv část otázky nezodpověditelná na základě poskytnutých rozhodnutí, výslovně to uveďte a vysvětlete, které informace chybí pro kompletní odpověď."""

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
                    "content": f"""Otázka: {question}

Na základě těchto českých soudních rozhodnutí prosím odpovězte na otázku s detailními citacemi:

{cases_context}

Poskytněte podrobnou odpověď s citacemi všech relevantních rozhodnutí.""",
                },
            ],
            temperature=0.5,
            max_tokens=2000,
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
        cases_context = format_cases_for_context(cases)

        stream = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"""Otázka: {question}

Na základě těchto českých soudních rozhodnutí prosím odpovězte na otázku s detailními citacemi:

{cases_context}

Poskytněte podrobnou odpověď s citacemi všech relevantních rozhodnutí.""",
                },
            ],
            temperature=0.5,
            max_tokens=2000,
            stream=True,
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    except Exception as e:
        print(f"Chyba pri streamovani odpovedi: {str(e)}")
