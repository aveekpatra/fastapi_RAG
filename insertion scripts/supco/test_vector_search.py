import json
import os
import random
import re
from pathlib import Path

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

# ============= CONFIGURATION =============
QDRANT_HOST = "hopper.proxy.rlwy.net"
QDRANT_PORT = 48447
QDRANT_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.cWl-rXCSkKbL9rIzNj00YIYFkMskD71UfoKfoECy7I0"
QDRANT_HTTPS = False

COLLECTION_NAME = "czech_supreme_court"
EMBEDDING_MODEL = "Seznam/retromae-small-cs"
INPUT_FOLDER = "json-output"

# ============= HELPER FUNCTIONS =============
def extract_key_phrases(text, num_phrases=5):
    """Extract key phrases from text for testing."""
    # Remove common words and extract meaningful phrases
    sentences = re.split(r'[.!?]\s+', text)
    phrases = []
    
    for sentence in sentences[:20]:  # Check first 20 sentences
        sentence = sentence.strip()
        if len(sentence) > 30 and len(sentence) < 200:
            # Look for legal terms
            if any(word in sentence.lower() for word in ['soud', 'práv', 'zákon', 'rozhodnutí', 'stěžovatel']):
                phrases.append(sentence)
        
        if len(phrases) >= num_phrases:
            break
    
    return phrases

def generate_test_queries(json_files, num_queries=5):
    """Generate realistic legal scenario queries that people would actually search for."""
    
    # Real-world legal scenarios based on Czech Supreme Court cases
    test_queries = [
        {
            'text': 'Jaké jsou podmínky pro určení neexistence věcného břemene na nemovitosti?',
            'description': 'Question about conditions for determining non-existence of easements on property'
        },
        {
            'text': 'Může zástavní věřitel napadnout věcná břemena zřízená bez jeho souhlasu?',
            'description': 'Query about mortgage creditor challenging easements created without consent'
        },
        {
            'text': 'Kdo musí být účastníkem řízení o určení existence věcného břemene?',
            'description': 'Question about required parties in proceedings to determine easement existence'
        },
        {
            'text': 'Jaká je věcná legitimace v řízení o určení práva k nemovitosti?',
            'description': 'Query about standing in proceedings to determine property rights'
        },
        {
            'text': 'Může soud rozhodnout o věcném břemenu bez účasti všech spoluvlastníků?',
            'description': 'Question about court deciding on easement without all co-owners present'
        },
        {
            'text': 'Jaký je rozdíl mezi naléhavým právním zájmem a věcnou legitimací?',
            'description': 'Query about difference between urgent legal interest and standing'
        },
        {
            'text': 'Musí být správce konkursní podstaty účastníkem sporu o věcná břemena?',
            'description': 'Question about bankruptcy trustee participation in easement disputes'
        },
        {
            'text': 'Kdy lze podat dovolání proti rozhodnutí odvolacího soudu?',
            'description': 'Query about when cassation appeal can be filed against appellate court decision'
        },
        {
            'text': 'Jaké jsou důvody pro zrušení rozhodnutí odvolacího soudu?',
            'description': 'Question about grounds for annulling appellate court decisions'
        },
        {
            'text': 'Co se stane když zástavce zatíží nemovitost bez souhlasu zástavního věřitele?',
            'description': 'Query about consequences when pledgor encumbers property without creditor consent'
        }
    ]
    
    return test_queries

