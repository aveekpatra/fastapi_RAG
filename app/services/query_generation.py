"""
Query Generation Service
Generates multiple optimized search queries from a user question using LLM
"""
from openai import OpenAI
from app.config import settings

QUERY_GENERATION_PROMPT = """Jste expert na generování vyhledávacích dotazů pro právní databáze. Vaším úkolem je vzít uživatelskou otázku a vygenerovat 2-3 optimalizované vyhledávací dotazy, které pomohou najít relevantní právní případy.

Pravidla pro generování dotazů:
1. Každý dotaz by měl zachytit jiný aspekt nebo perspektivu původní otázky
2. Používejte právní terminologii a klíčová slova
3. Buďte konkrétní a zaměřený - vyhněte se příliš obecným dotazům
4. Zahrňte relevantní právní pojmy, paragrafy nebo oblasti práva
5. Dotazy by měly být v češtině
6. Každý dotaz by měl být na samostatném řádku
7. Nepoužívejte číslování nebo odrážky - pouze čisté dotazy

Příklad:
Uživatelská otázka: "Může zaměstnavatel propustit zaměstnance bez udání důvodu?"

Vygenerované dotazy:
výpověď bez udání důvodu pracovní právo
okamžité zrušení pracovního poměru zaměstnavatelem
ochrana zaměstnance před neodůvodněným propuštěním

Nyní vygenerujte 2-3 optimalizované vyhledávací dotazy pro následující otázku:"""


async def generate_search_queries(question: str, client: OpenAI, num_queries: int = 3) -> list[str]:
    """
    Generate multiple optimized search queries from a user question
    
    Args:
        question: Original user question
        client: OpenAI client instance
        num_queries: Number of queries to generate (default: 3)
    
    Returns:
        List of generated search queries
    """
    try:
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {"role": "system", "content": QUERY_GENERATION_PROMPT},
                {"role": "user", "content": question}
            ],
            temperature=0.7,  # Slightly higher for diversity
            max_tokens=300,
        )
        
        generated_text = (response.choices[0].message.content or "").strip()
        
        # Parse queries - split by newlines and filter empty lines
        queries = [
            q.strip() 
            for q in generated_text.split('\n') 
            if q.strip() and not q.strip().startswith(('1.', '2.', '3.', '-', '*'))
        ]
        
        # Limit to requested number of queries
        queries = queries[:num_queries]
        
        # Fallback to original question if generation fails
        if not queries:
            print("Warning: Query generation failed, using original question")
            queries = [question]
        
        print(f"Generated {len(queries)} search queries:")
        for i, q in enumerate(queries, 1):
            print(f"  {i}. {q}")
        
        return queries
        
    except Exception as e:
        print(f"Error generating queries: {str(e)}")
        # Fallback to original question
        return [question]
