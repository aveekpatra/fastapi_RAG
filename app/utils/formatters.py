from app.models import CaseResult


def format_cases_for_context(cases: list[CaseResult]) -> str:
    """
    Format all cases for GPT context with clear structure for citation
    """
    if not cases:
        return "Žádná rozhodnutí nebyla nalezena."
    
    context = f"CELKEM NALEZENO: {len(cases)} rozhodnutí\n\n"
    
    for i, case in enumerate(cases, 1):
        # Format keywords
        keywords_str = ', '.join(case.keywords) if case.keywords else 'Neuvedena'
        
        # Format legal references
        legal_refs_str = ', '.join(case.legal_references) if case.legal_references else 'Neuvedeny'
        
        context += f"""═══════════════════════════════════════════════════════════════
ROZHODNUTÍ [{i}] - Pro citaci použijte: [^{i}]
═══════════════════════════════════════════════════════════════

📋 IDENTIFIKACE:
   Spisová značka: {case.case_number}
   Soud: {case.court}
   Soudce: {case.judge or "Neuvedeno"}
   Datum vydání: {case.date_issued or "Neuvedeno"}
   ECLI: {case.ecli or "Neuvedeno"}

📝 PŘEDMĚT SPORU:
   {case.subject}

🏷️ KLÍČOVÁ SLOVA:
   {keywords_str}

⚖️ PRÁVNÍ PŘEDPISY ZMÍNĚNÉ V ROZHODNUTÍ:
   {legal_refs_str}

🔗 ZDROJ:
   {case.source_url or "Neuvedeno"}

📊 RELEVANCE: {case.relevance_score:.2%}

"""
    
    context += """
═══════════════════════════════════════════════════════════════
INSTRUKCE PRO CITACI:
═══════════════════════════════════════════════════════════════
- Citujte rozhodnutí pomocí [^1], [^2], [^3] atd.
- Na konci odpovědi uveďte seznam všech citovaných rozhodnutí
- Používejte POUZE informace z těchto rozhodnutí
- Pokud rozhodnutí neobsahují odpověď, JASNĚ to řekněte
"""
    
    return context