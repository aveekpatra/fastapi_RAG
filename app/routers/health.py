from datetime import datetime
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}