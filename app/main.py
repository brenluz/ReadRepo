from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import router as auth_router
from app.chat import router as chat_router
from app.config import settings
from app.repos import router as repos_router

app = FastAPI(title="ReadRepo")

# Allow the browser extension (and local dev clients) to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(repos_router)
app.include_router(chat_router)


@app.get("/")
async def root() -> dict:
    # Public health/info route (no auth: repo features run unauthenticated).
    return {"name": "ReadRepo", "status": "ok"}
