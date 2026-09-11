from fastapi import Depends, FastAPI

from app.auth import get_current_user, router as auth_router
from app.repos import router as repos_router

app = FastAPI(title="Repo Q&A Bot")
app.include_router(auth_router)
app.include_router(repos_router)


@app.get("/")
async def root(user: dict = Depends(get_current_user)):
    # Placeholder landing route so we can confirm the whole login ->
    # callback -> session flow works end to end. This is where the
    # chat UI will eventually live.
    return {"message": f"Logged in as {user['github_login']}"}