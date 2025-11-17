from app.models import CaseResult


def format_cases_for_context(cases: list[CaseResult]) -> str:
    """
    Format all cases for GPT context with FULL INFORMATION - NO TRUNCATION
    
    CRITICAL: This function passes COMPLETE case information to GPT
    - NO truncation of subject text
    - NO truncation of keywords
    - NO truncation of legal references
    - ALL information is preserved for accurate legal analysis
    """
    if not cases:
        return "Žádná rozhodnutí nebyla nalezena."
    
    context = f"CELKEM NALEZENO: {len(cases)} rozhodnutí\n\n"
    context += "⚠️ DŮLEŽITÉ: Všechna rozhodnutí obsahují KOMPLETNÍ informace bez zkrácení.\n\n"
    
    for i, case in enumerate(cases, 1):
        # Format keywords - FULL LIST, NO TRUNCATION
        keywords_str = ', '.join(case.keywords) if case.keywords else 'Neuvedena'
        
        # Format legal references - FULL LIST, NO TRUNCATION
        legal_refs_str = ', '.join(case.legal_references) if case.legal_references else 'Neuvedeny'
        
        # FULL SUBJECT - NO TRUNCATION
        # This is critical for legal analysis
        full_subject = case.subject if case.subject else "Neuvedeno"
        
        context += f"""═══════════════════════════════════════════════════════════════
ROZHODNUTÍ [{i}] - Pro citaci použijte: [^{i}]
═══════════════════════════════════════════════════════════════

📋 IDENTIFIKACE:
   Spisová značka: {case.case_number}
   Soud: {case.court}
   Soudce: {case.judge or "Neuvedeno"}
   Datum vydání: {case.date_issued or "Neuvedeno"}
   Datum publikace: {case.date_published or "Neuvedeno"}
   ECLI: {case.ecli or "Neuvedeno"}

📝 PŘEDMĚT SPORU (KOMPLETNÍ TEXT):
{full_subject}

🏷️ KLÍČOVÁ SLOVA (VŠECHNA):
{keywords_str}

⚖️ PRÁVNÍ PŘEDPISY ZMÍNĚNÉ V ROZHODNUTÍ (VŠECHNY):
{legal_refs_str}

🔗 ZDROJ:
{case.source_url or "Neuvedeno"}

📊 RELEVANCE: {case.relevance_score:.4f}

"""
    
    context += """
═══════════════════════════════════════════════════════════════
INSTRUKCE PRO CITACI:
═══════════════════════════════════════════════════════════════
- Citujte rozhodnutí pomocí [^1], [^2], [^3] atd.
- Na konci odpovědi uveďte seznam všech citovaných rozhodnutí
- Používejte POUZE informace z těchto rozhodnutí
- Pokud rozhodnutí neobsahují odpověď, JASNĚ to řekněte
- VŠECHNY informace výše jsou KOMPLETNÍ bez zkrácení

POZNÁMKA: Máte k dispozici PLNÝ kontext všech rozhodnutí.
Analyzujte je důkladně a poskytněte přesnou odpověď založenou na těchto datech.
"""
    
    return context