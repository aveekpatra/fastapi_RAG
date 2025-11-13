from fastapi import FastAPI
from app.config import settings
from app.routers import health, legal, search

app = FastAPI(
    title="Czech Legal Assistant API",
    description="AI-powered legal query system with RAG",
    version="1.0.0",
)

# Include routers
app.include_router(health.router)
app.include_router(legal.router)
app.include_router(search.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.HOST, port=settings.PORT)