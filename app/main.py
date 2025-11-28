from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import health, legal, search, multi_source

app = FastAPI(
    title="Czech Legal Assistant API",
    description="AI-powered legal query system with RAG - Multi-source support",
    version="2.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=getattr(settings, "ALLOWED_ORIGINS", "http://localhost:3000").split(
        ","
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Security middleware to add headers
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )
    return response


# Include routers
app.include_router(health.router)
app.include_router(legal.router)
app.include_router(search.router)
app.include_router(multi_source.router)  # New multi-source endpoints at /v2


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
