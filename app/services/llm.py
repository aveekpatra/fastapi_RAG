from openai import OpenAI
from app.config import settings
from app.models import CaseResult
from app.utils.formatters import format_cases_for_context

SYSTEM_PROMPT = """Jste právní expert se specialistem na české právo. Odpovídejte na otázky uživatele VÝHRADNĚ na základě poskytnutých rozhodnutí českých soudů. 

Vaše odpověď musí obsahovat:
1. Přímou odpověď na položenou otázku na základě příslušných rozhodnutí
2. Citace všech relevantních rozhodnutí s následujícími údaji:
   - Spisová značka rozsudku
   - Název soudu
   - Datum vydání
   - ECLI reference
   - Relevantní právní předpisy (§ citace)
   - Klíčové právní principy nebo závěry z rozhodnutí

Odpověď musí být:
- Strukturovaná a logická
- Psaná v češtině
- Soustředěna výhradně na poskytnutá rozhodnutí
- Bez generalizací nebo informací mimo základnu rozhodnutí
- S přesnými citacemi a odkazem na čísla případů

Pokud je otázka nezodpověditelná na základě poskytnutých rozhodnutí, výslovně to uveďte."""


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
            messages=[{"role": "user", "content": question}],
            stream=False,
        )

        sonar_answer = sonar_response.choices[0].message.content or ""

        # Capture citations
        sonar_citations = getattr(sonar_response, "citations", [])
        if not sonar_citations:
            search_results = getattr(sonar_response, "search_results", [])
            sonar_citations = [
                result.get("url", "")
                for result in search_results
                if result.get("url")
            ]

        return sonar_answer, sonar_citations

    except Exception as e:
        print(f"Chyba pri ziskani Sonar odpovedi: {str(e)}")
        return "", []


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