import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.config import settings
from app.sessions import session_store

router = APIRouter(prefix="/auth")

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"

STATE_COOKIE_NAME = "oauth_state"
SESSION_COOKIE_NAME = "session_id"


@router.get("/login")
async def login() -> RedirectResponse:
    """
    Step 1 of the flow: send the user to GitHub's consent screen.

    We generate a random `state` value and stash it in a short-lived
    cookie *before* redirecting. GitHub will hand this same value
    back to us in the callback, and we'll check it matches — that's
    what stops an attacker from crafting their own callback URL and
    tricking a victim's browser into completing an OAuth exchange
    that isn't theirs.
    """
    if not settings.github_client_id or not settings.github_client_secret:
        raise HTTPException(
            status_code=503,
            detail="GitHub OAuth is not configured (set GITHUB_CLIENT_ID / "
            "GITHUB_CLIENT_SECRET). Repo features work without it.",
        )

    state = secrets.token_urlsafe(16)

    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": settings.oauth_redirect_uri,
        "scope": settings.oauth_scope,
        "state": state,
    }
    github_url = f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"

    response = RedirectResponse(url=github_url)
    response.set_cookie(
        key=STATE_COOKIE_NAME,
        value=state,
        httponly=True,       # not readable by JS - blocks XSS from stealing it
        secure=False,        # flip to True once you're on HTTPS (required in prod)
        samesite="lax",      # sent on top-level GET redirects like this one
        max_age=600,         # only needs to live for the few seconds of the redirect round-trip
    )
    return response


@router.get("/callback")
async def callback(
    request: Request,
    code: str,
    state: str,
    oauth_state: str | None = Cookie(default=None),
) -> RedirectResponse:
    """
    Step 2: GitHub redirects here with a temporary `code` after the
    user approves access. We (a) verify `state` matches what we set,
    (b) exchange `code` for an access token — this exchange must
    happen server-side since it requires `client_secret`, which must
    never reach the browser — and (c) create our own session.
    """
    if not oauth_state or oauth_state != state:
        raise HTTPException(status_code=400, detail="Invalid or missing OAuth state")

    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.oauth_redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        token_response.raise_for_status()
        token_data = token_response.json()

        if "error" in token_data:
            raise HTTPException(status_code=400, detail=token_data.get("error_description", "OAuth error"))

        access_token = token_data["access_token"]

        # Fetch the user's login now so we don't need a second round
        # trip later just to know "who is this."
        user_response = await client.get(
            GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_response.raise_for_status()
        github_login = user_response.json()["login"]

    session_id = session_store.create(
        {"access_token": access_token, "github_login": github_login}
    )

    response = RedirectResponse(url="/")
    response.delete_cookie(STATE_COOKIE_NAME)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=False,  # same note as above: True in production
        samesite="lax",
        # No max_age set here deliberately -> session cookie, cleared
        # when the browser closes. We'll revisit this once we talk
        # about token expiry/refresh.
    )
    return response


async def get_current_user(session_id: str | None = Cookie(default=None)) -> dict:
    """
    A FastAPI dependency later routes will use like:

        @router.get("/ask")
        async def ask(user: dict = Depends(get_current_user)): ...

    Centralizing "how do I know who's asking" in one place means the
    RAG endpoints don't need to know anything about cookies or
    sessions — they just receive a dict with the token they need to
    call the GitHub API as this user.
    """
    if session_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session = session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid")

    return session