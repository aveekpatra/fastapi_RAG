"""
Compare Basic vs Improved RAG Search Methods
This script helps identify why improved RAG might be choosing wrong answers
"""
import asyncio
import json
from typing import Dict, Any, List
from dotenv import load_dotenv
import os

# Import your services directly
from app.services.qdrant import _get_cases_basic, _get_cases_improved_rag
from app.services.llm import get_openai_client
from app.services.query_generation import generate_search_queries
from app.config import settings

load_dotenv()


class SearchComparator:
    def __init__(self):
        self.openai_client = get_openai_client()
    
    async def compare_search_methods(self, question: str, top_k: int = 5) -> Dict[str, Any]:
        """
        Compare basic and improved RAG search methods side by side
        """
        print("\n" + "=" * 80)
        print(f"COMPARING SEARCH METHODS")
        print("=" * 80)
        print(f"Question: {question}")
        print(f"Top K: {top_k}")
        print("-" * 80)
        
        results = {
            "question": question,
            "top_k": top_k,
            "basic_rag": {},
            "improved_rag": {},
            "comparison": {}
        }
        
        # Test 1: Basic RAG
        print("\n[1/3] Testing BASIC RAG (single vector search)...")
        try:
            basic_cases = await _get_cases_basic(question, top_k)
            results["basic_rag"] = {
                "status": "success",
                "num_results": len(basic_cases),
                "cases": [
                    {
                        "case_number": c.case_number,
                        "court": c.court,
                        "subject": c.subject[:100] + "..." if len(c.subject) > 100 else c.subject,
                        "relevance_score": round(c.relevance_score, 4),
                        "keywords": c.keywords[:5]
                    }
                    for c in basic_cases
                ]
            }
            print(f"✅ Basic RAG: Found {len(basic_cases)} cases")
            
            if basic_cases:
                print(f"   Top score: {basic_cases[0].relevance_score:.4f}")
                print(f"   Top case: {basic_cases[0].case_number}")
        except Exception as e:
            results["basic_rag"] = {
                "status": "error",
                "error": str(e)
            }
            print(f"❌ Basic RAG failed: {str(e)}")
        
        # Test 2: Improved RAG with query generation
        print("\n[2/3] Testing IMPROVED RAG (query generation + multi-search)...")
        try:
            # First, show generated queries
            print("   Generating search queries...")
            generated_queries = await generate_search_queries(
                question, 
                self.openai_client,
                num_queries=settings.NUM_GENERATED_QUERIES
            )
            
            print(f"   Generated {len(generated_queries)} queries:")
            for i, q in enumerate(generated_queries, 1):
                print(f"     {i}. {q}")
            
            # Now run improved RAG
            print("   Running multi-query search...")
            improved_cases = await _get_cases_improved_rag(
                question, 
                top_k, 
                self.openai_client
            )
            
            results["improved_rag"] = {
                "status": "success",
                "generated_queries": generated_queries,
                "num_results": len(improved_cases),
                "cases": [
                    {
                        "case_number": c.case_number,
                        "court": c.court,
                        "subject": c.subject[:100] + "..." if len(c.subject) > 100 else c.subject,
                        "relevance_score": round(c.relevance_score, 4),
                        "keywords": c.keywords[:5]
                    }
                    for c in improved_cases
                ]
            }
            print(f"✅ Improved RAG: Found {len(improved_cases)} cases")
            
            if improved_cases:
                print(f"   Top score: {improved_cases[0].relevance_score:.4f}")
                print(f"   Top case: {improved_cases[0].case_number}")
        except Exception as e:
            results["improved_rag"] = {
                "status": "error",
                "error": str(e)
            }
            print(f"❌ Improved RAG failed: {str(e)}")
        
        # Test 3: Comparison
        print("\n[3/3] Analyzing differences...")
        
        if results["basic_rag"].get("status") == "success" and results["improved_rag"].get("status") == "success":
            basic_cases = results["basic_rag"]["cases"]
            improved_cases = results["improved_rag"]["cases"]
            
            # Get case numbers
            basic_case_numbers = set(c["case_number"] for c in basic_cases)
            improved_case_numbers = set(c["case_number"] for c in improved_cases)
            
            # Find differences
            only_in_basic = basic_case_numbers - improved_case_numbers
            only_in_improved = improved_case_numbers - basic_case_numbers
            in_both = basic_case_numbers & improved_case_numbers
            
            results["comparison"] = {
                "total_unique_cases": len(basic_case_numbers | improved_case_numbers),
                "cases_in_both": len(in_both),
                "only_in_basic": len(only_in_basic),
                "only_in_improved": len(only_in_improved),
                "overlap_percentage": (len(in_both) / top_k * 100) if top_k > 0 else 0,
                "only_in_basic_list": list(only_in_basic),
                "only_in_improved_list": list(only_in_improved),
                "in_both_list": list(in_both)
            }
            
            print(f"\n   Total unique cases found: {results['comparison']['total_unique_cases']}")
            print(f"   Cases in both results: {len(in_both)} ({results['comparison']['overlap_percentage']:.1f}%)")
            print(f"   Only in basic: {len(only_in_basic)}")
            print(f"   Only in improved: {len(only_in_improved)}")
            
            if len(in_both) < top_k / 2:
                print("\n   ⚠️  WARNING: Low overlap! Methods are returning very different results.")
                print("   This suggests:")
                print("   - Generated queries might be too different from original")
                print("   - Weighted scoring might be favoring different cases")
                print("   - Consider reviewing query generation prompt")
            
            # Score comparison for cases in both
            if in_both:
                print("\n   Score comparison for common cases:")
                for case_num in list(in_both)[:3]:
                    basic_case = next(c for c in basic_cases if c["case_number"] == case_num)
                    improved_case = next(c for c in improved_cases if c["case_number"] == case_num)
                    
                    print(f"     {case_num}:")
                    print(f"       Basic score: {basic_case['relevance_score']:.4f}")
                    print(f"       Improved score: {improved_case['relevance_score']:.4f}")
                    print(f"       Difference: {abs(basic_case['relevance_score'] - improved_case['relevance_score']):.4f}")
        
        return results
    
    def print_detailed_comparison(self, results: Dict[str, Any]):
        """Print detailed side-by-side comparison"""
        print("\n" + "=" * 80)
        print("DETAILED COMPARISON")
        print("=" * 80)
        
        basic_cases = results.get("basic_rag", {}).get("cases", [])
        improved_cases = results.get("improved_rag", {}).get("cases", [])
        
        print("\nBASIC RAG RESULTS:")
        print("-" * 80)
        if basic_cases:
            for i, case in enumerate(basic_cases, 1):
                print(f"{i}. {case['case_number']} (score: {case['relevance_score']})")
                print(f"   Court: {case['court']}")
                print(f"   Subject: {case['subject']}")
                print(f"   Keywords: {', '.join(case['keywords'])}")
                print()
        else:
            print("No results")
        
        print("\nIMPROVED RAG RESULTS:")
        print("-" * 80)
        if "generated_queries" in results.get("improved_rag", {}):
            print("Generated queries:")
            for i, q in enumerate(results["improved_rag"]["generated_queries"], 1):
                print(f"  {i}. {q}")
            print()
        
        if improved_cases:
            for i, case in enumerate(improved_cases, 1):
                print(f"{i}. {case['case_number']} (score: {case['relevance_score']})")
                print(f"   Court: {case['court']}")
                print(f"   Subject: {case['subject']}")
                print(f"   Keywords: {', '.join(case['keywords'])}")
                print()
        else:
            print("No results")
        
        # Highlight differences
        if basic_cases and improved_cases:
            comparison = results.get("comparison", {})
            
            print("\nKEY DIFFERENCES:")
            print("-" * 80)
            
            if comparison.get("only_in_basic_list"):
                print(f"\nCases ONLY in Basic RAG ({len(comparison['only_in_basic_list'])}):")
                for case_num in comparison["only_in_basic_list"]:
                    case = next(c for c in basic_cases if c["case_number"] == case_num)
                    print(f"  - {case_num} (score: {case['relevance_score']})")
            
            if comparison.get("only_in_improved_list"):
                print(f"\nCases ONLY in Improved RAG ({len(comparison['only_in_improved_list'])}):")
                for case_num in comparison["only_in_improved_list"]:
                    case = next(c for c in improved_cases if c["case_number"] == case_num)
                    print(f"  - {case_num} (score: {case['relevance_score']})")
    
    def save_results(self, results: Dict[str, Any], filename: str = "search_comparison.json"):
        """Save comparison results to JSON file"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Results saved to {filename}")


async def main():
    """Main comparison runner"""
    
    # Test queries
    test_queries = [
        "rozvod manželství",
        "Může zaměstnavatel propustit zaměstnance bez udání důvodu?",
        "Jaké jsou podmínky pro získání náhrady škody?",
    ]
    
    comparator = SearchComparator()
    
    print("\n" + "=" * 80)
    print("SEARCH METHOD COMPARISON TOOL")
    print("=" * 80)
    print(f"\nConfiguration:")
    print(f"  USE_IMPROVED_RAG: {settings.USE_IMPROVED_RAG}")
    print(f"  NUM_GENERATED_QUERIES: {settings.NUM_GENERATED_QUERIES}")
    print(f"  RESULTS_PER_QUERY: {settings.RESULTS_PER_QUERY}")
    print(f"  FINAL_TOP_K: {settings.FINAL_TOP_K}")
    print(f"  Qdrant Collection: {settings.QDRANT_COLLECTION}")
    
    all_results = []
    
    for i, question in enumerate(test_queries, 1):
        print(f"\n\n{'=' * 80}")
        print(f"TEST {i}/{len(test_queries)}")
        print('=' * 80)
        
        results = await comparator.compare_search_methods(question, top_k=5)
        comparator.print_detailed_comparison(results)
        
        all_results.append(results)
        
        # Save individual result
        filename = f"comparison_test_{i}.json"
        comparator.save_results(results, filename)
    
    # Summary
    print("\n\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    total_tests = len(test_queries)
    successful_basic = sum(1 for r in all_results if r["basic_rag"].get("status") == "success")
    successful_improved = sum(1 for r in all_results if r["improved_rag"].get("status") == "success")
    
    avg_overlap = sum(r["comparison"].get("overlap_percentage", 0) for r in all_results) / total_tests if total_tests > 0 else 0
    
    print(f"\nTotal tests: {total_tests}")
    print(f"Basic RAG successful: {successful_basic}/{total_tests}")
    print(f"Improved RAG successful: {successful_improved}/{total_tests}")
    print(f"Average overlap: {avg_overlap:.1f}%")
    
    if avg_overlap < 50:
        print("\n⚠️  WARNING: Low average overlap between methods!")
        print("\nPossible causes:")
        print("1. Query generation is creating very different queries")
        print("2. Weighted scoring formula is significantly changing rankings")
        print("3. Multi-query approach is finding different relevant cases")
        print("\nRecommendations:")
        print("- Review generated queries in the output above")
        print("- Check if generated queries make sense for the original question")
        print("- Consider adjusting NUM_GENERATED_QUERIES or RESULTS_PER_QUERY")
        print("- Try modifying the query generation prompt in app/services/query_generation.py")
        print("- Review the weighted scoring formula in app/services/qdrant.py")
    elif avg_overlap > 80:
        print("\n✅ High overlap - methods are returning similar results")
        print("   Improved RAG is working as expected (finding similar cases with better coverage)")
    else:
        print("\n✓ Moderate overlap - methods have some differences")
        print("  This is normal. Improved RAG should find additional relevant cases.")
    
    print("\n" + "=" * 80)
    print("Comparison complete! Check the generated JSON files for detailed results.")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
