"""
Advanced Search Testing and Validation Tool
Tests both basic and improved RAG pipelines and compares results
"""
import asyncio
import json
from typing import List, Dict, Any
from dotenv import load_dotenv
import httpx

load_dotenv()

# Test configuration
API_BASE_URL = "http://localhost:8000"  # Change if your API runs on different port
API_KEY = ""  # Set your API key here or in .env

# Test queries - add your own test cases
TEST_QUERIES = [
    {
        "question": "rozvod manželství",
        "expected_keywords": ["rozvod", "manželství", "rozchod"],
        "description": "Basic divorce query"
    },
    {
        "question": "Může zaměstnavatel propustit zaměstnance bez udání důvodu?",
        "expected_keywords": ["výpověď", "zaměstnanec", "pracovní"],
        "description": "Employment termination question"
    },
    {
        "question": "Jaké jsou podmínky pro získání náhrady škody?",
        "expected_keywords": ["náhrada", "škoda", "odpovědnost"],
        "description": "Damages compensation question"
    },
]


class SearchTester:
    def __init__(self, api_base_url: str, api_key: str):
        self.api_base_url = api_base_url
        self.api_key = api_key
        self.headers = {"X-API-Key": api_key} if api_key else {}
    
    async def test_basic_search(self, question: str, top_k: int = 5) -> Dict[str, Any]:
        """Test basic search endpoint"""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(
                    f"{self.api_base_url}/search-cases",
                    params={"question": question, "top_k": top_k},
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    return {
                        "status": "success",
                        "data": response.json()
                    }
                else:
                    return {
                        "status": "error",
                        "status_code": response.status_code,
                        "error": response.text
                    }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def test_debug_search(self, question: str, top_k: int = 5) -> Dict[str, Any]:
        """Test debug search endpoint with detailed info"""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(
                    f"{self.api_base_url}/debug/test-search",
                    params={"question": question, "top_k": top_k},
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    return {
                        "status": "success",
                        "data": response.json()
                    }
                else:
                    return {
                        "status": "error",
                        "status_code": response.status_code,
                        "error": response.text
                    }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def test_qdrant_diagnostics(self) -> Dict[str, Any]:
        """Run full Qdrant diagnostics"""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(
                    f"{self.api_base_url}/debug/qdrant-full",
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    return {
                        "status": "success",
                        "data": response.json()
                    }
                else:
                    return {
                        "status": "error",
                        "status_code": response.status_code,
                        "error": response.text
                    }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
    
    def analyze_results(self, results: Dict[str, Any], expected_keywords: List[str]) -> Dict[str, Any]:
        """Analyze search results for relevance"""
        if results.get("status") != "success":
            return {"error": "Search failed"}
        
        data = results.get("data", {})
        cases = data.get("cases", [])
        
        analysis = {
            "total_results": len(cases),
            "keyword_matches": {},
            "score_distribution": [],
            "relevance_assessment": "unknown"
        }
        
        if not cases:
            analysis["relevance_assessment"] = "no_results"
            return analysis
        
        # Check keyword matches in results
        for keyword in expected_keywords:
            matches = 0
            for case in cases:
                # Check in subject, keywords, and case_number
                subject = case.get("subject", "").lower()
                case_keywords = [k.lower() for k in case.get("keywords", [])]
                
                if keyword.lower() in subject or any(keyword.lower() in k for k in case_keywords):
                    matches += 1
            
            analysis["keyword_matches"][keyword] = {
                "count": matches,
                "percentage": (matches / len(cases)) * 100 if cases else 0
            }
        
        # Score distribution
        scores = [case.get("relevance_score", 0) for case in cases]
        analysis["score_distribution"] = {
            "min": min(scores) if scores else 0,
            "max": max(scores) if scores else 0,
            "avg": sum(scores) / len(scores) if scores else 0,
            "scores": scores
        }
        
        # Overall relevance assessment
        total_keyword_matches = sum(m["count"] for m in analysis["keyword_matches"].values())
        match_rate = (total_keyword_matches / (len(cases) * len(expected_keywords))) * 100 if cases and expected_keywords else 0
        
        if match_rate > 50:
            analysis["relevance_assessment"] = "good"
        elif match_rate > 20:
            analysis["relevance_assessment"] = "moderate"
        else:
            analysis["relevance_assessment"] = "poor"
        
        analysis["match_rate"] = match_rate
        
        return analysis
    
    def print_results(self, query_info: Dict[str, Any], results: Dict[str, Any], analysis: Dict[str, Any]):
        """Pretty print test results"""
        print("\n" + "=" * 80)
        print(f"TEST: {query_info['description']}")
        print("=" * 80)
        print(f"Question: {query_info['question']}")
        print(f"Expected keywords: {', '.join(query_info['expected_keywords'])}")
        print("-" * 80)
        
        if results.get("status") != "success":
            print(f"❌ FAILED: {results.get('error', 'Unknown error')}")
            return
        
        data = results.get("data", {})
        cases = data.get("cases", [])
        
        print(f"✅ Results found: {len(cases)}")
        
        if not cases:
            print("⚠️  No cases returned!")
            return
        
        # Print analysis
        print(f"\nRelevance Assessment: {analysis['relevance_assessment'].upper()}")
        print(f"Match Rate: {analysis['match_rate']:.1f}%")
        
        print("\nKeyword Matches:")
        for keyword, match_info in analysis["keyword_matches"].items():
            print(f"  - '{keyword}': {match_info['count']}/{len(cases)} cases ({match_info['percentage']:.1f}%)")
        
        print("\nScore Distribution:")
        print(f"  Min: {analysis['score_distribution']['min']:.4f}")
        print(f"  Max: {analysis['score_distribution']['max']:.4f}")
        print(f"  Avg: {analysis['score_distribution']['avg']:.4f}")
        
        print("\nTop 3 Results:")
        for i, case in enumerate(cases[:3], 1):
            print(f"\n  {i}. {case.get('case_number', 'N/A')}")
            print(f"     Court: {case.get('court', 'N/A')}")
            print(f"     Subject: {case.get('subject', 'N/A')[:100]}...")
            print(f"     Score: {case.get('relevance_score', 0):.4f}")
            print(f"     Keywords: {', '.join(case.get('keywords', [])[:5])}")
    
    async def run_comprehensive_test(self):
        """Run comprehensive test suite"""
        print("\n" + "=" * 80)
        print("COMPREHENSIVE SEARCH TESTING")
        print("=" * 80)
        
        # Step 1: Qdrant diagnostics
        print("\n[1/3] Running Qdrant diagnostics...")
        diagnostics = await self.test_qdrant_diagnostics()
        
        if diagnostics.get("status") == "success":
            diag_data = diagnostics.get("data", {})
            summary = diag_data.get("summary", {})
            
            if summary.get("all_tests_passed"):
                print("✅ Qdrant diagnostics: PASSED")
            else:
                print("⚠️  Qdrant diagnostics: ISSUES DETECTED")
                print(f"   {summary.get('recommendation', '')}")
                
                # Print test details
                tests = diag_data.get("tests", {})
                for test_name, test_result in tests.items():
                    status = test_result.get("status", "unknown")
                    print(f"   - {test_name}: {status}")
                    if "warning" in test_result:
                        print(f"     ⚠️  {test_result['warning']}")
        else:
            print(f"❌ Qdrant diagnostics: FAILED - {diagnostics.get('error', 'Unknown error')}")
            return
        
        # Step 2: Run test queries
        print("\n[2/3] Running test queries...")
        
        all_results = []
        for query_info in TEST_QUERIES:
            results = await self.test_basic_search(query_info["question"])
            analysis = self.analyze_results(results, query_info["expected_keywords"])
            
            self.print_results(query_info, results, analysis)
            
            all_results.append({
                "query": query_info,
                "results": results,
                "analysis": analysis
            })
        
        # Step 3: Summary
        print("\n" + "=" * 80)
        print("[3/3] SUMMARY")
        print("=" * 80)
        
        successful_tests = sum(1 for r in all_results if r["results"].get("status") == "success")
        good_relevance = sum(1 for r in all_results if r["analysis"].get("relevance_assessment") == "good")
        
        print(f"Total tests: {len(TEST_QUERIES)}")
        print(f"Successful: {successful_tests}/{len(TEST_QUERIES)}")
        print(f"Good relevance: {good_relevance}/{len(TEST_QUERIES)}")
        
        if good_relevance < len(TEST_QUERIES) / 2:
            print("\n⚠️  WARNING: Less than 50% of queries have good relevance!")
            print("\nPossible issues:")
            print("1. Query generation might be creating irrelevant queries")
            print("2. Embedding model might not match the indexed data")
            print("3. Weighted scoring formula might need adjustment")
            print("4. Collection might not have enough relevant data")
            print("\nRecommendations:")
            print("- Check generated queries in debug mode")
            print("- Verify embedding model consistency")
            print("- Try disabling improved RAG (set USE_IMPROVED_RAG=False)")
            print("- Review the data in your Qdrant collection")


async def main():
    """Main test runner"""
    import os
    
    # Get API key from environment or use default
    api_key = os.getenv("API_KEY", API_KEY)
    
    if not api_key:
        print("⚠️  Warning: No API key set. If your API requires authentication, set API_KEY in .env")
    
    tester = SearchTester(API_BASE_URL, api_key)
    
    print("Starting comprehensive search testing...")
    print(f"API Base URL: {API_BASE_URL}")
    print(f"API Key: {'Set' if api_key else 'Not set'}")
    
    await tester.run_comprehensive_test()
    
    print("\n" + "=" * 80)
    print("Testing complete!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