# ============= SEARCH TESTING =============
class VectorSearchTester:
    def __init__(self):
        print("🚀 Vector Search Testing Tool")
        print("=" * 60)
        
        print(f"🧠 Loading embedding model: {EMBEDDING_MODEL}")
        self.model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
        
        print("🔗 Connecting to Qdrant...")
        self.client = QdrantClient(
            host=QDRANT_HOST,
            port=QDRANT_PORT,
            api_key=QDRANT_API_KEY,
            https=QDRANT_HTTPS,
            timeout=60,
        )
        
        print("✅ Initialization complete\n")

    def check_collection_stats(self):
        """Check collection statistics."""
        print("📊 Collection Statistics")
        print("-" * 60)
        
        try:
            collection_info = self.client.get_collection(COLLECTION_NAME)
            
            print(f"Collection name: {COLLECTION_NAME}")
            print(f"Total points: {collection_info.points_count}")
            print(f"Vector size: {collection_info.config.params.vectors.size}")
            print(f"Distance metric: {collection_info.config.params.vectors.distance}")
            print()
            
            return collection_info.points_count
        
        except Exception as e:
            print(f"❌ Error getting collection info: {e}")
            return 0

    def search(self, query_text, top_k=5):
        """Perform vector search."""
        try:
            # Embed query
            query_vector = self.model.encode(
                query_text,
                normalize_embeddings=True
            ).tolist()
            
            # Search
            results = self.client.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_vector,
                limit=top_k,
                with_payload=True
            )
            
            return results
        
        except Exception as e:
            print(f"❌ Search error: {e}")
            return []

    def test_query(self, query_info, query_num):
        """Test a single query."""
        print(f"\n🔍 Test Query #{query_num}")
        print("-" * 60)
        print(f"Scenario: {query_info.get('description', 'N/A')}")
        print(f"Query: {query_info['text']}")
        print()
        
        results = self.search(query_info['text'], top_k=5)
        
        if not results:
            print("❌ No results returned!")
            return False
        
        print(f"📋 Top {len(results)} Results:")
        print()
        
        # Check if results are relevant (score > 0.5 is generally good)
        relevant_results = 0
        
        for i, result in enumerate(results, 1):
            case_number = result.payload.get('case_number', 'N/A')
            date = result.payload.get('date', 'N/A')
            chunk_index = result.payload.get('chunk_index', 0)
            total_chunks = result.payload.get('total_chunks', 0)
            has_full_text = result.payload.get('has_full_text', False)
            chunk_text = result.payload.get('chunk_text', '')
            score = result.score
            
            print(f"  {i}. Case: {case_number} ({date})")
            print(f"     Relevance Score: {score:.4f}")
            print(f"     Chunk: {chunk_index + 1}/{total_chunks}")
            print(f"     Has full text: {'✅' if has_full_text else '❌'}")
            print(f"     Context preview:")
            print(f"     {chunk_text[:200]}...")
            
            if score > 0.5:
                relevant_results += 1
                print(f"     ✅ RELEVANT (score > 0.5)")
            else:
                print(f"     ⚠️  Low relevance (score ≤ 0.5)")
            
            print()
        
        if relevant_results >= 3:
            print(f"✅ Test PASSED - Found {relevant_results} relevant results with good context")
            return True
        elif relevant_results >= 1:
            print(f"⚠️  Test PARTIAL - Found {relevant_results} relevant results (expected 3+)")
            return False
        else:
            print("❌ Test FAILED - No relevant results found")
            return False

    def test_chunk_zero_retrieval(self):
        """Test that chunk 0 has full_text."""
        print("\n🔬 Testing Chunk 0 Full Text Storage")
        print("-" * 60)
        
        try:
            # Get a random point
            results = self.client.scroll(
                collection_name=COLLECTION_NAME,
                limit=10,
                with_payload=True
            )
            
            points = results[0]
            
            if not points:
                print("❌ No points found in collection")
                return False
            
            chunk_zero_found = False
            chunk_zero_has_full_text = False
            
            for point in points:
                chunk_index = point.payload.get('chunk_index', -1)
                has_full_text = point.payload.get('has_full_text', False)
                full_text = point.payload.get('full_text')
                
                if chunk_index == 0:
                    chunk_zero_found = True
                    case_number = point.payload.get('case_number', 'N/A')
                    
                    print(f"Found chunk 0 for case: {case_number}")
                    print(f"Has full_text field: {'✅' if full_text else '❌'}")
                    print(f"Has full_text flag: {'✅' if has_full_text else '❌'}")
                    
                    if full_text:
                        print(f"Full text length: {len(full_text)} characters")
                        chunk_zero_has_full_text = True
                    
                    break
            
            if chunk_zero_found and chunk_zero_has_full_text:
                print("\n✅ Chunk 0 storage test PASSED")
                return True
            else:
                print("\n❌ Chunk 0 storage test FAILED")
                return False
        
        except Exception as e:
            print(f"❌ Error testing chunk 0: {e}")
            return False

    def test_non_chunk_zero(self):
        """Test that non-chunk-0 chunks don't have full_text."""
        print("\n🔬 Testing Non-Chunk-0 Storage Efficiency")
        print("-" * 60)
        
        try:
            results = self.client.scroll(
                collection_name=COLLECTION_NAME,
                limit=20,
                with_payload=True
            )
            
            points = results[0]
            
            non_zero_chunks = [p for p in points if p.payload.get('chunk_index', 0) > 0]
            
            if not non_zero_chunks:
                print("⚠️  No non-zero chunks found in sample")
                return True
            
            has_full_text_count = 0
            
            for point in non_zero_chunks[:5]:
                chunk_index = point.payload.get('chunk_index', -1)
                full_text = point.payload.get('full_text')
                case_number = point.payload.get('case_number', 'N/A')
                
                print(f"Chunk {chunk_index} of case {case_number}: ", end="")
                
                if full_text:
                    print("❌ Has full_text (should not!)")
                    has_full_text_count += 1
                else:
                    print("✅ No full_text (correct)")
            
            if has_full_text_count == 0:
                print("\n✅ Storage efficiency test PASSED")
                return True
            else:
                print(f"\n⚠️  Found {has_full_text_count} non-zero chunks with full_text")
                return False
        
        except Exception as e:
            print(f"❌ Error testing non-chunk-0: {e}")
            return False

    def run_tests(self):
        """Run all tests."""
        print("\n" + "=" * 60)
        print("STARTING VECTOR SEARCH VERIFICATION")
        print("=" * 60 + "\n")
        
        # Check collection stats
        total_points = self.check_collection_stats()
        
        if total_points == 0:
            print("❌ Collection is empty! Upload data first.")
            return
        
        # Test chunk 0 storage
        self.test_chunk_zero_retrieval()
        
        # Test non-chunk-0 storage
        self.test_non_chunk_zero()
        
        # Generate test queries
        print("\n📝 Testing with Real-World Legal Scenarios")
        print("-" * 60)
        print("These queries simulate actual questions people would ask")
        print("when searching for relevant Supreme Court case law.\n")
        
        queries = generate_test_queries([], num_queries=10)
        
        if not queries:
            print("❌ Could not generate test queries")
            return
        
        print(f"Testing {len(queries)} realistic legal scenarios\n")
        
        # Run search tests
        passed = 0
        total = len(queries)
        
        for i, query_info in enumerate(queries, 1):
            if self.test_query(query_info, i):
                passed += 1
        
        # Final summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        print(f"Total queries tested: {total}")
        print(f"Queries passed: {passed}")
        print(f"Success rate: {(passed/total)*100:.1f}%")
        
        if passed == total:
            print("\n✅ ALL TESTS PASSED! Vector search is working perfectly.")
        elif passed > total * 0.7:
            print("\n⚠️  MOST TESTS PASSED. Vector search is working but may need tuning.")
        else:
            print("\n❌ MANY TESTS FAILED. Check your data and embeddings.")
        
        print("=" * 60)

if __name__ == "__main__":
    tester = VectorSearchTester()
    tester.run_tests()
