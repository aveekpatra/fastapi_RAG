"""
Test Script for GPT-5-mini Legal Search Pipeline
Tests: Qdrant connection, embeddings, search, LLM generation
"""
import asyncio
import os
import sys
import time

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()


async def test_config():
    """Test configuration loading"""
    print("\n" + "="*70)
    print("1️⃣  TESTING CONFIGURATION")
    print("="*70)
    
    from app.config import settings
    
    checks = [
        ("OPENROUTER_API_KEY", bool(settings.OPENROUTER_API_KEY)),
        ("QDRANT_HOST", bool(settings.QDRANT_HOST)),
        ("QDRANT_API_KEY", bool(settings.QDRANT_API_KEY)),
        ("LLM_MODEL", settings.LLM_MODEL),
        ("FAST_MODEL", settings.FAST_MODEL),
        ("LLM_TIMEOUT", settings.LLM_TIMEOUT),
        ("SEZNAM_EMBEDDING_MODEL", settings.SEZNAM_EMBEDDING_MODEL),
    ]
    
    all_ok = True
    for name, value in checks:
        status = "✅" if value else "❌"
        print(f"   {status} {name}: {value}")
        if not value:
            all_ok = False
    
    print(f"\n   Qdrant URL: {settings.qdrant_url}")
    return all_ok


async def test_qdrant_connection():
    """Test Qdrant connection and collections"""
    print("\n" + "="*70)
    print("2️⃣  TESTING QDRANT CONNECTION")
    print("="*70)
    
    from app.services.multi_source_search import multi_source_engine
    
    try:
        sources = await multi_source_engine.get_available_sources()
        
        all_ok = True
        for source in sources:
            status = "✅" if source["status"] == "available" else "❌"
            print(f"   {status} {source['name']}")
            print(f"      Collection: {source['collection']}")
            print(f"      Points: {source['points_count']:,}")
            print(f"      Status: {source['status']}")
            if source["status"] != "available":
                all_ok = False
        
        return all_ok
    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
        return False


async def test_embedding():
    """Test embedding generation"""
    print("\n" + "="*70)
    print("3️⃣  TESTING EMBEDDING MODEL")
    print("="*70)
    
    from app.services.multi_source_search import embedding_manager
    from app.config import settings
    
    test_text = "náhrada škody při dopravní nehodě"
    
    try:
        start = time.time()
        vector = embedding_manager.get_embedding(test_text, settings.SEZNAM_EMBEDDING_MODEL)
        elapsed = time.time() - start
        
        print(f"   ✅ Model: {settings.SEZNAM_EMBEDDING_MODEL}")
        print(f"   ✅ Vector size: {len(vector)}")
        print(f"   ✅ Time: {elapsed:.2f}s")
        print(f"   ✅ Sample values: [{vector[0]:.4f}, {vector[1]:.4f}, ...]")
        return True
    except Exception as e:
        print(f"   ❌ Embedding failed: {e}")
        return False


async def test_vector_search():
    """Test vector search across all courts"""
    print("\n" + "="*70)
    print("4️⃣  TESTING VECTOR SEARCH (ALL 3 COURTS)")
    print("="*70)
    
    from app.services.multi_source_search import multi_source_engine, DataSource
    
    test_query = "náhrada škody při dopravní nehodě"
    
    try:
        start = time.time()
        results = await multi_source_engine.orchestrated_search(
            query=test_query,
            source=DataSource.ALL_COURTS,
            limit=5,
            rerank=False  # Skip reranking for this test
        )
        elapsed = time.time() - start
        
        print(f"\n   Query: '{test_query}'")
        print(f"   Results: {len(results)}")
        print(f"   Time: {elapsed:.2f}s")
        
        if results:
            print(f"\n   Top results:")
            for i, r in enumerate(results[:3], 1):
                print(f"   {i}. {r.case_number} ({r.court})")
                print(f"      Score: {r.relevance_score:.4f}")
                print(f"      Date: {r.date_issued}")
                print(f"      Text: {(r.subject or '')[:100]}...")
            return True
        else:
            print("   ⚠️ No results found")
            return False
    except Exception as e:
        print(f"   ❌ Search failed: {e}")
        import traceback
        traceback.print_exc()
        return False



