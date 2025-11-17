"""
Diagnostic Tool: Why Are We Getting Wrong Answers?
This script performs deep analysis to identify the root cause
"""
import asyncio
import json
from typing import Dict, Any, List
from dotenv import load_dotenv

from app.services.qdrant import _get_cases_basic
from app.services.llm import get_openai_client
from app.services.query_generation import generate_search_queries
from app.services.embedding import get_embedding
from app.config import settings

load_dotenv()


class WrongAnswerDiagnostic:
    def __init__(self):
        self.openai_client = get_openai_client()
    
    async def analyze_query_generation(self, question: str) -> Dict[str, Any]:
        """
        Analyze if query generation is creating relevant queries
        """
        print("\n" + "=" * 80)
        print("STEP 1: QUERY GENERATION ANALYSIS")
        print("=" * 80)
        
        print(f"\nOriginal Question: {question}")
        
        # Generate queries
        queries = await generate_search_queries(
            question,
            self.openai_client,
            num_queries=settings.NUM_GENERATED_QUERIES
        )
        
        print(f"\nGenerated {len(queries)} queries:")
        for i, q in enumerate(queries, 1):
            print(f"  {i}. {q}")
        
        # Analyze query quality
        analysis = {
            "original_question": question,
            "generated_queries": queries,
            "quality_checks": {}
        }
        
        # Check 1: Are queries too similar to original?
        original_words = set(question.lower().split())
        for i, query in enumerate(queries, 1):
            query_words = set(query.lower().split())
            overlap = len(original_words & query_words) / len(original_words) if original_words else 0
            
            analysis["quality_checks"][f"query_{i}"] = {
                "query": query,
                "word_overlap_with_original": round(overlap * 100, 1),
                "assessment": "too_similar" if overlap > 0.8 else "good_diversity" if overlap < 0.5 else "moderate"
            }
            
            print(f"\n  Query {i} Analysis:")
            print(f"    Word overlap with original: {overlap * 100:.1f}%")
            print(f"    Assessment: {analysis['quality_checks'][f'query_{i}']['assessment']}")
        
        # Overall assessment
        avg_overlap = sum(
            check["word_overlap_with_original"] 
            for check in analysis["quality_checks"].values()
        ) / len(queries) if queries else 0
        
        if avg_overlap > 80:
            print("\n  ⚠️  WARNING: Queries are too similar to original!")
            print("     This defeats the purpose of multi-query search.")
            print("     Consider improving the query generation prompt.")
        elif avg_overlap < 30:
            print("\n  ⚠️  WARNING: Queries might be too different!")
            print("     They might not capture the original intent.")
        else:
            print("\n  ✅ Query diversity looks good!")
        
        return analysis
    
    async def analyze_individual_query_results(self, queries: List[str], top_k: int = 10) -> Dict[str, Any]:
        """
        Analyze results for each individual query
        """
        print("\n" + "=" * 80)
        print("STEP 2: INDIVIDUAL QUERY RESULTS ANALYSIS")
        print("=" * 80)
        
        results = {
            "queries": {},
            "overlap_analysis": {}
        }
        
        all_case_numbers = []
        
        for i, query in enumerate(queries, 1):
            print(f"\n[Query {i}] {query}")
            print("-" * 80)
            
            cases = await _get_cases_basic(query, top_k)
            
            case_numbers = [c.case_number for c in cases]
            all_case_numbers.append(set(case_numbers))
            
            results["queries"][f"query_{i}"] = {
                "query": query,
                "num_results": len(cases),
                "cases": [
                    {
                        "case_number": c.case_number,
                        "court": c.court,
                        "subject": c.subject[:80] + "..." if len(c.subject) > 80 else c.subject,
                        "score": round(c.relevance_score, 4),
                        "keywords": c.keywords[:3]
                    }
                    for c in cases
                ]
            }
            
            print(f"  Found {len(cases)} cases")
            if cases:
                print(f"  Top case: {cases[0].case_number} (score: {cases[0].relevance_score:.4f})")
                print(f"  Subject: {cases[0].subject[:100]}...")
                print(f"  Keywords: {', '.join(cases[0].keywords[:5])}")
            else:
                print("  ⚠️  No results found!")
        
        # Analyze overlap between queries
        if len(all_case_numbers) >= 2:
            print("\n" + "-" * 80)
            print("OVERLAP ANALYSIS")
            print("-" * 80)
            
            # Pairwise overlap
            for i in range(len(queries)):
                for j in range(i + 1, len(queries)):
                    overlap = all_case_numbers[i] & all_case_numbers[j]
                    overlap_pct = len(overlap) / top_k * 100 if top_k > 0 else 0
                    
                    print(f"\nQuery {i+1} vs Query {j+1}:")
                    print(f"  Common cases: {len(overlap)} ({overlap_pct:.1f}%)")
                    
                    if overlap_pct > 70:
                        print(f"  ⚠️  High overlap - queries might be too similar")
                    elif overlap_pct < 20:
                        print(f"  ⚠️  Low overlap - queries might be too different")
                    else:
                        print(f"  ✅ Good diversity")
                    
                    results["overlap_analysis"][f"q{i+1}_vs_q{j+1}"] = {
                        "overlap_count": len(overlap),
                        "overlap_percentage": round(overlap_pct, 1),
                        "common_cases": list(overlap)
                    }
        
        return results
    
    async def analyze_scoring_impact(self, question: str, queries: List[str], top_k: int = 5) -> Dict[str, Any]:
        """
        Analyze how weighted scoring affects final results
        """
        print("\n" + "=" * 80)
        print("STEP 3: SCORING IMPACT ANALYSIS")
        print("=" * 80)
        
        # Get results for each query
        all_results = []
        for query in queries:
            cases = await _get_cases_basic(query, settings.RESULTS_PER_QUERY)
            all_results.append(cases)
        
        # Simulate the merging logic from _get_cases_improved_rag
        case_scores = {}
        
        for query_results in all_results:
            for case in query_results:
                case_id = case.case_number
                
                if case_id not in case_scores:
                    case_scores[case_id] = {
                        'case': case,
                        'max_score': case.relevance_score,
                        'total_score': case.relevance_score,
                        'count': 1,
                        'scores': [case.relevance_score]
                    }
                else:
                    case_scores[case_id]['max_score'] = max(
                        case_scores[case_id]['max_score'],
                        case.relevance_score
                    )
                    case_scores[case_id]['total_score'] += case.relevance_score
                    case_scores[case_id]['count'] += 1
                    case_scores[case_id]['scores'].append(case.relevance_score)
        
        # Calculate different scoring methods
        scoring_methods = {
            "current_weighted": [],  # (avg * sqrt(count))
            "max_score": [],
            "average_score": [],
            "sum_score": []
        }
        
        for case_id, data in case_scores.items():
            case = data['case']
            
            # Current method
            weighted = (data['total_score'] / data['count']) * (data['count'] ** 0.5)
            scoring_methods["current_weighted"].append((case_id, weighted, data))
            
            # Alternative methods
            scoring_methods["max_score"].append((case_id, data['max_score'], data))
            scoring_methods["average_score"].append((case_id, data['total_score'] / data['count'], data))
            scoring_methods["sum_score"].append((case_id, data['total_score'], data))
        
        # Sort each method
        for method in scoring_methods:
            scoring_methods[method].sort(key=lambda x: x[1], reverse=True)
        
        # Compare top K results
        print(f"\nComparing top {top_k} results across scoring methods:")
        print("-" * 80)
        
        analysis = {
            "scoring_methods": {}
        }
        
        for method_name, results in scoring_methods.items():
            top_cases = results[:top_k]
            
            print(f"\n{method_name.upper().replace('_', ' ')}:")
            for i, (case_id, score, data) in enumerate(top_cases, 1):
                print(f"  {i}. {case_id}")
                print(f"     Score: {score:.4f}")
                print(f"     Appeared in {data['count']}/{len(queries)} queries")
                print(f"     Individual scores: {[round(s, 4) for s in data['scores']]}")
            
            analysis["scoring_methods"][method_name] = [
                {
                    "case_number": case_id,
                    "score": round(score, 4),
                    "frequency": data['count'],
                    "individual_scores": [round(s, 4) for s in data['scores']]
                }
                for case_id, score, data in top_cases
            ]
        
        # Check if different methods give different results
        current_top = set(c[0] for c in scoring_methods["current_weighted"][:top_k])
        max_top = set(c[0] for c in scoring_methods["max_score"][:top_k])
        avg_top = set(c[0] for c in scoring_methods["average_score"][:top_k])
        
        print("\n" + "-" * 80)
        print("SCORING METHOD COMPARISON:")
        print("-" * 80)
        
        current_vs_max = len(current_top & max_top) / top_k * 100
        current_vs_avg = len(current_top & avg_top) / top_k * 100
        
        print(f"Current vs Max Score overlap: {current_vs_max:.1f}%")
        print(f"Current vs Average Score overlap: {current_vs_avg:.1f}%")
        
        if current_vs_max < 60 or current_vs_avg < 60:
            print("\n⚠️  WARNING: Scoring method significantly affects results!")
            print("   Consider testing different scoring formulas.")
        else:
            print("\n✅ Scoring method is relatively stable.")
        
        analysis["overlap_analysis"] = {
            "current_vs_max": round(current_vs_max, 1),
            "current_vs_avg": round(current_vs_avg, 1)
        }
        
        return analysis
    
    async def run_full_diagnostic(self, question: str, top_k: int = 5):
        """
        Run complete diagnostic workflow
        """
        print("\n" + "=" * 80)
        print("WRONG ANSWER DIAGNOSTIC TOOL")
        print("=" * 80)
        print(f"\nQuestion: {question}")
        print(f"Top K: {top_k}")
        print(f"\nConfiguration:")
        print(f"  USE_IMPROVED_RAG: {settings.USE_IMPROVED_RAG}")
        print(f"  NUM_GENERATED_QUERIES: {settings.NUM_GENERATED_QUERIES}")
        print(f"  RESULTS_PER_QUERY: {settings.RESULTS_PER_QUERY}")
        
        report = {
            "question": question,
            "top_k": top_k,
            "config": {
                "use_improved_rag": settings.USE_IMPROVED_RAG,
                "num_generated_queries": settings.NUM_GENERATED_QUERIES,
                "results_per_query": settings.RESULTS_PER_QUERY
            }
        }
        
        # Step 1: Query generation analysis
        query_analysis = await self.analyze_query_generation(question)
        report["query_generation"] = query_analysis
        
        # Step 2: Individual query results
        queries = query_analysis["generated_queries"]
        results_analysis = await self.analyze_individual_query_results(queries, settings.RESULTS_PER_QUERY)
        report["individual_results"] = results_analysis
        
        # Step 3: Scoring impact
        scoring_analysis = await self.analyze_scoring_impact(question, queries, top_k)
        report["scoring_analysis"] = scoring_analysis
        
        # Final recommendations
        print("\n" + "=" * 80)
        print("RECOMMENDATIONS")
        print("=" * 80)
        
        recommendations = []
        
        # Check query quality
        avg_overlap = sum(
            check["word_overlap_with_original"]
            for check in query_analysis["quality_checks"].values()
        ) / len(queries) if queries else 0
        
        if avg_overlap > 80:
            recommendations.append({
                "issue": "Queries too similar to original",
                "severity": "high",
                "solution": "Improve query generation prompt to create more diverse queries"
            })
        elif avg_overlap < 30:
            recommendations.append({
                "issue": "Queries too different from original",
                "severity": "medium",
                "solution": "Adjust query generation prompt to stay closer to original intent"
            })
        
        # Check scoring impact
        if scoring_analysis["overlap_analysis"]["current_vs_max"] < 60:
            recommendations.append({
                "issue": "Scoring method significantly changes results",
                "severity": "high",
                "solution": "Consider using max_score or average_score instead of weighted formula"
            })
        
        # Check if any query returned no results
        no_results_queries = [
            q for q, data in results_analysis["queries"].items()
            if data["num_results"] == 0
        ]
        
        if no_results_queries:
            recommendations.append({
                "issue": f"{len(no_results_queries)} queries returned no results",
                "severity": "high",
                "solution": "Generated queries might be too specific or use wrong terminology"
            })
        
        if recommendations:
            print("\n⚠️  Issues found:")
            for i, rec in enumerate(recommendations, 1):
                print(f"\n{i}. {rec['issue']} (Severity: {rec['severity']})")
                print(f"   Solution: {rec['solution']}")
        else:
            print("\n✅ No major issues detected!")
            print("   The improved RAG pipeline appears to be working correctly.")
            print("   If you're still getting wrong answers, the issue might be:")
            print("   - Data quality in Qdrant collection")
            print("   - Embedding model mismatch")
            print("   - User expectations vs actual relevant cases")
        
        report["recommendations"] = recommendations
        
        # Save report
        filename = "diagnostic_report.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Full diagnostic report saved to {filename}")
        
        return report


async def main():
    """Main diagnostic runner"""
    
    # Test with a problematic query
    test_question = input("\nEnter a question that's giving wrong answers (or press Enter for default): ").strip()
    
    if not test_question:
        test_question = "Může zaměstnavatel propustit zaměstnance bez udání důvodu?"
        print(f"Using default question: {test_question}")
    
    diagnostic = WrongAnswerDiagnostic()
    await diagnostic.run_full_diagnostic(test_question, top_k=5)
    
    print("\n" + "=" * 80)
    print("Diagnostic complete!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
