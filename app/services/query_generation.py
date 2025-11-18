"""
Query Generation Service
Generates multiple optimized search queries from a user question using LLM
IMPORTANT: Maintains original meaning while expanding search coverage
"""
from openai import OpenAI
from app.config import settings

QUERY_GENERATION_PROMPT = """Jste expert na generování vyhledávacích dotazů pro právní databáze českých soudních rozhodnutí.

KRITICKÁ PRAVIDLA (MUSÍ BÝT DODRŽENA):
1. ZACHOVEJTE PŮVODNÍ VÝZNAM - dotazy musí hledat odpověď na STEJNOU otázku
2. Každý dotaz musí obsahovat KLÍČOVÉ PRÁVNÍ POJMY z původní otázky
3. Neměňte právní kontext ani oblast práva
4. Dotazy by měly být KRATŠÍ než původní otázka (max 8 slov)
5. Používejte konkrétní právní terminologii, ne obecné fráze
6. Každý dotaz zachycuje JINÝ ASPEKT téže otázky
7. Dotazy v češtině, jeden na řádek, BEZ číslování

ŠPATNÉ PŘÍKLADY (NEPOUŽÍVAT):
❌ "práva zaměstnanců" (příliš obecné)
❌ "co říká zákon" (příliš vágní)
❌ "soudní rozhodnutí" (nemá kontext)
❌ Dotazy měnící téma nebo právní oblast

DOBRÉ PŘÍKLADY:
✅ Původní: "Může zaměstnavatel propustit zaměstnance bez udání důvodu?"
   Dotaz 1: výpověď bez udání důvodu §52 zákoník práce
   Dotaz 2: okamžité zrušení pracovního poměru zaměstnavatelem
   Dotaz 3: ochranná doba zaměstnance výpověď

✅ Původní: "Jaké jsou podmínky pro rozvod manželství?"
   Dotaz 1: rozvod manželství podmínky §755 občanský zákoník
   Dotaz 2: rozpad manželství soudní řízení
   Dotaz 3: rozvod bez souhlasu druhého manžela

POSTUP:
1. Identifikujte HLAVNÍ PRÁVNÍ OTÁZKU
2. Extrahujte KLÍČOVÉ PRÁVNÍ POJMY
3. Vytvořte 2-3 dotazy s různými formulacemi STEJNÉ otázky
4. Každý dotaz musí být RELEVANTNÍ k původnímu záměru

Nyní vygenerujte 2-3 optimalizované vyhledávací dotazy pro následující otázku:"""


async def generate_search_queries(question: str, client: OpenAI, num_queries: int = 2) -> list[str]:
    """
    Generate multiple optimized search queries from a user question
    MAINTAINS ORIGINAL MEANING while expanding search coverage
    
    Args:
        question: Original user question
        client: OpenAI client instance
        num_queries: Number of queries to generate (default: 2)
    
    Returns:
        List of generated search queries that maintain original intent
    """
    try:
        response = client.chat.completions.create(
            model="openai/gpt-5-mini",
            messages=[
                {"role": "system", "content": QUERY_GENERATION_PROMPT},
                {"role": "user", "content": question}
            ],
            temperature=0.5,  # Hardcoded: Lower temperature for focused queries
            max_tokens=300,  # Hardcoded: Enough for 2-3 short queries
        )
        
        generated_text = (response.choices[0].message.content or "").strip()
        
        # Parse queries - split by newlines and filter empty lines
        queries = [
            q.strip() 
            for q in generated_text.split('\n') 
            if q.strip() and not q.strip().startswith(('1.', '2.', '3.', '-', '*', '✅', '❌'))
        ]
        
        # Limit to requested number of queries
        queries = queries[:num_queries]
        
        # Validate queries - ensure they're not too short or too long
        validated_queries = []
        for q in queries:
            word_count = len(q.split())
            if 2 <= word_count <= 12:  # Reasonable length
                validated_queries.append(q)
        
        # If validation removed all queries, use original
        if not validated_queries:
            print("⚠️ Warning: Query validation failed, using original question")
            validated_queries = [question]
        
        # Always include original question as first query for safety
        # Then add validated queries (excluding duplicates of original)
        final_queries = [question]
        for q in validated_queries:
            if q != question and len(final_queries) < num_queries:
                final_queries.append(q)
        
        # If we don't have enough queries, just use original
        if len(final_queries) < num_queries:
            print(f"⚠️ Varování: Vygenerováno pouze {len(final_queries)} dotazů místo {num_queries}")
        
        print(f"✅ Vygenerováno {len(final_queries)} vyhledávacích dotazů (včetně původního):")
        for i, q in enumerate(final_queries, 1):
            marker = "📌 PŮVODNÍ" if i == 1 else f"🔍 VARIANTA {i-1}"
            print(f"  {marker}: {q}")
        
        return final_queries
        
    except Exception as e:
        print(f"❌ Chyba při generování dotazů: {str(e)}")
        # Fallback to original question
        return [question]
