from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.materials import router as materials_router
from app.core.config import settings
from app.core.middleware import RateLimitMiddleware

app = FastAPI(title="Exam Review Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)

app.include_router(materials_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "default_provider": settings.default_llm_provider}
