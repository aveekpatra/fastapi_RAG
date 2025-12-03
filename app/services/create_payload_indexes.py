"""
Create payload indexes on Qdrant collections for faster filtered queries.

Run this script once to create indexes on case_number and legal_references fields.
This dramatically improves performance of keyword-based searches.

Usage:
    python -m app.services.create_payload_indexes
"""
import asyncio
import httpx
from app.config import settings


COLLECTIONS = [
    settings.QDRANT_CONSTITUTIONAL_COURT,
    settings.QDRANT_SUPREME_COURT,
    settings.QDRANT_SUPREME_ADMIN_COURT,
    settings.QDRANT_COLLECTION,
]

INDEXES = [
    {"field_name": "case_number", "field_schema": "keyword"},
    {"field_name": "legal_references", "field_schema": "keyword"},
    {"field_name": "chunk_index", "field_schema": "integer"},
]


async def create_indexes():
    """Create payload indexes on all collections."""
    qdrant_url = settings.qdrant_url
    headers = {"api-key": settings.QDRANT_API_KEY} if settings.QDRANT_API_KEY else {}
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        for collection in COLLECTIONS:
            print(f"\n📦 Collection: {collection}")
            
            for index in INDEXES:
                try:
                    response = await client.put(
                        f"{qdrant_url}/collections/{collection}/index",
                        headers=headers,
                        json=index,
                    )
                    
                    if response.status_code == 200:
                        print(f"   ✅ Created index: {index['field_name']}")
                    elif response.status_code == 400:
                        # Index might already exist
                        print(f"   ⏭️ Index exists: {index['field_name']}")
                    else:
                        print(f"   ❌ Failed: {index['field_name']} - {response.status_code}")
                        
                except Exception as e:
                    print(f"   ❌ Error: {index['field_name']} - {e}")
    
    print("\n✅ Done!")


if __name__ == "__main__":
    asyncio.run(create_indexes())
