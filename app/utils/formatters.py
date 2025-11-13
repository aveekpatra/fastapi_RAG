from app.models import CaseResult


def format_cases_for_context(cases: list[CaseResult]) -> str:
    """
    Format all cases for GPT context without truncation
    """
    context = ""
    for i, case in enumerate(cases, 1):
        context += f"""
ROZHODNUTÍ {i}:
Spisová značka: {case.case_number}
Soud: {case.court}
Soudce: {case.judge or "Neuvedeno"}
Datum vydání: {case.date_issued}
Datum publikace: {case.date_published}
ECLI: {case.ecli}
Předmět sporu: {case.subject}
Klíčová slova: {', '.join(case.keywords) if case.keywords else 'Neuvedena'}
Právní předpisy: {', '.join(case.legal_references) if case.legal_references else 'Neuvedeny'}
Zdroj: {case.source_url}
Relevance: {case.relevance_score}
---
"""
    return context