async def test_llm_query_generation():
    """Test LLM query generation (GPT-5-nano)"""
    print("\n" + "="*70)
    print("5️⃣  TESTING LLM QUERY GENERATION (GPT-5-nano)")
    print("="*70)
    
    from app.services.llm import llm_service
    
    test_question = "Jaké jsou podmínky pro náhradu škody při dopravní nehodě?"
    
    try:
        start = time.time()
        queries = await llm_service.generate_search_queries(test_question, num_queries=3)
        elapsed = time.time() - start
        
        print(f"   Question: '{test_question}'")
        print(f"   Generated queries ({len(queries)}):")
        for i, q in enumerate(queries, 1):
            print(f"      {i}. {q}")
        print(f"   Time: {elapsed:.2f}s")
        
        return len(queries) > 0
    except Exception as e:
        print(f"   ❌ Query generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_llm_answer_generation():
    """Test LLM answer generation (GPT-5-mini)"""
    print("\n" + "="*70)
    print("6️⃣  TESTING LLM ANSWER GENERATION (GPT-5-mini)")
    print("="*70)
    
    from app.services.llm import llm_service
    from app.services.multi_source_search import multi_source_engine, DataSource
    
    test_question = "Jaké jsou podmínky pro náhradu škody při dopravní nehodě?"
    
    try:
        # First get some cases
        print("   Fetching cases...")
        cases = await multi_source_engine.orchestrated_search(
            query=test_question,
            source=DataSource.ALL_COURTS,
            limit=3,
            rerank=False
        )
        
        if not cases:
            print("   ⚠️ No cases found, skipping answer generation")
            return False
        
        print(f"   Found {len(cases)} cases")
        print("   Generating answer (this may take a while due to reasoning)...")
        
        start = time.time()
        answer = await llm_service.answer_based_on_cases(test_question, cases)
        elapsed = time.time() - start
        
        print(f"\n   Answer preview:")
        print(f"   {answer[:500]}...")
        print(f"\n   Answer length: {len(answer)} chars")
        print(f"   Time: {elapsed:.2f}s")
        
        return len(answer) > 50
    except Exception as e:
        print(f"   ❌ Answer generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_full_pipeline():
    """Test full search pipeline with multi-query and reranking"""
    print("\n" + "="*70)
    print("7️⃣  TESTING FULL PIPELINE (Multi-query + RRF)")
    print("="*70)
    
    from app.services.llm import llm_service
    from app.services.multi_source_search import multi_source_engine, DataSource
    
    test_question = "Kdy může zaměstnavatel okamžitě zrušit pracovní poměr?"
    
    try:
        print(f"   Question: '{test_question}'")
        
        # Generate queries
        print("\n   Step 1: Generating search queries...")
        start = time.time()
        queries = await llm_service.generate_search_queries(test_question, num_queries=3)
        print(f"   Generated {len(queries)} queries in {time.time()-start:.2f}s")
        
        # Multi-query search
        print("\n   Step 2: Multi-query search with RRF fusion...")
        start = time.time()
        cases = await multi_source_engine.multi_query_search(
            queries=queries,
            source=DataSource.ALL_COURTS,
            results_per_query=10,
            final_limit=5
        )
        print(f"   Found {len(cases)} cases in {time.time()-start:.2f}s")
        
        if cases:
            print("\n   Top cases:")
            for i, c in enumerate(cases[:3], 1):
                print(f"   {i}. {c.case_number} ({c.court}) - Score: {c.relevance_score:.4f}")
        
        # Generate answer
        print("\n   Step 3: Generating answer...")
        start = time.time()
        answer = await llm_service.answer_based_on_cases(test_question, cases)
        print(f"   Generated answer in {time.time()-start:.2f}s")
        print(f"\n   Answer preview:\n   {answer[:400]}...")
        
        return len(cases) > 0 and len(answer) > 50
    except Exception as e:
        print(f"   ❌ Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("🧪 GPT-5-MINI LEGAL SEARCH PIPELINE TEST")
    print("="*70)
    
    results = {}
    
    # Run tests
    results["config"] = await test_config()
    results["qdrant"] = await test_qdrant_connection()
    results["embedding"] = await test_embedding()
    results["search"] = await test_vector_search()
    results["query_gen"] = await test_llm_query_generation()
    results["answer_gen"] = await test_llm_answer_generation()
    results["full_pipeline"] = await test_full_pipeline()
    
    # Summary
    print("\n" + "="*70)
    print("📊 TEST SUMMARY")
    print("="*70)
    
    passed = 0
    for name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {status} - {name}")
        if result:
            passed += 1
    
    total = len(results)
    print(f"\n   Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n   🎉 ALL TESTS PASSED!")
    else:
        print(f"\n   ⚠️ {total - passed} test(s) failed")
    
    print("="*70 + "\n")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
