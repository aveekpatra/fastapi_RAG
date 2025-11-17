"""
Test script to verify Qdrant connection and data
Run this to diagnose why case search returns no results
"""
import asyncio
import httpx
from dotenv import load_dotenv
import os

load_dotenv()

QDRANT_HOST = os.getenv("QDRANT_HOST", "")
QDRANT_PORT = os.getenv("QDRANT_PORT", "6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
QDRANT_HTTPS = os.getenv("QDRANT_HTTPS", "False").lower() == "true"
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "")

protocol = "https" if QDRANT_HTTPS else "http"
qdrant_url = f"{protocol}://{QDRANT_HOST}:{QDRANT_PORT}"

print("=" * 60)
print("QDRANT CONNECTION TEST")
print("=" * 60)
print(f"URL: {qdrant_url}")
print(f"Collection: {QDRANT_COLLECTION}")
print(f"Has API Key: {bool(QDRANT_API_KEY)}")
print("=" * 60)


async def test_connection():
    """Test basic connection to Qdrant"""
    headers = {"api-key": QDRANT_API_KEY} if QDRANT_API_KEY else {}
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            print("\n1. Testing connection to Qdrant...")
            response = await client.get(f"{qdrant_url}/collections", headers=headers)
            
            if response.status_code == 200:
                print("✅ Connection successful!")
                collections = response.json()
                print(f"   Collections: {collections}")
            else:
                print(f"❌ Connection failed: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
                
    except Exception as e:
        print(f"❌ Connection error: {str(e)}")
        return False
    
    return True


async def test_collection():
    """Test if collection exists and has data"""
    headers = {"api-key": QDRANT_API_KEY} if QDRANT_API_KEY else {}
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            print(f"\n2. Checking collection '{QDRANT_COLLECTION}'...")
            response = await client.get(
                f"{qdrant_url}/collections/{QDRANT_COLLECTION}",
                headers=headers
            )
            
            if response.status_code == 200:
                info = response.json()
                print("✅ Collection exists!")
                print(f"   Status: {info.get('status')}")
                
                result = info.get('result', {})
                vectors_count = result.get('vectors_count') or result.get('points_count', 0)
                print(f"   Points count: {vectors_count}")
                
                if vectors_count == 0:
                    print("⚠️  WARNING: Collection is EMPTY! No data to search.")
                    return False
                    
                config = result.get('config', {})
                params = config.get('params', {})
                vectors_config = params.get('vectors', {})
                
                if isinstance(vectors_config, dict):
                    size = vectors_config.get('size', 'unknown')
                    distance = vectors_config.get('distance', 'unknown')
                    print(f"   Vector size: {size}")
                    print(f"   Distance metric: {distance}")
                
                return True
            else:
                print(f"❌ Collection not found: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
                
    except Exception as e:
        print(f"❌ Error checking collection: {str(e)}")
        return False


async def test_search():
    """Test a simple search"""
    headers = {"api-key": QDRANT_API_KEY} if QDRANT_API_KEY else {}
    
    try:
        # Generate a test embedding
        from sentence_transformers import SentenceTransformer
        print("\n3. Loading embedding model...")
        model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        
        test_query = "rozvod manželství"
        print(f"   Test query: '{test_query}'")
        
        print("   Generating embedding...")
        vector = model.encode(test_query).tolist()
        print(f"   Vector dimension: {len(vector)}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            print(f"\n4. Searching in collection '{QDRANT_COLLECTION}'...")
            response = await client.post(
                f"{qdrant_url}/collections/{QDRANT_COLLECTION}/points/search",
                headers=headers,
                json={
                    "vector": vector,
                    "limit": 5,
                    "with_payload": True,
                }
            )
            
            if response.status_code == 200:
                results = response.json()
                result_list = results.get('result', [])
                print(f"✅ Search successful!")
                print(f"   Results found: {len(result_list)}")
                
                if len(result_list) == 0:
                    print("\n⚠️  WARNING: Search returned 0 results!")
                    print("   Possible reasons:")
                    print("   - Collection is empty")
                    print("   - Query doesn't match any documents")
                    print("   - Embedding model mismatch")
                else:
                    print("\n   Top results:")
                    for i, result in enumerate(result_list[:3], 1):
                        payload = result.get('payload', {})
                        score = result.get('score', 0)
                        case_num = payload.get('case_number', 'N/A')
                        court = payload.get('court', 'N/A')
                        print(f"   {i}. {case_num} - {court} (score: {score:.4f})")
                
                return len(result_list) > 0
            else:
                print(f"❌ Search failed: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
                
    except Exception as e:
        print(f"❌ Error during search: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests"""
    print("\nStarting diagnostic tests...\n")
    
    # Test 1: Connection
    if not await test_connection():
        print("\n❌ FAILED: Cannot connect to Qdrant")
        return
    
    # Test 2: Collection
    if not await test_collection():
        print("\n❌ FAILED: Collection issue detected")
        return
    
    # Test 3: Search
    if not await test_search():
        print("\n⚠️  WARNING: Search returned no results")
        print("\nRECOMMENDATION: Check if data was properly uploaded to Qdrant")
        return
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("=" * 60)
    print("\nQdrant is working correctly. If you're still seeing issues,")
    print("the problem might be in the API layer or frontend.")


if __name__ == "__main__":
    asyncio.run(main())
